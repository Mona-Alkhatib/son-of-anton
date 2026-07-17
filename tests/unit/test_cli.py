from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from oracle.cli import app
from oracle.types import IncidentResponse

runner = CliRunner()


def _fake_response() -> IncidentResponse:
    return IncidentResponse(
        answer_md="short answer.",
        citations=[],
        drafted_slack_post=None,
        drafted_actions=[],
        incident_id="INC-x",
        request_id="req_1",
    )


def test_ask_prints_answer() -> None:
    svc = AsyncMock()
    svc.ask = AsyncMock(return_value=_fake_response())
    with (
        patch("oracle.cli.build_service", AsyncMock(return_value=(svc, None))),
        patch("oracle.cli.close_pool", AsyncMock()),
    ):
        r = runner.invoke(app, ["ask", "hi there"])

    assert r.exit_code == 0
    assert "short answer." in r.stdout


def test_ask_json_flag_emits_json() -> None:
    svc = AsyncMock()
    svc.ask = AsyncMock(return_value=_fake_response())
    with (
        patch("oracle.cli.build_service", AsyncMock(return_value=(svc, None))),
        patch("oracle.cli.close_pool", AsyncMock()),
    ):
        r = runner.invoke(app, ["ask", "hi", "--json"])

    assert r.exit_code == 0
    assert '"answer_md":"short answer."' in r.stdout
