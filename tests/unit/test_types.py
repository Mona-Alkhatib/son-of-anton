from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oracle.types import (
    ApprovalDecision,
    Caller,
    Citation,
    IncidentResponse,
    ProposedAction,
    RoutingDecision,
    SpecialistFindings,
)


def test_caller_round_trip() -> None:
    c = Caller(source="cli", identity="mona@laptop")
    dumped = c.model_dump_json()
    assert Caller.model_validate_json(dumped) == c


def test_caller_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        Caller(source="mail", identity="x")


def test_frozen_model_cannot_mutate() -> None:
    c = Citation(source_type="runbook", source_id="r1.md", snippet="hi", score=0.5)
    with pytest.raises(ValidationError):
        c.snippet = "changed"  # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Citation(
            source_type="runbook",
            source_id="r1.md",
            snippet="hi",
            score=0.5,
            bogus="nope",  # type: ignore[call-arg]
        )


def test_incident_response_defaults() -> None:
    r = IncidentResponse(
        answer_md="answer",
        citations=[],
        drafted_slack_post=None,
        drafted_actions=[],
        incident_id="INC-1",
        request_id="req-1",
    )
    assert r.drafted_slack_post is None
    assert r.drafted_actions == []


def test_routing_decision_confidence_bounds() -> None:
    ok = RoutingDecision(
        specialist="freshness", confidence=0.85, reasoning="r", hand_off_context={}
    )
    assert ok.confidence == 0.85
    with pytest.raises(ValidationError):
        RoutingDecision(specialist="freshness", confidence=1.5, reasoning="r", hand_off_context={})


def test_specialist_findings_with_action() -> None:
    a = ProposedAction(
        adapter="airflow",
        verb="clear_task",
        args={"dag_id": "d", "task_id": "t", "run_id": "r"},
        write=True,
        rationale="skipped run",
    )
    f = SpecialistFindings(
        specialist="freshness",
        root_cause_hypothesis="missed run",
        evidence=[],
        suggested_actions=[a],
    )
    assert f.suggested_actions[0].write is True


def test_approval_decision() -> None:
    d = ApprovalDecision(approved=True, decided_by="mona", decided_at=datetime.now(UTC), note=None)
    assert d.approved
