from __future__ import annotations

from unittest.mock import AsyncMock, patch

import groq
import httpx
import pytest

from app.agents.llm import LLMConfigurationError, invoke_with_retry


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status_code, request=request, headers=headers or {})


class MockLLM:
    def __init__(self, side_effects: list[object]) -> None:
        self.side_effects = list(side_effects)
        self.call_count = 0
        self.messages_received: list[list[object]] = []

    async def ainvoke(self, messages: list[object]) -> object:
        self.call_count += 1
        self.messages_received.append(messages)
        if not self.side_effects:
            return "default_success"
        effect = self.side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


@pytest.mark.asyncio
async def test_authentication_error_raises_configuration_error() -> None:
    resp = _make_response(401)
    exc = groq.AuthenticationError("Invalid API Key", response=resp, body=None)
    llm = MockLLM([exc])

    with pytest.raises(LLMConfigurationError) as exc_info:
        await invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

    assert "invalid or not authorized" in str(exc_info.value)
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_permission_denied_raises_configuration_error() -> None:
    resp = _make_response(403)
    exc = groq.PermissionDeniedError("Forbidden", response=resp, body=None)
    llm = MockLLM([exc])

    with pytest.raises(LLMConfigurationError) as exc_info:
        await invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

    assert "invalid or not authorized" in str(exc_info.value)
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_plain_exception_with_401_or_500_raised_unchanged() -> None:
    plain_exc_401 = Exception("401 Client Error")
    llm_401 = MockLLM([plain_exc_401])

    with pytest.raises(Exception) as exc_info_401:
        await invoke_with_retry(llm_401, [{"role": "user", "content": "hi"}])

    assert exc_info_401.value is plain_exc_401
    assert not isinstance(exc_info_401.value, LLMConfigurationError)

    plain_exc_500 = Exception("500 Server Error")
    llm_500 = MockLLM([plain_exc_500])

    with pytest.raises(Exception) as exc_info_500:
        await invoke_with_retry(llm_500, [{"role": "user", "content": "hi"}])

    assert exc_info_500.value is plain_exc_500


@pytest.mark.asyncio
async def test_rate_limit_with_used_tokens_retries_and_succeeds() -> None:
    msg = (
        "Rate limit reached for model `llama-3.3-70b-versatile` on tokens per minute (TPM): "
        "Limit 12000, Used 11401, Requested 1355. Please try again in 3.77s."
    )
    resp = _make_response(429)
    exc = groq.RateLimitError(msg, response=resp, body=None)
    llm = MockLLM([exc, "success_result"])
    publisher = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await invoke_with_retry(
            llm,
            [{"role": "user", "content": "hi"}],
            publisher=publisher,
            task_id="task-123",
        )

    assert result == "success_result"
    assert llm.call_count == 2
    mock_sleep.assert_awaited_once_with(3.77)
    publisher.emit.assert_awaited_once()
    assert publisher.emit.call_args.kwargs["payload"]["kind"] == "rate_limit_wait"
    assert publisher.emit.call_args.kwargs["payload"]["wait_seconds"] == 3.77


@pytest.mark.asyncio
async def test_retry_after_header_honored() -> None:
    resp = _make_response(429, headers={"retry-after": "15"})
    exc = groq.RateLimitError("Rate limit", response=resp, body=None)
    llm = MockLLM([exc, "success_header"])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

    assert result == "success_header"
    mock_sleep.assert_awaited_once_with(15.0)


@pytest.mark.asyncio
async def test_wait_cap_at_60_seconds() -> None:
    resp = _make_response(429, headers={"retry-after": "120"})
    exc = groq.RateLimitError("Rate limit", response=resp, body=None)
    llm = MockLLM([exc, "success_cap"])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

    assert result == "success_cap"
    mock_sleep.assert_awaited_once_with(60.0)


@pytest.mark.asyncio
async def test_rate_limit_exhaustion_raises() -> None:
    resp = _make_response(429)
    exc = groq.RateLimitError("Rate limit exceeded", response=resp, body=None)
    llm = MockLLM([exc] * 10)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(groq.RateLimitError):
            await invoke_with_retry(llm, [{"role": "user", "content": "hi"}])

    assert llm.call_count == 6


@pytest.mark.asyncio
async def test_tool_use_failed_corrective_retries_exactly_twice() -> None:
    body = {"error": {"message": "Failed to parse tool call", "code": "tool_use_failed"}}
    resp = _make_response(400)
    exc = groq.BadRequestError("Failed to parse tool call", response=resp, body=body)

    # Success on 2nd retry (3rd attempt)
    llm_succeeds = MockLLM([exc, exc, "success_after_corrective"])
    result = await invoke_with_retry(llm_succeeds, [{"role": "user", "content": "hi"}])
    assert result == "success_after_corrective"
    assert llm_succeeds.call_count == 3
    # Check corrective message was added
    assert len(llm_succeeds.messages_received[1]) == 2
    assert (
        "Your previous tool call did not match" in llm_succeeds.messages_received[1][-1]["content"]
    )

    # Fails 3 times in a row -> raises BadRequestError on 3rd attempt
    llm_fails = MockLLM([exc, exc, exc, exc])
    with pytest.raises(groq.BadRequestError):
        await invoke_with_retry(llm_fails, [{"role": "user", "content": "hi"}])
    assert llm_fails.call_count == 3
