from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.planner import planner_node
from app.agents.nodes.researcher import researcher_node
from app.agents.nodes.synthesizer import synthesizer_node
from app.agents.state import AgentState


def _after_planner(state: AgentState) -> str:
    if state.get("fatal_error"):
        return END
    return "researcher"


def _after_researcher(state: AgentState) -> str:
    if state.get("fatal_error"):
        return END
    if state["current_step"] < len(state["plan"]):
        return "researcher"
    return "synthesizer"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", _after_planner, {"researcher": "researcher", END: END})
    graph.add_conditional_edges(
        "researcher",
        _after_researcher,
        {"researcher": "researcher", "synthesizer": "synthesizer", END: END},
    )
    graph.add_edge("synthesizer", END)

    return graph.compile()
