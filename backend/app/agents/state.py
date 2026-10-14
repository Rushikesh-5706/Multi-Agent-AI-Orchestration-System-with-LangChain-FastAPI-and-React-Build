from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Finding(TypedDict):
    step_index: int
    step: str
    finding: str
    tools_used: list[str]
    had_errors: bool


class AgentState(TypedDict):
    task_id: str
    prompt: str
    plan: list[str]
    current_step: int
    findings: Annotated[list[Finding], operator.add]
    messages: Annotated[list[dict], operator.add]
    final_answer: str | None
    fatal_error: str | None
