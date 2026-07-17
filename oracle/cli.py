from __future__ import annotations

import asyncio
import sys

import asyncpg
import typer
from rich.console import Console

from oracle.audit import AuditWriter
from oracle.db import close_pool, pool
from oracle.llm import LLMGateway
from oracle.retrieval.stub import StubRetriever
from oracle.service import OracleService
from oracle.types import Caller

app = typer.Typer(help="On-Call Oracle CLI (phase 1)")
console = Console()


async def build_service() -> tuple[OracleService, asyncpg.Pool]:
    """Async factory: opens the pool and wires the service on the current loop."""
    p = await pool()
    writer = AuditWriter(pool=p)
    gateway = LLMGateway(audit_writer=writer.as_gateway_callable())
    svc = OracleService(llm=gateway, retriever=StubRetriever())
    return svc, p


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question for the Oracle"),
    incident_id: str | None = typer.Option(None, "--incident-id"),
    json_out: bool = typer.Option(False, "--json"),
    stream: bool = typer.Option(False, "--stream"),
) -> None:
    if stream:
        console.print("[yellow]streaming lands in phase 3; ignoring --stream.[/yellow]")

    async def _work() -> int:
        try:
            svc, _ = await build_service()
            resp = await svc.ask(
                question,
                incident_id=incident_id,
                caller=Caller(source="cli", identity="local"),
            )
            if json_out:
                sys.stdout.write(resp.model_dump_json())
                sys.stdout.write("\n")
            else:
                console.print(resp.answer_md)
            return 0
        except Exception as exc:
            console.print(f"[red]error:[/red] {exc}")
            return 1
        finally:
            await close_pool()

    raise typer.Exit(asyncio.run(_work()))


@app.command("audit-tail")
def audit_tail(limit: int = typer.Option(10, "--limit")) -> None:
    async def _work() -> int:
        try:
            p = await pool()
            rows = await p.fetch(
                "select request_id, prompt_name, model, tokens_in, tokens_out, "
                "cost_usd, latency_ms, cache_read, error, created_at "
                "from audit_llm_calls order by created_at desc limit $1",
                limit,
            )
            for row in rows:
                console.print(dict(row))
            return 0
        finally:
            await close_pool()

    raise typer.Exit(asyncio.run(_work()))


if __name__ == "__main__":
    app()
