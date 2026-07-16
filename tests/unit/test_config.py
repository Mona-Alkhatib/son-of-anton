import pytest
from pydantic import ValidationError

from oracle.config import Settings


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgres://x:y@localhost/z")
    monkeypatch.setenv("ORACLE_LOG_LEVEL", "DEBUG")

    s = Settings()

    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert s.database_url == "postgres://x:y@localhost/z"
    assert s.log_level == "DEBUG"
    assert s.default_model == "claude-sonnet-4-6"
    assert s.per_incident_budget_usd == 0.50


def test_settings_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings()
