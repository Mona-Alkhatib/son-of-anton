import pytest

from anton.retrieval.stub import StubRetriever


@pytest.mark.asyncio
async def test_stub_returns_empty() -> None:
    r = StubRetriever()
    out = await r.search("anything")
    assert out == []


@pytest.mark.asyncio
async def test_stub_honors_top_k_argument() -> None:
    r = StubRetriever()
    out = await r.search("anything", top_k=10)
    assert out == []
