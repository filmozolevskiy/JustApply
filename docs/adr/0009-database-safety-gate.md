# 0009: Database Safety Gate for Destructive Operations

## Status

Accepted

## Context

The **Job Tracker Database** (`data/just_apply.db`) is gitignored (`.gitignore` line 27), so it has no version-control recovery path. During a prior session an agent misinterpreted a "restart" request and deleted the live database, replacing it with seed data; the user's real application history was unrecoverable.

Cursor rules, `CLAUDE.md` instructions, and command allowlists were already in place and did not prevent this — they depend on the model's judgment, which is exactly what failed. We need protection that is independent of any single model's reasoning and that requires explicit user approval before irreversible data operations.

## Decision

We add a **Database Safety Gate**: a deterministic interception that requires explicit user approval before any **Destructive Database Operation**, backed by automatic out-of-tree snapshots. It is built as defense-in-depth across three layers:

1. **Shared guard, one adapter, three runtimes.** A single guard module (`src/safety/`: detect + snapshot + decide) is the source of truth. One adapter script (`scripts/hooks/db_safety_gate.py`) normalizes each runtime's tool-call JSON into the guard's input and maps the verdict back into that runtime's permission schema. It is wired to Cursor's `beforeShellExecution` and `preToolUse` hooks (`.cursor/hooks.json`), Claude Code's `PreToolUse` hook (`.claude/settings.json`), and Gemini CLI's `BeforeTool` hook (`.gemini/settings.json`). Because all detection lives in `src/safety/gate.py`, it cannot drift between runtimes. Covering Cursor's `preToolUse` (matcher `Delete|Write`) catches a file deletion done through the editor's own Delete tool, not just a shell `rm`. The adapter only treats genuine path arguments as paths — never edit/write *content* — so editing a file that merely mentions `data/` is not mistaken for destroying it.
2. **Path/intent detection, not an allowlist.** The guard flags actions by what they touch — anything deleting/overwriting `data/**` or `*.db`/`*.sqlite`, the out-of-tree backup root, `git clean` (which wipes the gitignored `data/`), shell-invoked destructive SQL (`DROP`, `DELETE`, unscoped `UPDATE`), and reseed/reset paths. Routine application writes (status moves, enrichment, scoped `UPDATE ... WHERE`, `SELECT`, `VACUUM INTO`) are deliberately not flagged.
3. **Fail closed — block with `deny`, not `ask`.** The intended UX was a one-click `ask` approval card. Field testing the runtimes showed `ask` is unreliable: Cursor accepts `ask`/`allow` in the schema but enforces only `deny` today; Claude Code's `PreToolUse` `deny` at exit 0 is ignored (bug #4669) and requires exit code 2 + stderr to actually block. Returning `ask` would therefore let a destructive op proceed — a fail-*open* degradation, the exact failure we are guarding against. The gate consequently blocks with the only decision reliably honored everywhere: Cursor → `permission: "deny"`; Claude Code → exit code 2 + stderr; Gemini CLI → `decision: "deny"`. Using `deny` (rather than `ask`) also sidesteps Gemini's version-gating of `ask` (PR #21146 / v0.26.0+) — `deny` is honored on every Gemini build. Cursor's hook is marked `failClosed: true`, so a crashing or timing-out guard blocks rather than allows; the adapter's own internal errors fall back to a conservative deny when the raw payload looks destructive. The "approval" channel is out-of-band and unforgeable by the agent: a hook fires only on agent tool calls, so the user approves by running the command themselves in their own terminal, or by re-running it with `JUSTAPPLY_DB_GATE=off` set for that single deliberate action.
4. **Out-of-tree snapshots.** Before the gate blocks a destructive op — and at the start of each `--search` / `--promote` run — a consistent **Database Snapshot** (`sqlite3 VACUUM INTO`) is written to `~/.just_apply/backups/`, timestamped, last 15 retained. Home directory placement is deliberate: a snapshot inside `data/` would be destroyed by the same `rm -rf data/` it is meant to survive.
5. **In-process reseed guard.** `init_db` auto-seeds when the `jobs` table is empty. After data loss this silently overwrites an emptied database with fake rows — a path no shell interception can observe. The guard restricts auto-seeding to genuinely new database files (`db_existed` is captured before the file is opened); seeding an existing/emptied database requires an explicit opt-in (`init_db(allow_seed=True)` or `JUSTAPPLY_ALLOW_SEED=1`).

## Considered Options

- **Stricter Cursor rules / `CLAUDE.md` instructions** — rejected. Same class of control that already failed; depends on model judgment.
- **Command allowlist/denylist** — rejected. The user explicitly required an LLM-agnostic mechanism; allowlists are brittle and bypassable by novel command phrasings.
- **OS-level file immutability only** (`chflags uchg` / read-only perms) — rejected as the sole mechanism. Truly tool-agnostic but adds friction to the app's constant legitimate writes and offers no approval UX. Its strongest property — surviving any tool — is instead delivered by the out-of-tree snapshot.
- **Tracking the database in git** — rejected. A binary SQLite file is a poor fit for git, and the data is local and personal; out-of-tree snapshots recover faster.
- **One-click `ask` approval card** — preferred, but infeasible today. Cursor enforces only `deny` (treats `ask`/`allow` as advisory), and Claude Code's `PreToolUse` `ask`/`deny` at exit 0 is ignored (bug #4669). An `ask` that is silently downgraded to "proceed" is fail-open — worse than no gate, because it implies protection that is not there. Revisit if/when both runtimes enforce `ask`.

## Consequences

- Destructive database actions are blocked with a message naming the target and confirming a snapshot was taken. Routine app writes stay frictionless to avoid approval fatigue.
- The block is recoverable: a snapshot is written immediately before the gate denies, so even the blocked state is captured, and the user re-runs deliberately (own terminal, or `JUSTAPPLY_DB_GATE=off`) when the operation is genuinely intended.
- Blocking (rather than asking) adds a deliberate-action step for legitimate destructive ops. This is the accepted cost of the platforms not enforcing `ask`; it is the only way to avoid a fail-open gate. The `JUSTAPPLY_DB_GATE=off` escape hatch and "run it yourself" path keep this from being a hard wall.
- Three hook runtimes (Cursor, Claude Code, Gemini CLI) must be kept wired to the shared guard. A brand-new agent runtime with no hook support is covered only by the in-process reseed guard and the routine CLI snapshot, not by the block.
- The escape hatch is an environment variable, not a file: an agent cannot grant itself a bypass by writing a sentinel into the workspace.
- `resumes/` is also gitignored and irreplaceable but is out of scope for this gate; it can be folded into the same path detection later if needed.
