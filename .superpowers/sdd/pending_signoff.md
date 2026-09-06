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

(none yet)
