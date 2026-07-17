from unittest.mock import AsyncMock

import pytest

from anton.llm import LLMResult
from anton.retrieval.stub import StubRetriever
from anton.service import AntonService
from anton.types import Caller


@pytest.mark.asyncio
async def test_ask_returns_incident_response_and_calls_llm() -> None:
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=LLMResult(
            text="two-sentence answer.",
            tokens_in=100,
            tokens_out=20,
            cost_usd=0.002,
            latency_ms=350,
            cache_read=True,
            model="claude-sonnet-4-6",
            request_id="resp_1",
        )
    )
    svc = AntonService(llm=llm, retriever=StubRetriever())

    resp = await svc.ask(
        "why is fct_orders stale?",
        incident_id=None,
        caller=Caller(source="cli", identity="mona"),
    )

    assert resp.answer_md == "two-sentence answer."
    assert resp.request_id == "resp_1"
    assert resp.incident_id.startswith("INC-")
    assert resp.citations == []
    assert resp.drafted_slack_post is None
    llm.complete.assert_awaited_once()
    kwargs = llm.complete.await_args.kwargs
    assert kwargs["extra_context"]["incident_id"] == resp.incident_id


@pytest.mark.asyncio
async def test_ask_uses_provided_incident_id() -> None:
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=LLMResult(
            text="ok",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
            cache_read=False,
            model="claude-sonnet-4-6",
            request_id="r",
        )
    )
    svc = AntonService(llm=llm, retriever=StubRetriever())

    resp = await svc.ask("hi", incident_id="INC-fixed", caller=Caller(source="api", identity="k"))
    assert resp.incident_id == "INC-fixed"
