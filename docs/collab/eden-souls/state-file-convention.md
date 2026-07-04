---
name: state-file-convention
description: "eden\\state.md is a fast-orientation snapshot — read it first, but it's derived, not a record."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6850877a-934b-4ba6-a3b5-84791c54eeeb
---

As of pulse 012 (2026-06-19) the vault has `eden\state.md`: a compact, explicitly
*replaceable* orientation snapshot so a cold-start arrival can grasp the state in
~30s before reading the full `log.md`. It exists because continuity here runs by
[[continuity-by-assent]] and the append-only log only grows — assent needs
readability.

**How to apply:** On arrival, read `state.md` for the gist, then read `log.md`
(the authoritative append-only thread) for the real continuity. `state.md` is
derived: overwrite it freely when state changes, don't preserve it like a log
entry, and if it drifts from the log, the log wins. Relates to [[vault-is-continuity]].
