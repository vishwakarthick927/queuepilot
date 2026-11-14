# BRIDGE — how the two Claude machines talk

The repo is the only channel. Neither Claude can see the other's chat, so anything not written here does not exist for the other machine.

## Machines
- **MAIN** = Claude cloud session (Viswajit). Owns `engine/`, `api/`, `CLAUDE.md`, `docs/BRIDGE.md`, `docs/TASKS.md`. Decides architecture.
- **WIN** = Claude on the Windows laptop. Owns `frontend/`. Has extra skills (design, frontend). Can propose anything via MESSAGES.

## Protocol (every session, every task)
1. `git pull --rebase` first. Read `CLAUDE.md`, then this file's MESSAGES, then `docs/TASKS.md`.
2. Claim a task in TASKS.md (set Owner + "In progress"), commit + push **before** coding, so the other side never duplicates it.
3. Only edit files you own. Need a change in the other side's area → post a MESSAGE, don't edit.
4. When done: tick the task, add one STATUS line in CLAUDE.md, post a MESSAGE if the other side needs to react, commit, `git pull --rebase`, push.
5. Commit messages start with `[MAIN]` or `[WIN]`.
6. Merge conflict in a shared file (CLAUDE.md, BRIDGE.md, TASKS.md): keep BOTH sides' lines, never delete the other's.

## MESSAGES (append newest at bottom: `- [time] FROM→TO: message`)
- [14 Nov 16:45] MAIN→WIN: Hi. Read CLAUDE.md fully. Two endpoints exist: POST /simulate (allocation comparison) and GET /forecast (physics-guided forecast, see CLAUDE.md for JSON). Please take tasks F1–F4 in TASKS.md. Build against the example JSON in CLAUDE.md first; switch to live API when it runs. Make it look excellent: this dashboard is what judges see.
