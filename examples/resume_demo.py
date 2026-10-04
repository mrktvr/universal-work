#!/usr/bin/env python3
"""Demonstrate a saved task resumed by a fresh worker using the real CLI.

Run from any directory: python /path/to/universal-work/examples/resume_demo.py
Python 3.10+, standard library only. Default execution writes only to a disposable
temporary directory and uses no network. --phase is internal to this example.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


WORKCTL = Path(__file__).resolve().parents[1] / "scripts" / "workctl.py"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(root, *args):
    # Structured arguments keep workspace paths and notes out of shell code.
    process = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(WORKCTL),
         "--db", str(root / "ledger.sqlite3"), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    require(process.returncode == 0,
            f"CLI {args[0]} failed: {process.stdout}\n{process.stderr}")
    response = json.loads(process.stdout)
    require(response.get("ok") is True, f"CLI {args[0]} returned {response}")
    print(f"  {args[0]}: {response.get('task', {}).get('state', 'ok')}", flush=True)
    return response


def prepare(root):
    workspace = root / "workspace"
    workspace.mkdir()
    write_json(workspace / "input.json", [2, 3, 5])
    # The acceptance contract is specified independently BEFORE output exists:
    # three inputs, with the manually established arithmetic 2 + 3 + 5 = 10.
    write_json(root / "task.json", {
        "goal": "Sum the three supplied integers and verify the exact result",
        "workspace": str(workspace),
        "criteria": [{"id": "exact-result", "type": "json_equals",
                      "path": "result.json", "pointer": "",
                      "expected": {"count": 3, "total": 10}}],
        "limits": {"max_steps": 10, "max_seconds": 120},
    })
    task_id = command(root, "new", "--spec", str(root / "task.json"))["task"]["id"]
    write_json(root / "task-id.json", task_id)
    command(root, "start", task_id)
    command(root, "checkpoint", task_id, "--note",
            "Input saved and contract fixed; next: generate result.json and verify.")
    command(root, "stop", task_id, "--reason", "Demonstration handoff to a fresh worker")


def resume(root):
    task_id = json.loads((root / "task-id.json").read_text(encoding="utf-8"))
    task = command(root, "show", task_id)["task"]
    require(task["state"] == "stopped" and task["steps"] == 1,
            "Saved stop/checkpoint state was not recovered")
    require(any(event["kind"] == "checkpoint" for event in task["recent_events"]),
            "Saved checkpoint is missing")
    workspace = root / "workspace"
    values = json.loads((workspace / "input.json").read_text(encoding="utf-8"))
    require(values == [2, 3, 5], "Saved inputs changed during handoff")
    require(not (workspace / "result.json").exists(), "Result was generated before resume")
    command(root, "resume", task_id)
    write_json(workspace / "result.json", {"count": len(values), "total": sum(values)})
    verified = command(root, "verify", task_id)
    require(verified["verification"]["passed"] is True, "Exact JSON check failed")
    finished = command(root, "finish", task_id)
    require(finished["task"]["state"] == "completed", "Task did not complete")
    saved = command(root, "show", task_id)["task"]
    require(saved["state"] == "completed" and saved["verification"]["passed"] is True,
            "Completed verification was not persisted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "resume"))
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.phase:
        if args.root is None:
            parser.error("--phase requires --root")
        (prepare if args.phase == "prepare" else resume)(args.root)
        return
    if args.root is not None:
        parser.error("--root is internal and requires --phase")
    with tempfile.TemporaryDirectory(prefix="universal-work-demo-") as temp:
        for phase in ("prepare", "resume"):
            print(f"Fresh worker: {phase}", flush=True)
            subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
                 "--phase", phase, "--root", temp], check=True, timeout=60,
            )
    print("PASS: resumed task completed with independently specified JSON criteria.")


if __name__ == "__main__":
    main()
