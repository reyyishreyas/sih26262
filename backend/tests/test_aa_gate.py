"""The "AA" gate: SHC/SAC opens only on a deficiency or negative outcome
(Phase 1.7).

PRD FR-10 ("Open SAC/SHC only on deficiency or negative outcome", T2.3)
and §6 pattern note: "SCR+EVC+AA — Scrutiny, EVC, then SAC/SHC only if
earlier outcome has deficiencies ('AA' = as applicable)."

The route patterns already mark the ``shc`` stage ``when: if_deficiencies``
(task 1.2), but nothing answered *whether that gate is open* for a case.
This adds that answer as advisory configuration (`table_2_3.aa_gate`) plus
a service lookup, like the 1.5/1.6 tasks.

Safety rules honoured here:
- **Missing/undecided data is never a guessed open or closed.** If the
  scrutiny result is not yet recorded, the gate answers ``needs_review``
  (Master Prompt §2 rule 4) — a gate must not silently open or shut.
- Advisory only (DEC-0003): this returns ``open``/``closed``/``needs_review``
  for a screen or the stage graph to consult; it does not itself open a
  stage, transition a case, or block anything.
- No invented regulation: the gate cites FR-10 / T2.3 as its source, and
  the vocabulary it understands ("nil_deficiency" / "deficiency") comes
  from PRD FR-14's own wording, not a guess.
"""

from __future__ import annotations

from app.services import routing

NIL = "nil_deficiency"  # FR-14's clean result
DEFICIENCY = "deficiency"  # FR-14's negative result


def test_the_aa_gate_is_configured_and_advisory():
    gate = routing.aa_gate()
    assert gate["status"] == "unverified"
    assert gate["advisory_only"] is True


def test_the_gate_points_at_the_fr_it_came_from():
    assert "FR-10" in routing.aa_gate()["source"]


def test_a_clean_scrutiny_result_keeps_the_gate_closed():
    """Nil Deficiency and no open deficiency → SHC is not due (FR-10)."""
    assert (
        routing.aa_stage_is_due(scrutiny_result=NIL, deficiencies_remaining=0)
        == "closed"
    )


def test_a_deficiency_opens_the_gate_even_with_a_clean_result():
    """An open deficiency is enough on its own — the two conditions are OR'd."""
    assert (
        routing.aa_stage_is_due(scrutiny_result=NIL, deficiencies_remaining=2)
        == "open"
    )


def test_a_negative_scrutiny_result_opens_the_gate():
    """FR-10: 'deficiency **or** negative outcome' — the result alone opens it."""
    assert (
        routing.aa_stage_is_due(scrutiny_result=DEFICIENCY, deficiencies_remaining=0)
        == "open"
    )


def test_an_undecided_result_is_never_a_guessed_open_or_closed():
    """Rule 4: missing/uncertain data is 'needs review', never a guessed pass."""
    assert (
        routing.aa_stage_is_due(scrutiny_result=None, deficiencies_remaining=0)
        == "needs_review"
    )
    assert (
        routing.aa_stage_is_due(scrutiny_result=None, deficiencies_remaining=3)
        == "needs_review"
    )


def test_an_unrecognised_result_is_treated_as_uncertain_not_as_a_pass():
    """A result outside the configured vocabulary must not be read as clean."""
    assert (
        routing.aa_stage_is_due(scrutiny_result="something_else", deficiencies_remaining=0)
        == "needs_review"
    )


def test_the_scrutiny_result_vocabulary_comes_from_the_gate_config():
    """The words the gate understands are data, not hard-coded assumptions."""
    known = routing.aa_gate()["scrutiny_results"]
    assert NIL in known["clean"]
    assert DEFICIENCY in known["negative"]
