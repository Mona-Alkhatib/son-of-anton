from typing import Protocol

from anton.types import Citation


class Retriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        scope: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Citation]: ...
