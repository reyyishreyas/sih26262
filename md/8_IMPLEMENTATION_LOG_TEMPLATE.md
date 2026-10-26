# docs/IMPLEMENTATION_LOG.md  (copy this file to that path)

**Purpose:** the single place where every decision and every piece of implementation work is recorded, by humans and AI agents. Bugs and errors go in `docs/BUG_LOG.md`, not here (link between them by ID).

## Rules
1. **Append-only.** Add new entries at the **top of the Entries section** (newest first). Never edit or delete an old entry. To correct one, add a new entry that says `Supersedes: IMPL-0007` / `Amends: DEC-0003`.
2. **One entry per task or decision**, written when the work is finished (or when the decision is made), before you end your session.
3. **Truthful.** Status words only: Verified, Implemented, Tested, Partial, Proposed, Unverified, Blocked, Deprecated. Paste real command output summaries; never write "tests pass" without counts. Say "not run" when you did not run it.
4. **No secrets, tokens, real personal data or document contents.** Refer to files by path and hash.
5. Decisions that need a human (see Essentials: approval gates) are logged as `Proposed` with `Owner: <human>` until approved; do not implement them first.
6. IDs: `DEC-0001…` decisions, `IMPL-0001…` implementation entries, `BUG-0001…` live in the bug log. Use the next unused number.

## Index (keep updated; one line per entry)
| ID | Date | Type | Title | Status | Task / FR | Agent or author |
|---|---|---|---|---|---|---|
| DEC-0001 | 2026-10-26 | Decision | Database host = Supabase (managed Postgres only, own JWT auth) | Proposed→Accepted | addendum 7 | Project lead |
| DEC-0002 | 2026-10-26 | Decision | LLM chain Gemini → OpenRouter → more → deterministic; off by default | Accepted | addendum 7 | Project lead |
| DEC-0003 | 2026-10-26 | Decision | Regulatory values default to Unverified/advisory | Accepted | PRD §0 | Project lead |

## Entry template: decision
```
### DEC-XXXX — <short title>
- Date / author (human or agent name + model):
- Status: Proposed | Accepted | Rejected | Superseded by DEC-XXXX
- Context (what forced the decision; link PRD/FR/OPEN IDs and sources):
- Options considered (A/B/C with one-line pros/cons):
- Decision:
- Rationale:
- Consequences (what it changes, what it blocks, follow-ups):
- Approval needed from / approved by / date:
- Evidence (links to commits, tests, official source IDs):
```

## Entry template: implementation
```
### IMPL-XXXX — <short title>
- Date / agent (name + model) / branch / commit hash:
- Task ID (AGENT-xx or plan item) and PRD IDs (FR-xx):
- Goal:
- What existed before (files/symbols reused, or "search found nothing"):
- What I did (bullet list; plain language):
- Files changed (path — reason):
- Migrations / API / config / rule-file changes:
- Decisions made (link DEC-XXXX; any new decision must also get its own DEC entry):
- Permission and audit effects:
- Verification: exact commands + results (counts, skips and why). Anything not run = "not run".
- Status per requirement touched (status words):
- Limitations / assumptions / manual steps:
- Related bugs (BUG-XXXX):
- Open questions for a human:
- Next suggested task:
```

## Entries (newest first)
<!-- add entries below this line -->
