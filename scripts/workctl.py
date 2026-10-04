#!/usr/bin/env python3
"""Deterministic local work ledger; Python 3.10+, standard library only.

This records decisions and verifies files. It does not execute actions, enforce
tool permissions, sandbox programs, or run a background worker. Claims are
advisory. The database and workspace must be on trusted local storage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import stat
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext


SPEC_LIMIT = 1024 * 1024
FILE_LIMIT = 64 * 1024 * 1024
APP_ID = 0x55574C31
SCHEMA_VERSION = 1
STATES = {"ready", "running", "blocked", "stopped", "checking", "completed"}
DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class WorkError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def fail(code, message):
    raise WorkError(code, message)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("invalid_json", "Duplicate JSON object key.")
        result[key] = value
    return result


def reject_constant(_):
    fail("invalid_json", "Nonfinite JSON numbers are not supported.")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        reject_constant(value)
    return number


def loads(value):
    try:
        return json.loads(value, object_pairs_hook=strict_pairs,
                          parse_constant=reject_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError):
        fail("invalid_json", "Cannot decode valid UTF-8 JSON.")


def dumps(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":"), sort_keys=True)
    except (ValueError, TypeError, RecursionError):
        fail("invalid_json", "JSON values must be finite and serializable.")


def obj(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        fail("invalid_spec", "Object has missing or unknown fields.")


def string(value, name, limit=4000, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value.strip()) or len(value) > limit or "\x00" in value:
        fail("invalid_argument", f"{name} must be a nonempty string of at most {limit} characters without NUL.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        fail("invalid_argument", f"{name} must contain valid Unicode.")
    return value


def relative_path(value):
    string(value, "path", 4096)
    if (Path(value).is_absolute() or PureWindowsPath(value).drive or "\\" in value
            or ".." in value.split("/") or value in {".", ""}):
        fail("unsafe_path", "Paths must be relative and contain no traversal, drive, or backslash.")
    normalized = Path(value).as_posix()
    if normalized == ".":
        fail("unsafe_path", "Path must name an item inside the workspace.")
    return normalized


def contained(workspace, value):
    relative = relative_path(value)
    try:
        root = Path(workspace).resolve(strict=True)
        if str(root) != workspace or not root.is_dir():
            fail("unsafe_path", "The stored workspace no longer resolves to its original directory.")
        target = (root / relative).resolve(strict=False)
        target.relative_to(root)
        if target == root:
            fail("unsafe_path", "Path must name an item inside the workspace.")
    except (ValueError, RuntimeError):
        fail("unsafe_path", "Path resolves outside the workspace or contains a symlink loop.")
    return target


def decimal_value(value, name):
    string(value, name, 1000)
    if not DECIMAL_RE.fullmatch(value):
        fail("invalid_spec", f"{name} must be a finite decimal string.")
    try:
        number = Decimal(value)
        if not number.is_finite() or abs(number.adjusted()) > 10000:
            fail("invalid_spec", f"{name} exceeds the supported decimal range.")
        return number
    except InvalidOperation:
        fail("invalid_spec", f"{name} must be a finite decimal string.")


def pointer_tokens(pointer):
    string(pointer, "pointer", 4096, nonempty=False)
    if pointer and not pointer.startswith("/"):
        fail("invalid_spec", "JSON pointer must be empty or begin with '/'.")
    if re.search(r"~(?:[^01]|$)", pointer):
        fail("invalid_spec", "JSON pointer contains an invalid escape.")
    return [] if pointer == "" else [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def validate_spec(spec):
    obj(spec, ("goal", "workspace", "criteria", "limits"))
    string(spec["goal"], "goal", 10000)
    string(spec["workspace"], "workspace", 4096)
    root = Path(spec["workspace"])
    if not root.is_absolute() or not root.is_dir():
        fail("invalid_spec", "workspace must be an absolute existing directory.")
    spec["workspace"] = str(root.resolve(strict=True))
    obj(spec["limits"], ("max_steps", "max_seconds"))
    for name, value in spec["limits"].items():
        if type(value) is not int or not 0 < value <= 9223372036854775807:
            fail("invalid_spec", f"{name} must be a positive integer representable in SQLite.")
    if not isinstance(spec["criteria"], list) or not 1 <= len(spec["criteria"]) <= 128:
        fail("invalid_spec", "criteria must contain between 1 and 128 items.")
    ids = set()
    for criterion in spec["criteria"]:
        if not isinstance(criterion, dict):
            fail("invalid_spec", "Each criterion must be an object.")
        kind = criterion.get("type")
        params = {"file_nonempty": (), "text_contains": ("needle",),
                  "json_equals": ("pointer", "expected"), "csv_sum": ("column", "expected")}
        if not isinstance(kind, str) or kind not in params:
            fail("invalid_spec", "Unknown criterion type.")
        obj(criterion, ("id", "type", "path") + params[kind], ("tolerance",) if kind == "csv_sum" else ())
        identity = string(criterion["id"], "criterion id", 200)
        if identity in ids:
            fail("invalid_spec", "Criterion ids must be unique.")
        ids.add(identity)
        criterion["path"] = relative_path(criterion["path"])
        contained(spec["workspace"], criterion["path"])
        if kind == "text_contains":
            string(criterion["needle"], "needle", 64000, nonempty=False)
            if not criterion["needle"]:
                fail("invalid_spec", "needle must not be empty.")
        elif kind == "json_equals":
            pointer_tokens(criterion["pointer"])
            dumps(criterion["expected"])
        elif kind == "csv_sum":
            string(criterion["column"], "column", 1000)
            decimal_value(criterion["expected"], "expected")
            tolerance = decimal_value(criterion.get("tolerance", "0"), "tolerance")
            if tolerance < 0:
                fail("invalid_spec", "tolerance must be nonnegative.")
    return spec


def stamp(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds")
    except (ValueError, OverflowError, OSError):
        return value


def compare_resource_paths(left, right):
    # Match Windows path case rules without rewriting existing claim records.
    left, right = os.path.normcase(left), os.path.normcase(right)
    return (left > right) - (left < right)


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.create_collation("RESOURCE_PATH", compare_resource_paths)
        self.db.execute("PRAGMA busy_timeout=5000")
        app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
        tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        if app_id != APP_ID and (app_id or tables):
            fail("invalid_database", "Database is not a Universal Work ledger.")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("BEGIN IMMEDIATE")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            fail("invalid_database", "Database schema version is unsupported.")
        for statement in (
            "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,spec TEXT NOT NULL,state TEXT NOT NULL,steps INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,started REAL,deadline REAL,verification TEXT)",
            "CREATE TABLE IF NOT EXISTS actions (task_id TEXT NOT NULL REFERENCES tasks(id),key TEXT NOT NULL,state TEXT NOT NULL,description TEXT NOT NULL,evidence TEXT,created REAL NOT NULL,updated REAL NOT NULL,PRIMARY KEY(task_id,key))",
            "CREATE TABLE IF NOT EXISTS claims (resource TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),owner TEXT NOT NULL,relpath TEXT NOT NULL,created REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL REFERENCES tasks(id),kind TEXT NOT NULL,at REAL NOT NULL,data TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS event_task ON events(task_id,seq)",
        ):
            self.db.execute(statement)
        self.db.execute(f"PRAGMA application_id={APP_ID}")
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def task(self, task_id):
        string(task_id, "task id", 200)
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            fail("not_found", "Task does not exist.")
        task = dict(row)
        task["spec"] = loads(task["spec"])
        if task["state"] not in STATES:
            fail("invalid_database", "Task has an invalid state.")
        return task

    def event(self, task_id, kind, data=None):
        self.db.execute("INSERT INTO events(task_id,kind,at,data) VALUES(?,?,?,?)",
                        (task_id, kind, time.time(), dumps(data or {})))

    def update(self, task_id, state):
        self.db.execute("UPDATE tasks SET state=? WHERE id=?", (state, task_id))

    def counts(self, task_id):
        actions = dict(self.db.execute("SELECT state,count(*) FROM actions WHERE task_id=? GROUP BY state", (task_id,)).fetchall())
        claims = self.db.execute("SELECT count(*) FROM claims WHERE task_id=?", (task_id,)).fetchone()[0]
        return {"actions": actions, "claims": claims}

    def public(self, task, detailed=False):
        spec = task["spec"]
        result = {"id": task["id"], "goal": spec["goal"], "workspace": spec["workspace"],
                  "state": task["state"], "steps": task["steps"], "limits": spec["limits"],
                  "created_at": stamp(task["created"]), "started_at": stamp(task["started"]),
                  "deadline": stamp(task["deadline"]), **self.counts(task["id"])}
        if detailed:
            result["criteria"] = spec["criteria"]
            result["verification"] = loads(task["verification"]) if task["verification"] else None
            result["recent_actions"] = [dict(row) for row in self.db.execute(
                "SELECT key,state,description,evidence FROM actions WHERE task_id=? ORDER BY created DESC,key LIMIT 50", (task["id"],))]
            result["recent_claims"] = [dict(row) for row in self.db.execute(
                "SELECT relpath AS resource,owner FROM claims WHERE task_id=? ORDER BY created DESC LIMIT 50", (task["id"],))]
            result["recent_events"] = [{"seq": row["seq"], "kind": row["kind"], "at": stamp(row["at"]), "data": loads(row["data"])} for row in self.db.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY seq DESC LIMIT 20", (task["id"],))]
            result["history_limits"] = {"actions": 50, "claims": 50, "events": 20}
        return result

    def mutable(self, task):
        if task["state"] == "completed":
            fail("completed", "Completed tasks are immutable; create a new task.")

    def budget(self, task):
        if task["deadline"] is not None and time.time() >= task["deadline"]:
            fail("deadline_exceeded", "The original task deadline has expired.")
        if task["steps"] >= task["spec"]["limits"]["max_steps"]:
            fail("step_limit", "The task step budget is exhausted.")

    def running(self, task, check_budget=True):
        self.mutable(task)
        if task["state"] != "running":
            fail("invalid_state", "This command requires a running task.")
        if check_budget:
            self.budget(task)


def read_artifact(workspace, relative):
    path = contained(workspace, relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            fail("not_regular_file", "Criterion target is not a regular file.")
        if before.st_size > FILE_LIMIT:
            fail("file_too_large", "Criterion file exceeds 64 MiB.")
        data = handle.read(FILE_LIMIT + 1)
        after = os.fstat(handle.fileno())
        if len(data) > FILE_LIMIT:
            fail("file_too_large", "Criterion file exceeds 64 MiB.")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            fail("file_changed", "Criterion file changed during verification.")
        if contained(workspace, relative) != path or os.stat(path).st_ino != after.st_ino:
            fail("file_changed", "Criterion target changed during verification.")
    return data


def json_equal(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        return Decimal(str(actual)) == Decimal(str(expected))
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(json_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(json_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def evaluate(criterion, data):
    kind = criterion["type"]
    if kind == "file_nonempty":
        return bool(data)
    text = data.decode("utf-8-sig")
    if kind == "text_contains":
        return criterion["needle"] in text
    if kind == "json_equals":
        actual = loads(text)
        for token in pointer_tokens(criterion["pointer"]):
            if isinstance(actual, dict) and token in actual:
                actual = actual[token]
            elif isinstance(actual, list) and re.fullmatch(r"0|[1-9][0-9]*", token) and len(token) < 20 and int(token) < len(actual):
                actual = actual[int(token)]
            else:
                fail("pointer_not_found", "JSON pointer does not identify a value.")
        return json_equal(actual, criterion["expected"])
    # read_artifact already bounds the complete CSV to FILE_LIMIT bytes.
    csv.field_size_limit(FILE_LIMIT)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = next(reader, None)
    if not header or len(header) != len(set(header)) or criterion["column"] not in header:
        fail("invalid_csv", "CSV requires unique headers including the specified column.")
    index = header.index(criterion["column"])
    expected = decimal_value(criterion["expected"], "expected")
    tolerance = decimal_value(criterion.get("tolerance", "0"), "tolerance")
    # The bounded decimal exponent and file size allow an exact finite sum.
    with localcontext() as context:
        context.prec = 22020
        total = Decimal(0)
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                fail("invalid_csv", "CSV row width does not match its header.")
            total += decimal_value(row[index].strip(), "CSV value")
        return abs(total - expected) <= tolerance


def verify(ledger, task, finish=False):
    ledger.running(task, check_budget=False)
    ledger.update(task["id"], "checking")
    ledger.event(task["id"], "verification_started", {"finish": finish})
    results_by_id = {}
    groups = {}
    for criterion in task["spec"]["criteria"]:
        groups.setdefault(criterion["path"], []).append(criterion)
    for path, criteria in groups.items():
        data, artifact_error, digest = None, None, None
        try:
            data = read_artifact(task["spec"]["workspace"], path)
            digest = hashlib.sha256(data).hexdigest()
        except WorkError as error:
            artifact_error = (error.code, error.message)
        except FileNotFoundError:
            artifact_error = ("missing_file", "Criterion file does not exist.")
        except PermissionError:
            artifact_error = ("permission_denied", "Criterion file cannot be read.")
        except OSError:
            artifact_error = ("invalid_artifact", "Criterion file could not be safely read.")
        for criterion in criteria:
            result = {key: criterion[key] for key in ("id", "type", "path")}
            result.update(passed=False, sha256=digest)
            try:
                if artifact_error:
                    fail(*artifact_error)
                result["bytes"] = len(data)
                result["passed"] = evaluate(criterion, data)
                result["message"] = "Criterion passed." if result["passed"] else "Criterion did not match."
            except WorkError as error:
                result.update(code=error.code, message=error.message)
            except (UnicodeError, csv.Error, InvalidOperation, RecursionError, OverflowError):
                result.update(code="invalid_artifact", message="Criterion file could not be safely decoded.")
            results_by_id[criterion["id"]] = result
    results = [results_by_id[criterion["id"]] for criterion in task["spec"]["criteria"]]
    report = {"passed": all(result["passed"] for result in results), "checked_at": stamp(time.time()), "results": results}
    ledger.db.execute("UPDATE tasks SET verification=?,state='running' WHERE id=?", (dumps(report), task["id"]))
    ledger.event(task["id"], "verification_finished", {"passed": report["passed"], "hashes": {r["id"]: r["sha256"] for r in results}})
    code, message = None, None
    if not report["passed"]:
        code, message = "verification_failed", "One or more current artifacts failed verification."
    elif finish:
        counts = ledger.counts(task["id"])
        if counts["actions"].get("prepared", 0) or counts["actions"].get("unknown", 0):
            code, message = "unresolved_actions", "Reconcile all prepared or unknown actions before completion."
        elif counts["claims"]:
            code, message = "outstanding_claims", "Release all claims before completion."
        else:
            ledger.update(task["id"], "completed")
            ledger.event(task["id"], "completed")
    response = {"ok": code is None, "task": ledger.public(ledger.task(task["id"])), "verification": report}
    if code:
        response["error"] = {"code": code, "message": message}
    return response


def dispatch(ledger, args):
    command = args.command
    if command == "new":
        with open(args.spec, "rb") as handle:
            raw = handle.read(SPEC_LIMIT + 1)
        if len(raw) > SPEC_LIMIT:
            fail("invalid_spec", "Task spec exceeds 1 MiB.")
        spec = validate_spec(loads(raw))
        task_id = uuid.uuid4().hex
        ledger.db.execute("INSERT INTO tasks(id,spec,state,created) VALUES(?,?,'ready',?)", (task_id, dumps(spec), time.time()))
        ledger.event(task_id, "created")
        return {"ok": True, "task": ledger.public(ledger.task(task_id))}
    if command == "list":
        rows = ledger.db.execute("SELECT id FROM tasks ORDER BY created DESC,id LIMIT 101").fetchall()
        return {"ok": True, "tasks": [ledger.public(ledger.task(row[0])) for row in rows[:100]], "truncated": len(rows) > 100, "limit": 100}
    task = ledger.task(args.task)
    task_id = task["id"]
    if command == "show":
        return {"ok": True, "task": ledger.public(task, detailed=True)}
    ledger.mutable(task)
    if command in ("verify", "finish"):
        return verify(ledger, task, command == "finish")
    if command == "start":
        if task["state"] != "ready":
            fail("invalid_state", "Only a ready task can be started.")
        ledger.budget(task)
        now = time.time()
        ledger.db.execute("UPDATE tasks SET state='running',started=?,deadline=? WHERE id=?", (now, now + task["spec"]["limits"]["max_seconds"], task_id))
        ledger.event(task_id, "started")
    elif command == "resume":
        if task["state"] not in ("blocked", "stopped") or task["started"] is None:
            fail("invalid_state", "Only a previously started blocked or stopped task can resume.")
        ledger.budget(task)
        actions = ledger.counts(task_id)["actions"]
        if actions.get("prepared", 0) or actions.get("unknown", 0):
            fail("unresolved_actions", "Reconcile prepared or unknown external actions before resuming.")
        ledger.update(task_id, "running")
        ledger.event(task_id, "resumed")
    elif command in ("stop", "block"):
        reason = string(args.reason, "reason")
        if command == "block":
            ledger.running(task, check_budget=False)
        ledger.update(task_id, "stopped" if command == "stop" else "blocked")
        ledger.event(task_id, command, {"reason": reason})
    elif command == "checkpoint":
        ledger.running(task)
        note = string(args.note, "note")
        ledger.db.execute("UPDATE tasks SET steps=steps+1 WHERE id=?", (task_id,))
        ledger.event(task_id, "checkpoint", {"note": note})
    elif command == "action-prepare":
        key = string(args.key, "action key", 200)
        if ledger.db.execute("SELECT 1 FROM actions WHERE task_id=? AND key=?", (task_id, key)).fetchone():
            fail("action_exists", "This task already contains that action key; inspect its outcome and do not repeat its effect.")
        ledger.running(task)
        description = string(args.description, "description")
        now = time.time()
        ledger.db.execute("INSERT INTO actions VALUES(?,?, 'prepared',?,NULL,?,?)", (task_id, key, description, now, now))
        ledger.db.execute("UPDATE tasks SET steps=steps+1 WHERE id=?", (task_id,))
        ledger.event(task_id, "action_prepared", {"key": key})
    elif command == "action-outcome":
        key = string(args.key, "action key", 200)
        evidence = string(args.evidence, "evidence")
        action = ledger.db.execute("SELECT state FROM actions WHERE task_id=? AND key=?", (task_id, key)).fetchone()
        if action is None:
            fail("action_not_found", "Prepare an action before recording its outcome.")
        if action["state"] not in ("prepared", "unknown"):
            fail("action_final", "A succeeded or failed outcome cannot be rewritten.")
        ledger.db.execute("UPDATE actions SET state=?,evidence=?,updated=? WHERE task_id=? AND key=?", (args.outcome, evidence, time.time(), task_id, key))
        ledger.event(task_id, "action_outcome", {"key": key, "outcome": args.outcome})
    elif command == "claim":
        ledger.running(task)
        owner = string(args.owner, "owner", 200)
        relative = relative_path(args.resource)
        resource = str(contained(task["spec"]["workspace"], relative))
        existing = ledger.db.execute("SELECT task_id,owner FROM claims WHERE resource=? COLLATE RESOURCE_PATH", (resource,)).fetchone()
        if existing:
            fail("claim_conflict", "That canonical resource is already claimed in this ledger.")
        ledger.db.execute("INSERT INTO claims VALUES(?,?,?,?,?)", (resource, task_id, owner, relative, time.time()))
        ledger.event(task_id, "claimed", {"resource": relative, "owner": owner})
    elif command == "release":
        owner = string(args.owner, "owner", 200)
        relative = relative_path(args.resource)
        claim = ledger.db.execute("SELECT * FROM claims WHERE task_id=? AND relpath=?", (task_id, relative)).fetchone()
        if claim is None:
            resource = str(contained(task["spec"]["workspace"], relative))
            claim = ledger.db.execute("SELECT * FROM claims WHERE task_id=? AND resource=? COLLATE RESOURCE_PATH", (task_id, resource)).fetchone()
        if claim is None:
            fail("claim_not_found", "This task does not hold that resource claim.")
        if claim["owner"] != owner:
            fail("claim_owner", "Only the recorded owner can release this claim.")
        ledger.db.execute("DELETE FROM claims WHERE resource=?", (claim["resource"],))
        ledger.event(task_id, "released", {"resource": claim["relpath"], "owner": owner})
    return {"ok": True, "task": ledger.public(ledger.task(task_id))}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail("usage", message)


def parser():
    result = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Budget starts at first start; checkpoint and each new action-prepare cost one step.\n"
               "Action keys are unique per task; duplicate prepares are refused, never retried.\n"
               "Inspection, stop/block, release, outcomes and final checks survive budget exhaustion.\n"
               "Verification reads regular files up to 64 MiB; output never includes file contents.\n"
               "Use one ledger to coordinate claims; these are not operating-system locks.")
    result.add_argument("--db", required=True, help="SQLite ledger path on local disk")
    sub = result.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="validate a JSON spec and create a ready task")
    new.add_argument("--spec", required=True, help="UTF-8 JSON task spec, at most 1 MiB")
    sub.add_parser("list", help="show the latest 100 tasks")
    for name in ("show", "start", "checkpoint", "verify", "finish", "stop", "block", "resume", "action-prepare", "action-outcome", "claim", "release"):
        command = sub.add_parser(name)
        command.add_argument("task")
        if name == "checkpoint":
            command.add_argument("--note", required=True)
        elif name in ("stop", "block"):
            command.add_argument("--reason", required=True)
        elif name in ("action-prepare", "action-outcome"):
            command.add_argument("--key", required=True)
            if name == "action-prepare":
                command.add_argument("--description", required=True)
            else:
                command.add_argument("--outcome", choices=("succeeded", "failed", "unknown"), required=True)
                command.add_argument("--evidence", required=True)
        elif name in ("claim", "release"):
            command.add_argument("--resource", required=True)
            command.add_argument("--owner", required=True)
    return result


def main():
    ledger = None
    try:
        args = parser().parse_args()
        string(args.db, "database path", 4096)
        if args.db == ":memory:":
            fail("invalid_database", "Use a persistent ledger file on local disk.")
        database = Path(args.db)
        if args.command == "new":
            database.parent.mkdir(parents=True, exist_ok=True)
        elif not database.is_file():
            fail("database_not_found", "Ledger file does not exist; use new to create it.")
        ledger = Ledger(args.db)
        response = dispatch(ledger, args)
        ledger.db.commit()
    except WorkError as error:
        response = {"ok": False, "error": {"code": error.code, "message": error.message}}
    except sqlite3.Error:
        response = {"ok": False, "error": {"code": "database_error", "message": "Ledger is unavailable, busy, corrupt, or incompatible."}}
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        response = {"ok": False, "error": {"code": "io_error", "message": "Input or filesystem data could not be safely processed."}}
    finally:
        if ledger is not None:
            ledger.db.close()  # Rolls back any failed command, including partial mutations.
    print(dumps(response))
    return 0 if response["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
