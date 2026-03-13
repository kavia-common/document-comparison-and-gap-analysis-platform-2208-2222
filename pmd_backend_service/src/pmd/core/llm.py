from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMProvider(Protocol):
    """Protocol for LLM providers used to generate PMD text."""

    # PUBLIC_INTERFACE
    def generate_section(self, *, prompt: str) -> str:
        """Generate text for a section.

        Args:
            prompt: Prompt including template title and relevant matched summaries.

        Returns:
            Generated text.
        """


@dataclass(frozen=True)
class MockLLMProvider:
    """Deterministic mock provider for development and CI.

    This avoids external network calls and provides stable outputs.
    """

    name: str = "mock"

    # PUBLIC_INTERFACE
    def generate_section(self, *, prompt: str) -> str:
        """Return a simple deterministic transformation of the prompt."""
        trimmed = (prompt or "").strip()
        if len(trimmed) > 800:
            trimmed = trimmed[:800] + "..."
        return (
            "PMD SECTION (mock)\n"
            "------------------\n"
            f"{trimmed}\n\n"
            "NOTE: Configure a real provider to replace this mock output."
        )


# PUBLIC_INTERFACE
def get_llm_provider(name: str) -> LLMProvider:
    """Factory for LLM providers.

    Args:
        name: Provider name. Currently supports 'mock'.

    Returns:
        LLMProvider instance.

    Raises:
        ValueError: If provider is unknown.
    """
    normalized = (name or "").strip().lower()
    if normalized in {"mock", ""}:
        return MockLLMProvider()
    raise ValueError(
        f"Unknown LLM provider '{name}'. Only 'mock' is currently implemented."
    )
