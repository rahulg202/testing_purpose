"""Prompt management — versioned YAML prompts loaded at startup.

MVP: prompts are YAML files in git, version-pinned per the sprint plan §5.
Post-MVP: a registry with approval workflow.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger("atheria_llm.prompts")


@dataclass(frozen=True)
class PromptTemplate:
    """A versioned prompt template."""

    name: str
    version: str
    system_prompt: str
    user_template: str
    output_schema: dict[str, Any] | None = None
    model_id: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    content_hash: str = ""

    def render_user(self, **kwargs: Any) -> str:
        """Render the user template with variables."""
        return self.user_template.format(**kwargs)


class PromptRegistry:
    """Registry of versioned prompt templates.

    Loads from a directory of YAML files. Each file represents one prompt.
    """

    def __init__(self, prompts_dir: str | Path | None = None):
        self._prompts: dict[str, PromptTemplate] = {}
        if prompts_dir:
            self.load_directory(Path(prompts_dir))

    def load_directory(self, path: Path) -> None:
        """Load all .yaml/.yml prompt files from a directory."""
        if not path.exists():
            logger.warning("prompts_dir_not_found", path=str(path))
            return

        for file in sorted(path.glob("*.y*ml")):
            self.load_file(file)

    def load_file(self, path: Path) -> None:
        """Load a single prompt YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                logger.warning("invalid_prompt_file", path=str(path))
                return

            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

            template = PromptTemplate(
                name=data["name"],
                version=data["version"],
                system_prompt=data.get("system_prompt", ""),
                user_template=data.get("user_template", ""),
                output_schema=data.get("output_schema"),
                model_id=data.get("model_id"),
                max_tokens=data.get("max_tokens", 4096),
                temperature=data.get("temperature", 0.0),
                content_hash=content_hash,
            )

            self._prompts[template.name] = template
            logger.info(
                "prompt_loaded",
                name=template.name,
                version=template.version,
                hash=content_hash,
            )
        except Exception as exc:
            logger.error("prompt_load_failed", path=str(path), error=str(exc))

    def get(self, name: str) -> PromptTemplate | None:
        """Get a prompt template by name."""
        return self._prompts.get(name)

    def get_or_raise(self, name: str) -> PromptTemplate:
        """Get a prompt template or raise if not found."""
        template = self._prompts.get(name)
        if not template:
            raise KeyError(f"Prompt template '{name}' not found in registry")
        return template

    @property
    def loaded_prompts(self) -> list[str]:
        """List all loaded prompt names."""
        return list(self._prompts.keys())
