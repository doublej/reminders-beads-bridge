---
paths:
  - "src/reminders_bridge/mailbox.py"
  - "src/reminders_bridge/navigation.py"
  - "src/reminders_bridge/mirror.py"
  - "src/reminders_bridge/sandbox.py"
  - "src/reminders_bridge/prime.py"
  - "src/reminders_bridge/primer.md"
  - "docs/AGENT.md"
---

# Editing the voice lane — split readers, route instructions correctly

The voice exchange has **three agents reading three different surfaces.** The
recurring bug is writing an instruction into the surface its intended reader
never sees, so it silently does nothing. Before changing anything here, know who
reads what:

| Surface | Reader | Carries |
|---|---|---|
| `rbridge prime` → `primer.md` | **project agent** (Claude Code) | how to *author* a brief + open a mailbox |
| the **brief** (in `_rb_voice_<slug>`) | **voice agent** | per-exchange content + the file map |
| `!_rb_readme` → `docs/AGENT.md` | **voice agent** (acting inside Reminders) | standing directive incl. `fetch:`/`grep:`/`tree:` mechanics |

**The voice agent never reads `primer.md`.** So:
- A *runtime* rule for the voice agent (how it forms a `fetch:`, how it speaks) →
  put it in `docs/AGENT.md` or have the project agent embed it in the brief.
- An *authoring* rule (what the project agent should put in the brief) → `primer.md`.
- Per-exchange data (the handle ↔ path map) → the brief.

Keep `primer.md`, `docs/AGENT.md`, `docs/REFERENCE.md` (vocabulary), and
`GLOSSARY.md` consistent on the three role labels and surface terms.

## Speech is lossy for identifiers

Transcription corrupts machine identifiers both ways (TTS reads underscores/paths
as noise; STT never emits underscores and mangles dots/dashes/casing/proper
nouns). The rule, split across surfaces:
- Authoring (`primer.md`): spell identifiers out in spoken prose; give pullable
  files a speakable handle paired with the exact path in the brief's map.
- Voice-agent runtime (`docs/AGENT.md`): never write a heard path into a `fetch:`
  — use the exact path from the brief's map; fall back to `grep:` for fuzzy refs.

## File-navigation root

Nav serves requests only when the mailbox has a real `source_cwd` (the repo
root, set by `--cwd` at open time). Empty root ⇒ `navigation._root()` returns
`None` ⇒ requests silently ignored. `open_mailbox` self-heals an empty root from
`os.getcwd()` on re-open; `rbridge doctor` shows `nav=on/off root=…` per mailbox.
Keep nav reads sandboxed to the root (no dotfiles, secrets, or escapes).

## Defensive boundary

`projects_list.apply_hides()` must keep skipping voice lists
(`mailbox.is_voice_list_name()`) so the project-hide path can never delete one.

## Related

- `GLOSSARY.md` → "Voice exchange" + "Surfaces" · `docs/REFERENCE.md` → voice flow.
