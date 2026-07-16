from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "prompts"


class RenderedPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    system: str
    user: str
    metadata: dict[str, Any]


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: int
    model: str
    temperature: float = 0.2
    max_tokens: int = 2048
    system: str
    user_template: str
    tools: list[str] = Field(default_factory=list)
    few_shots_path: str | None = None
    context_recipe: dict[str, Any] = Field(default_factory=dict)

    def render(self, **variables: Any) -> RenderedPrompt:
        try:
            user = self.user_template.format(**variables)
        except KeyError as missing:
            raise KeyError(
                f"prompt {self.name}@v{self.version} missing template var: {missing}"
            ) from missing
        metadata = {
            "prompt_name": self.name,
            "prompt_version": self.version,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": list(self.tools),
        }
        return RenderedPrompt(system=self.system, user=user, metadata=metadata)


def _resolve_root(root: Path | None) -> Path:
    return root if root is not None else _DEFAULT_ROOT


def load(
    name: str,
    version: int | Literal["latest"] = "latest",
    *,
    root: Path | None = None,
) -> Prompt:
    base = _resolve_root(root)
    if version == "latest":
        candidates = sorted(
            base.glob(f"{name}.v*.yaml"),
            key=lambda p: int(p.stem.split(".v")[-1]),
        )
        if not candidates:
            raise FileNotFoundError(f"no prompt named {name!r} under {base}")
        path = candidates[-1]
    else:
        path = base / f"{name}.v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"prompt {name}@v{version} not found at {path}")

    data = yaml.safe_load(path.read_text())
    return Prompt.model_validate(data)
