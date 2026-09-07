# Pending sign-off — CRITICAL hook gates hit during unattended `/goal` runs

`/goal`'s CRITICAL gates (`protect_never_touch`/`protect_hook_integrity`/
`protect_destructive`/`protect_decision_record_bypass`/`protect_push_safety`)
still require a human — that's the whole point of CRITICAL. When one fires
with nobody around to answer, the run doesn't stall: it logs the item here,
skips it, and keeps working the rest of the queue. Root `CLAUDE.md`'s
`/goal` section is where this behavior is defined.

Review this file when you're back. Each entry needs your yes/no (or a
correction) before the item gets acted on — nothing here has been applied.

## Format

```
### <date> — <hook> — <file/command>
**Wanted to:** <one line>
**Why:** <one line>
**Urgency:** <one line — does anything else wait on this>
**Status:** pending
```

## Entries

### 2026-09-08 — protect_push_safety — `git push -u origin develop`
**Wanted to:** Publish local commit `569cb9a` that allows the documented Codex author email in the shared push-safety hook.
**Why:** `AGENTS.md` requires `Codex <noreply@openai.com>`, while the active global hook still rejects that email and blocks the ordinary non-force push.
**Urgency:** The branch is one commit ahead of `origin/develop`; no other repository work depends on publishing it.
**Status:** pending
