from pathlib import Path

import pytest
from pydantic_core import ValidationError

from anton.prompts import load


@pytest.fixture
def prompt_root(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "sample.v1.yaml").write_text(
        """
name: sample
version: 1
model: claude-sonnet-4-6
temperature: 0.2
max_tokens: 1024
system: |
  You are a helpful assistant.
user_template: |
  Q: {question}
tools: []
context_recipe:
  top_k: 5
""".strip()
    )
    (root / "sample.v2.yaml").write_text(
        """
name: sample
version: 2
model: claude-sonnet-4-6
temperature: 0.1
max_tokens: 2048
system: |
  You are a helpful assistant (v2).
user_template: |
  Question: {question}
tools: []
context_recipe: {}
""".strip()
    )
    return root


def test_load_latest_version(prompt_root: Path) -> None:
    p = load("sample", root=prompt_root)
    assert p.version == 2
    assert p.temperature == 0.1


def test_load_specific_version(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    assert p.version == 1
    assert "helpful assistant." in p.system


def test_load_unknown_prompt(prompt_root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load("nope", root=prompt_root)


def test_render_substitutes_vars(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    r = p.render(question="what feeds fct_orders?")
    assert "Q: what feeds fct_orders?" in r.user
    assert r.metadata["prompt_name"] == "sample"
    assert r.metadata["prompt_version"] == 1


def test_render_missing_var_raises(prompt_root: Path) -> None:
    p = load("sample", version=1, root=prompt_root)
    with pytest.raises(KeyError):
        p.render()


def test_prompt_frozen(prompt_root: Path) -> None:
    p = load("sample", root=prompt_root)
    with pytest.raises(ValidationError):
        p.temperature = 0.9  # type: ignore[misc]
