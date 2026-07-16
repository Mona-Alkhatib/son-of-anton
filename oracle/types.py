from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Specialist = Literal["freshness", "dag_failure", "schema_drift", "general"]
CallerSource = Literal["api", "cli", "ui", "slack"]


class OracleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Caller(OracleModel):
    source: CallerSource
    identity: str


class Citation(OracleModel):
    source_type: str
    source_id: str
    snippet: str
    score: float | None = None


class ProposedAction(OracleModel):
    adapter: str
    verb: str
    args: dict[str, Any]
    write: bool
    rationale: str


class ToolError(OracleModel):
    tool_name: str
    message: str
    retriable: bool


class RoutingDecision(OracleModel):
    specialist: Specialist
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    hand_off_context: dict[str, Any]


class SpecialistFindings(OracleModel):
    specialist: Specialist
    root_cause_hypothesis: str
    evidence: list[Citation]
    suggested_actions: list[ProposedAction]


class IncidentResponse(OracleModel):
    answer_md: str
    citations: list[Citation]
    drafted_slack_post: str | None
    drafted_actions: list[ProposedAction]
    incident_id: str
    request_id: str


class ApprovalDecision(OracleModel):
    approved: bool
    decided_by: str
    decided_at: datetime
    note: str | None
