from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError

from app.agents.tool_executor import execute_named_tool, execute_tool, get_spec_by_name
from app.core.enums import EventType


@pytest.mark.asyncio
async def test_unknown_tool_emits_audit_events_and_returns_error() -> None:
    publisher = AsyncMock()
    result = await execute_named_tool(
        name="nonexistent_tool",
        arguments={"arg": 1},
        publisher=publisher,
        task_id="task-123",
    )

    assert result.startswith("Error: Unknown tool 'nonexistent_tool'")
    assert publisher.emit.call_count == 2

    # Check TOOL_INVOCATION
    inv_call = publisher.emit.call_args_list[0].kwargs
    assert inv_call["event_type"] == EventType.TOOL_INVOCATION
    assert inv_call["payload"]["execution"] == "rejected"

    # Check TOOL_RESULT
    res_call = publisher.emit.call_args_list[1].kwargs
    assert res_call["event_type"] == EventType.TOOL_RESULT
    assert res_call["payload"]["is_error"] is True
    assert res_call["payload"]["execution"] == "rejected"


@pytest.mark.asyncio
async def test_invalid_arguments_emit_audit_events_and_return_error() -> None:
    publisher = AsyncMock()
    # get_weather requires location string; provide invalid type
    result = await execute_named_tool(
        name="get_weather",
        arguments={},
        publisher=publisher,
        task_id="task-123",
    )

    assert result.startswith("Error: Tool arguments failed validation for 'get_weather'")
    assert publisher.emit.call_count == 2
    assert publisher.emit.call_args_list[1].kwargs["payload"]["is_error"] is True


@pytest.mark.asyncio
async def test_inline_calculator_and_duration_recorded() -> None:
    publisher = AsyncMock()
    result = await execute_named_tool(
        name="data_calculator",
        arguments={"operation": "expression", "expression": "10 * 5"},
        publisher=publisher,
        task_id="task-123",
    )

    assert "Result: 50" in result
    assert publisher.emit.call_count == 2
    res_call = publisher.emit.call_args_list[1].kwargs
    assert res_call["payload"]["duration_ms"] >= 0
    assert res_call["payload"]["is_error"] is False


@pytest.mark.asyncio
async def test_celery_success_in_eager_mode() -> None:
    from unittest.mock import MagicMock

    publisher = AsyncMock()
    with patch("requests.get") as mock_get:
        geo_mock = MagicMock()
        geo_mock.status_code = 200
        geo_mock.json.return_value = [
            {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo", "country": "JP"}
        ]

        weather_mock = MagicMock()
        weather_mock.status_code = 200
        weather_mock.json.return_value = {
            "main": {"temp": 18.5, "feels_like": 17.0, "humidity": 60},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 3.2},
            "sys": {"country": "JP"},
            "name": "Tokyo",
        }
        mock_get.side_effect = [geo_mock, weather_mock]

        result = await execute_named_tool(
            name="get_weather",
            arguments={"location": "Tokyo, JP"},
            publisher=publisher,
            task_id="task-123",
        )

        assert "Tokyo" in result
        assert "18.5" in result
        assert publisher.emit.call_count == 2


@pytest.mark.asyncio
async def test_celery_timeout_revokes_and_returns_timeout_message() -> None:
    publisher = AsyncMock()
    spec = get_spec_by_name("get_weather")
    assert spec is not None

    from unittest.mock import MagicMock

    mock_async_result = MagicMock()
    mock_async_result.id = "celery-task-999"
    mock_async_result.get = MagicMock(side_effect=CeleryTimeoutError("Timeout"))

    with patch("app.worker.celery_app.celery_app.tasks.get") as mock_get_task:
        mock_task = MagicMock()
        mock_task.apply_async.return_value = mock_async_result
        mock_get_task.return_value = mock_task

        with patch("app.worker.celery_app.celery_app.control.revoke") as mock_revoke:
            result = await execute_tool(
                spec=spec,
                validated_args={"location": "Tokyo"},
                publisher=publisher,
                task_id="task-123",
            )

            assert "timed out after" in result
            mock_revoke.assert_called_once_with("celery-task-999", terminate=True)


@pytest.mark.asyncio
async def test_truncation_marker() -> None:
    publisher = AsyncMock()
    spec = get_spec_by_name("data_calculator")
    assert spec is not None

    with patch.object(spec, "runner", return_value="A" * 3000):
        result = await execute_tool(
            spec=spec,
            validated_args={"expression": "1+1"},
            publisher=publisher,
            task_id="task-123",
        )

        assert result.endswith("[truncated]")
        assert len(result) <= 1500 + len(" [truncated]")
