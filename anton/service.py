from __future__ import annotations

import uuid

from anton.llm import LLMGateway
from anton.prompts import load as load_prompt
from anton.retrieval.base import Retriever
from anton.types import Caller, IncidentResponse


class AntonService:
    def __init__(
        self,
        *,
        llm: LLMGateway,
        retriever: Retriever,
        prompt_name: str = "generic",
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._prompt_name = prompt_name

    async def ask(
        self,
        question: str,
        *,
        incident_id: str | None,
        caller: Caller,
    ) -> IncidentResponse:
        incident_id = incident_id or f"INC-{uuid.uuid4().hex[:8]}"

        hits = await self._retriever.search(question, top_k=0)
        context_block = (
            "\n".join(f"- {c.source_id}: {c.snippet}" for c in hits)
            if hits
            else "(no context available in phase 1)"
        )

        prompt = load_prompt(self._prompt_name)
        rendered = prompt.render(question=question, context=context_block)

        result = await self._llm.complete(
            rendered, extra_context={"incident_id": incident_id, "caller": caller.source}
        )

        return IncidentResponse(
            answer_md=result.text,
            citations=list(hits),
            drafted_slack_post=None,
            drafted_actions=[],
            incident_id=incident_id,
            request_id=result.request_id,
        )
