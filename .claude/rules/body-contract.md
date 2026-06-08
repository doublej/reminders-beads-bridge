---
paths:
  - "src/reminders_bridge/body.py"
---

# Editing body.py — the reminder-body contract

`body.py` owns every reminder-body string concern. It is the most fragile module
in the repo: a subtle change silently corrupts user data (`<bb:notes>`) or
triggers tamper-recovery loops. There is no unit test — the contract below *is*
the test.

## Invariants

- The body has exactly these blocks, in order: optional `<bb:restored>` banner,
  `<bb:meta>`, `<bb:desc>`, `<bb:notes>`. Only `<bb:notes>` is user-owned;
  everything else is rewritten from bead state every sync.
- **Round-trip is the law:** `parse(compose(bead, notes))` must recover the same
  `notes`, and `compose` must be idempotent — composing twice against the same
  bead + notes yields byte-identical output (a clean sync logs zero changes).
- Tamper = `<bb:meta>` or `<bb:desc>` diverging from the bead, or a required tag
  missing. On tamper: rewrite from bead state, **preserve `<bb:notes>`**, prepend
  the `<bb:restored>` banner. The banner itself is not tamper — it drops on the
  next clean sync.
- If `<bb:notes>` is unparseable, notes become empty — **never raise**. Losing
  the banner or failing a parse must never crash the sync.

## Before you commit a body.py change — verify by hand

1. Compose against a sample bead → parse it back → assert notes survive.
2. Compose the same bead+notes **twice** → assert byte-identical (idempotence).
3. Simulate tamper (mutate the composed `<bb:meta>`) → re-compose → assert the
   `<bb:restored>` banner appears and `<bb:notes>` is intact.
4. Run `rbridge sync` against a real project, then `rbridge lint` → expect clean.

## Adding a tag or a status — multi-file change, do them together

- New `<bb:*>` tag: update the parser **and** `rbridge lint` codes **and**
  `CLAUDE.md` (Body syntax) **and** `GLOSSARY.md` (tags table). A tag the parser
  emits but doesn't parse back breaks the round-trip.
- New bead status: add to `VALID_STATUSES`, and to the env-var docs in
  `docs/REFERENCE.md` / README.

## Related

- `CLAUDE.md` → "Body syntax + tamper" · `GLOSSARY.md` → body tags · lint codes.
