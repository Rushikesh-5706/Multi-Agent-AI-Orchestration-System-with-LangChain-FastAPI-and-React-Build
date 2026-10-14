from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: type
    runner: Callable[..., str]
    execution: Literal["celery", "inline"]
    celery_task_name: str | None = None


def _build_registry() -> list[ToolSpec]:
    from app.tools.calculator import run_calculator
    from app.tools.schemas import CalculatorInput, WeatherSearchInput, WebSearchInput
    from app.tools.weather import run_get_weather
    from app.tools.web_search import run_web_search

    return [
        ToolSpec(
            name="web_search",
            description=WebSearchInput.__doc__ or "",
            args_schema=WebSearchInput,
            runner=run_web_search,
            execution="celery",
            celery_task_name="tools.web_search",
        ),
        ToolSpec(
            name="get_weather",
            description=WeatherSearchInput.__doc__ or "",
            args_schema=WeatherSearchInput,
            runner=run_get_weather,
            execution="celery",
            celery_task_name="tools.get_weather",
        ),
        ToolSpec(
            name="data_calculator",
            description=CalculatorInput.__doc__ or "",
            args_schema=CalculatorInput,
            runner=run_calculator,
            execution="inline",
        ),
    ]


_REGISTRY: list[ToolSpec] | None = None


def get_tool_registry() -> list[ToolSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def get_tool_catalog_text() -> str:
    lines: list[str] = []
    for spec in get_tool_registry():
        schema = spec.args_schema.model_json_schema()
        fields = schema.get("properties", {})
        field_desc = ", ".join(f"{k}: {v.get('description', '')[:60]}" for k, v in fields.items())
        lines.append(f"- {spec.name}: {spec.description.strip()[:200]} | fields: {field_desc}")
    return "\n".join(lines)
