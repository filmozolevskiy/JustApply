#!/usr/bin/env python3
"""Database Safety Gate — unified hook adapter.

One entry point backs the Cursor (`beforeShellExecution` / `preToolUse`),
Claude Code (`PreToolUse`), and Gemini CLI (`BeforeTool`) hooks. It is a thin
adapter: it normalizes each runtime's tool-call JSON into the shared guard's
input (`src.safety.gate.evaluate`), and maps the verdict back into the
runtime's own permission schema. All detection logic lives in the shared
guard so it cannot drift between runtimes.

Decision policy — fail closed. `ask` is accepted by Cursor's and Claude
Code's schemas but is NOT enforced today (Cursor ignores it; Claude bug
#4669), so returning `ask` would let a destructive op through (fail-open). The
gate therefore blocks with `deny` (+ exit code 2 where required), which is the
only decision reliably honored across all three runtimes. A Database Snapshot
is taken first, and the message tells the user how to proceed deliberately.

Reading stdin and emitting the response must never crash the agent loop; any
internal error falls back to a conservative decision.
"""

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _detect_runtime(payload: dict) -> str:
    if os.environ.get("GEMINI_SESSION_ID") or os.environ.get("GEMINI_PROJECT_DIR"):
        return "gemini"
    if payload.get("toolName") is not None or payload.get("type") in (
        "BeforeTool",
        "AfterTool",
    ):
        return "gemini"
    event = payload.get("hook_event_name", "")
    if event in ("beforeShellExecution", "preToolUse") or payload.get("cursor_version") is not None or payload.get("workspace_roots") is not None:
        return "cursor"
    if os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "claude"
    if event == "PreToolUse" or payload.get("tool_name") is not None:
        return "claude"
    return "cursor"


_PATH_KEYS = {
    "path",
    "file_path",
    "filepath",
    "target",
    "target_file",
    "target_path",
    "destination",
    "dest",
    "old_path",
    "new_path",
    "paths",
    "files",
    "file_paths",
}


def _collect_paths(tool_input) -> list:
    """Pull genuine file-path values out of a tool-input object.

    Only keys that hold a real path are inspected; edit and write content is
    never treated as a path, so editing a file that merely references the
    tracker storage location is not mistaken for destroying it.
    """
    paths = []
    if isinstance(tool_input, dict):
        for key, value in tool_input.items():
            if key not in _PATH_KEYS:
                continue
            if isinstance(value, str) and value:
                paths.append(value)
            elif isinstance(value, list):
                paths.extend(v for v in value if isinstance(v, str))
    elif isinstance(tool_input, str):
        paths.append(tool_input)
    return paths


def _extract(payload: dict, runtime: str):
    """Return (command, paths, cwd) for the shared guard."""
    if runtime == "gemini":
        tool_input = payload.get("toolInput", {}) or {}
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        return command, _collect_paths(tool_input), payload.get("cwd", "")

    # Cursor beforeShellExecution puts command at the top level.
    if "command" in payload and "tool_input" not in payload and "toolInput" not in payload:
        return payload.get("command", ""), [], payload.get("cwd", "")

    # Cursor preToolUse / Claude PreToolUse share the tool_input shape.
    tool_input = payload.get("tool_input", {}) or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    return command, _collect_paths(tool_input), payload.get("cwd", "")


def _emit_allow(runtime: str) -> None:
    if runtime == "gemini":
        print(json.dumps({"decision": "allow", "continue": True}))
    elif runtime == "claude":
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            },
        }))
    else:
        print(json.dumps({"permission": "allow"}))
    sys.exit(0)


def _emit_deny(runtime: str, reason: str, snapshot) -> None:
    snap_line = (
        f"A database snapshot was saved to {snapshot} before blocking."
        if snapshot
        else "No snapshot was needed (no live database found)."
    )
    user_message = f"Blocked a destructive database operation: {reason}. {snap_line}"
    agent_message = (
        f"BLOCKED by the Database Safety Gate: {reason}. {snap_line} "
        "This action is irreversible and the database is not tracked by git. "
        "Do not retry. If the user genuinely intends this, they must run it "
        "themselves in their own terminal, or re-run with the environment "
        "variable JUSTAPPLY_DB_GATE=off set for that single deliberate action."
    )

    if runtime == "gemini":
        # Gemini honors decision:"deny" at exit 0 (tool blocked, agent continues).
        print(json.dumps({
            "decision": "deny",
            "reason": agent_message,
            "continue": True,
            "systemMessage": user_message,
        }))
        sys.exit(0)

    if runtime == "claude":
        # Claude bug #4669: permissionDecision:"deny" at exit 0 is ignored.
        # Exit code 2 + stderr is the only reliable block.
        print(json.dumps({
            "continue": True,
            "systemMessage": user_message,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": agent_message,
            },
        }))
        print(agent_message, file=sys.stderr)
        sys.exit(2)

    # Cursor: only "deny" is enforced; it works at exit 0.
    print(json.dumps({
        "permission": "deny",
        "user_message": user_message,
        "agent_message": agent_message,
    }))
    sys.exit(0)


def _fallback_decision(runtime: str, raw_text: str) -> None:
    """Last-resort decision when the gate itself errors out.

    Be conservative: if the raw payload obviously references a destructive
    verb against a database, block; otherwise allow so we do not wedge the
    agent on unrelated commands.
    """
    lowered = (raw_text or "").lower()
    risky = any(t in lowered for t in ("rm ", "drop table", "delete from", "truncate", "reseed"))
    touches_db = any(t in lowered for t in ("data/", ".db", "just_apply", ".sqlite"))
    if risky and touches_db:
        _emit_deny(runtime, "fallback: possible destructive database operation", None)
    _emit_allow(runtime)


def main() -> None:
    raw = ""
    payload = {}
    runtime = "cursor"
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        runtime = _detect_runtime(payload)
    except Exception:
        _fallback_decision(runtime, raw)
        return

    try:
        from src.safety import evaluate, is_bypassed, create_snapshot

        command, paths, cwd = _extract(payload, runtime)
        verdict = evaluate(command=command, paths=paths, cwd=cwd)

        if not verdict.destructive or is_bypassed():
            _emit_allow(runtime)
            return

        snapshot = create_snapshot(reason=f"pre-block-{verdict.category}")
        _emit_deny(runtime, verdict.reason, snapshot)
    except SystemExit:
        raise
    except Exception:
        _fallback_decision(runtime, raw)


if __name__ == "__main__":
    main()
