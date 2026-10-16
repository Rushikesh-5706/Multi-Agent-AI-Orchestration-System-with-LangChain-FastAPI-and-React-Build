from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END

from app.agents.graph import _after_planner, _after_researcher, _after_synthesizer
from app.agents.llm import LLMConfigurationError
from app.agents.nodes.planner import _parse_plan, planner_node
from app.agents.nodes.researcher import _format_previous_findings, researcher_node
from app.agents.nodes.synthesizer import synthesizer_node
from app.agents.state import AgentState, Finding
from app.core.enums import EventType


class ScriptedChatModel:
    def __init__(self, responses_by_agent: dict[str, list[object]]) -> None:
        self.responses_by_agent = {k: list(v) for k, v in responses_by_agent.items()}
        self.tools_bound: list[dict] = []
        self.call_history: list[list[object]] = []

    def bind_tools(self, tools: list[dict]) -> ScriptedChatModel:
        self.tools_bound = tools
        return self

    async def ainvoke(self, messages: list[object]) -> object:
        self.call_history.append(messages)
        # Determine role from system prompt
        sys_msg = str(messages[0].content) if hasattr(messages[0], "content") else str(messages[0])
        role = "unknown"
        if "Planner agent" in sys_msg:
            role = "planner"
        elif "Researcher agent" in sys_msg:
            role = "researcher"
        elif "Synthesizer agent" in sys_msg:
            role = "synthesizer"

        if role in self.responses_by_agent and self.responses_by_agent[role]:
            resp = self.responses_by_agent[role].pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return AIMessage(content="default scripted response")


def test_routing_functions_in_isolation() -> None:
    # _after_planner
    assert _after_planner({"fatal_error": "Config missing"}) == END
    assert _after_planner({"fatal_error": None}) == "researcher"

    # _after_researcher
    assert _after_researcher({"fatal_error": "Fatal", "current_step": 0, "plan": ["a"]}) == END
    assert (
        _after_researcher({"fatal_error": None, "current_step": 1, "plan": ["a", "b"]})
        == "researcher"
    )
    assert (
        _after_researcher({"fatal_error": None, "current_step": 2, "plan": ["a", "b"]})
        == "synthesizer"
    )

    # _after_synthesizer
    assert _after_synthesizer({"fatal_error": None}) == END
    assert _after_synthesizer({"fatal_error": "Error"}) == END


def test_planner_parses_both_json_shapes() -> None:
    # Array format
    plan_arr = _parse_plan('["Step 1", "Step 2"]', 5)
    assert plan_arr == ["Step 1", "Step 2"]

    # Object format
    plan_obj = _parse_plan('{"steps": ["Step A", "Step B"]}', 5)
    assert plan_obj == ["Step A", "Step B"]


@pytest.mark.asyncio
async def test_planner_failing_twice_triggers_single_step_fallback() -> None:
    llm = ScriptedChatModel(
        {"planner": [AIMessage(content="Bad plan 1"), AIMessage(content="Bad plan 2")]}
    )
    publisher = AsyncMock()

    config = {"configurable": {"publisher": publisher, "llm": llm}}
    state: AgentState = {
        "task_id": "test-task",
        "prompt": "Find Tokyo weather",
        "plan": [],
        "current_step": 0,
        "findings": [],
        "final_answer": None,
        "fatal_error": None,
    }

    result = await planner_node(state, config)
    assert result["plan"] == ["Find Tokyo weather"]

    # Emitted non-fatal error event
    error_call = [
        call
        for call in publisher.emit.call_args_list
        if call.kwargs.get("event_type") == EventType.ERROR
    ]
    assert len(error_call) == 1
    assert error_call[0].kwargs["payload"]["kind"] == "plan_parse_failure"
    assert error_call[0].kwargs["payload"]["fatal"] is False


def test_researcher_previous_findings_formatting_and_trimming() -> None:
    findings: list[Finding] = [
        {
            "step_index": 0,
            "step": "Get Tokyo weather",
            "finding": "18C and sunny",
            "tools_used": [],
            "had_errors": False,
        },
        {
            "step_index": 1,
            "step": "Get London weather",
            "finding": "12C and rainy",
            "tools_used": [],
            "had_errors": False,
        },
    ]

    formatted = _format_previous_findings(findings)
    assert "Step 1 (Get Tokyo weather): 18C and sunny" in formatted
    assert "Step 2 (Get London weather): 12C and rainy" in formatted

    # Trimming test: when length > 1800, oldest finding is popped
    long_findings: list[Finding] = [
        {
            "step_index": 0,
            "step": "Old step",
            "finding": "X" * 1500,
            "tools_used": [],
            "had_errors": False,
        },
        {
            "step_index": 1,
            "step": "New step",
            "finding": "Y" * 500,
            "tools_used": [],
            "had_errors": False,
        },
    ]
    trimmed = _format_previous_findings(long_findings)
    assert "Old step" not in trimmed
    assert "New step" in trimmed


@pytest.mark.asyncio
async def test_researcher_per_step_llm_failure_records_unavailable_and_continues() -> None:
    llm = ScriptedChatModel({"researcher": [RuntimeError("Temporary provider failure")]})
    publisher = AsyncMock()

    config = {"configurable": {"publisher": publisher, "llm": llm}}
    state: AgentState = {
        "task_id": "task-recover",
        "prompt": "Test recovery",
        "plan": ["Step 1", "Step 2"],
        "current_step": 0,
        "findings": [],
        "final_answer": None,
        "fatal_error": None,
    }

    result = await researcher_node(state, config)
    assert result["current_step"] == 1
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert "Unavailable: the model request failed (RuntimeError)." in finding["finding"]
    assert finding["had_errors"] is True


@pytest.mark.asyncio
async def test_researcher_llm_configuration_error_returns_fatal_error() -> None:
    llm = ScriptedChatModel({"researcher": [LLMConfigurationError("Invalid API key")]})
    publisher = AsyncMock()

    config = {"configurable": {"publisher": publisher, "llm": llm}}
    state: AgentState = {
        "task_id": "task-fatal",
        "prompt": "Test fatal",
        "plan": ["Step 1"],
        "current_step": 0,
        "findings": [],
        "final_answer": None,
        "fatal_error": None,
    }

    result = await researcher_node(state, config)
    assert result.get("fatal_error") == "Invalid API key"


@pytest.mark.asyncio
async def test_synthesizer_failure_returns_fatal_error() -> None:
    llm = ScriptedChatModel({"synthesizer": [RuntimeError("Synthesis model failed")]})
    publisher = AsyncMock()

    config = {"configurable": {"publisher": publisher, "llm": llm}}
    state: AgentState = {
        "task_id": "task-synth-fail",
        "prompt": "Prompt",
        "plan": ["Step 1"],
        "current_step": 1,
        "findings": [
            {
                "step_index": 0,
                "step": "Step 1",
                "finding": "Found 18C",
                "tools_used": [],
                "had_errors": False,
            }
        ],
        "final_answer": None,
        "fatal_error": None,
    }

    result = await synthesizer_node(state, config)
    assert "fatal_error" in result
    assert "Synthesizer failed to produce an answer" in result["fatal_error"]
