"""Mock LLM adapter.

It refuses to answer without context and never invents a citation. The prototype does
not ship a working regulatory assistant; this exists so the interface is real and the
UI can be built against it.
"""

from __future__ import annotations

from .base import GroundedAnswer


class MockLLMAdapter:
    simulated = True

    def answer(self, *, question: str, context: list[str]) -> GroundedAnswer:
        if not context:
            return GroundedAnswer(
                answer=(
                    "No approved source passage was supplied, so no answer can be "
                    "grounded. This is a mock adapter."
                ),
                insufficient_evidence=True,
                simulated=True,
            )
        return GroundedAnswer(
            answer=(
                "Mock response. A production adapter would answer only from the "
                "supplied approved passages and cite them."
            ),
            citations=[],
            insufficient_evidence=True,
            simulated=True,
        )
