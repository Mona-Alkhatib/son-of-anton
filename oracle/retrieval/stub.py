from oracle.types import Citation


class StubRetriever:
    async def search(
        self,
        query: str,
        *,
        scope: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Citation]:
        return []
