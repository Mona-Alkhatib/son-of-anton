from typing import Any, ClassVar
from unittest.mock import AsyncMock, patch

import pytest

from oracle.llm import LLMGateway, LLMResult
from oracle.prompts import RenderedPrompt


@pytest.fixture
def rendered() -> RenderedPrompt:
    return RenderedPrompt(
        system="You are helpful.",
        user="Q: is water wet?",
        metadata={
            "prompt_name": "sample",
            "prompt_version": 1,
            "model": "claude-sonnet-4-6",
            "temperature": 0.2,
            "max_tokens": 128,
            "tools": [],
        },
    )


def _fake_litellm_response(text: str = "yes") -> Any:
    class Msg:
        content = text

    class Choice:
        message = Msg()

    class Usage:
        prompt_tokens = 40
        completion_tokens = 5
        cache_read_input_tokens = 10

    class Resp:
        id = "resp_abc"
        model = "claude-sonnet-4-6"
        choices: ClassVar[list[Choice]] = [Choice()]
        usage = Usage()

    return Resp()


@pytest.mark.asyncio
async def test_complete_returns_result_and_writes_audit(rendered: RenderedPrompt) -> None:
    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    with patch("oracle.llm.acompletion", AsyncMock(return_value=_fake_litellm_response())):
        result = await gw.complete(rendered)

    assert isinstance(result, LLMResult)
    assert result.text == "yes"
    assert result.tokens_in == 40
    assert result.tokens_out == 5
    assert result.cache_read is True
    assert result.request_id.startswith("resp_")
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_retries_on_rate_limit(rendered: RenderedPrompt) -> None:
    import litellm

    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    call = AsyncMock(
        side_effect=[
            litellm.exceptions.RateLimitError(
                "rl", llm_provider="anthropic", model="claude-sonnet-4-6"
            ),
            _fake_litellm_response(),
        ]
    )
    with patch("oracle.llm.acompletion", call):
        result = await gw.complete(rendered)

    assert result.text == "yes"
    assert call.await_count == 2


@pytest.mark.asyncio
async def test_complete_records_error_and_reraises(rendered: RenderedPrompt) -> None:
    import litellm

    audit = AsyncMock()
    gw = LLMGateway(audit_writer=audit)

    call = AsyncMock(
        side_effect=litellm.exceptions.APIError(
            status_code=500,
            message="boom",
            llm_provider="anthropic",
            model="claude-sonnet-4-6",
        )
    )
    with patch("oracle.llm.acompletion", call), pytest.raises(Exception):  # noqa: B017
        await gw.complete(rendered)

    audit.assert_awaited_once()
    args, kwargs = audit.await_args
    assert kwargs["error"] is not None or (args and args[-1] is not None)
