"""Regulatory knowledge / extraction-helper adapter contract.

The AI layer may suggest field values, discrepancies and cited answers. It may not
produce a compliance verdict: that is the rule engine's job, over verified inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Citation:
    source_id: str
    section: str
    quote: str


@dataclass
class GroundedAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    insufficient_evidence: bool = False
    simulated: bool = True


class LLMAdapter(Protocol):
    def answer(self, *, question: str, context: list[str]) -> GroundedAnswer:
        ...
