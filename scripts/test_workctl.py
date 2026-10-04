#!/usr/bin/env python3
"""Black-box acceptance checks for the local workctl CLI.

Run: python scripts/test_workctl.py
Every CLI invocation runs in a new process. All fixtures, databases, resources,
and simulated action records are disposable local files; no action is executed.
"""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


WORKCTL = Path(__file__).with_name("workctl.py")


class WorkctlAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workctl-acceptance-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database = self.root / "ledger.sqlite3"
        self.spec_number = 0

    def command(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(WORKCTL), "--db", str(self.database), *args],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0 if ok else 2,
            f"command {args!r}\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI did not return one JSON envelope: {result.stdout!r}; {exc}")
        self.assertIs(response.get("ok"), ok, response)
        if not ok:
            error = response.get("error")
            self.assertIsInstance(error, dict, response)
            self.assertIsInstance(error.get("code"), str, response)
            self.assertTrue(error["code"].strip(), response)
            self.assertIsInstance(error.get("message"), str, response)
            self.assertTrue(error["message"].strip(), response)
        return response

    def write_spec(self, *, criteria=None, limits=None, workspace=None, **extra):
        spec = {
            "goal": "Produce and verify a local acceptance artifact",
            "workspace": str(workspace or self.workspace),
            "criteria": criteria if criteria is not None else [
                {"id": "artifact", "type": "file_nonempty", "path": "artifact.txt"}
            ],
            "limits": limits or {"max_steps": 30, "max_seconds": 60},
        }
        spec.update(extra)
        self.spec_number += 1
        path = self.root / f"spec-{self.spec_number}.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def new(self, **spec_options):
        response = self.command("new", "--spec", str(self.write_spec(**spec_options)))
        task = response["task"]
        self.assertIsInstance(task["id"], str)
        self.assertTrue(task["id"])
        self.assertEqual(task["state"], "ready")
        return task["id"]

    def running(self, **spec_options):
        task_id = self.new(**spec_options)
        response = self.command("start", task_id)
        self.assertEqual(response["task"]["state"], "running")
        return task_id

    def artifact(self, content="A durable artifact.\n", name="artifact.txt"):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def require_case_insensitive_workspace(self):
        if sys.platform != "win32":
            self.skipTest("Windows resource path case handling")
        probe = self.workspace / "_ÄCaseProbe.txt"
        alias = self.workspace / "_äcaseprobe.txt"
        probe.write_text("filesystem case probe", encoding="utf-8")
        try:
            insensitive = alias.exists() and probe.samefile(alias)
        finally:
            probe.unlink()
        if not insensitive:
            self.skipTest("Workspace filesystem distinguishes filename case")

    def assert_verification(self, response, passed):
        verification = response["verification"]
        self.assertIs(verification["passed"], passed, response)
        self.assertIsInstance(verification["results"], list)
        self.assertTrue(verification["results"])
        return verification

    def exhaust_steps(self, task_id):
        # The budget is observable at the CLI; no private database writes are used.
        limit = self.command("show", task_id)["task"]["limits"]["max_steps"]
        for index in range(limit + 1):
            shown = self.command("show", task_id)["task"]
            if shown["steps"] >= limit:
                break
            self.command("checkpoint", task_id, "--note", f"bounded step {index}")
        self.command("checkpoint", task_id, "--note", "over quota", ok=False)

    def test_successful_lifecycle_persists_across_processes(self):
        self.artifact()
        task_id = self.running()
        self.command("checkpoint", task_id, "--note", "Artifact prepared")
        shown = self.command("show", task_id)["task"]
        self.assertEqual(shown["id"], task_id)
        self.assertEqual(shown["state"], "running")
        self.assertEqual(shown["steps"], 1)
        verified = self.command("verify", task_id)
        self.assert_verification(verified, True)
        self.assertEqual(verified["task"]["state"], "running")
        finished = self.command("finish", task_id)
        self.assertEqual(finished["task"]["state"], "completed")
        self.assertEqual(self.command("show", task_id)["task"]["state"], "completed")
        listed = self.command("list")
        self.assertIn(task_id, [task["id"] for task in listed["tasks"]])

    def test_new_creates_nested_database_dirs_but_inspection_does_not(self):
        self.database = self.root / "missing" / "nested" / "ledger.sqlite3"
        for args in (("list",), ("show", "task-does-not-exist")):
            with self.subTest(command=args[0]):
                self.command(*args, ok=False)
                self.assertFalse(self.database.exists())
                self.assertFalse((self.root / "missing").exists())
        task_id = self.new()
        self.assertTrue(self.database.is_file())
        self.assertEqual(self.command("show", task_id)["task"]["state"], "ready")

    def test_missing_or_empty_artifact_cannot_complete(self):
        task_id = self.running()
        for content in (None, ""):
            with self.subTest(content=content):
                if content is not None:
                    self.artifact(content)
                response = self.command("verify", task_id, ok=False)
                self.assert_verification(response, False)
                self.assertEqual(response["task"]["state"], "running")
                self.command("finish", task_id, ok=False)
                self.assertEqual(self.command("show", task_id)["task"]["state"], "running")

    def test_finish_rechecks_edited_artifact_and_refreshes_digest(self):
        path = self.artifact("first contents")
        task_id = self.running()
        old = self.assert_verification(self.command("verify", task_id), True)
        self.assertEqual(old["results"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        path.write_text("changed contents, still valid", encoding="utf-8")
        finished = self.command("finish", task_id)
        fresh = self.assert_verification(finished, True)
        self.assertEqual(fresh["results"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertNotEqual(old["results"][0]["sha256"], fresh["results"][0]["sha256"])

    def test_prior_pass_cannot_hide_a_later_content_failure(self):
        path = self.artifact("required phrase")
        task_id = self.running(criteria=[{
            "id": "text", "type": "text_contains", "path": "artifact.txt",
            "needle": "required phrase",
        }])
        self.assert_verification(self.command("verify", task_id), True)
        path.write_text("the evidence changed", encoding="utf-8")
        response = self.command("finish", task_id, ok=False)
        self.assert_verification(response, False)
        self.assertNotEqual(response["task"]["state"], "completed")

    def test_step_quota_denies_checkpoints_and_new_action_preparations(self):
        task_id = self.running(limits={"max_steps": 2, "max_seconds": 60})
        self.exhaust_steps(task_id)
        before = self.command("show", task_id)["task"]["steps"]
        self.command("action-prepare", task_id, "--key", "too-late",
                     "--description", "Never executed", ok=False)
        self.assertEqual(self.command("show", task_id)["task"]["steps"], before)

    def test_exhausted_budget_allows_recording_outcomes_and_releasing_claims(self):
        task_id = self.running(limits={"max_steps": 2, "max_seconds": 60})
        self.command("claim", task_id, "--resource", "shared.txt", "--owner", "worker-a")
        self.command("action-prepare", task_id, "--key", "simulated",
                     "--description", "Record only; no external action")
        self.exhaust_steps(task_id)
        self.command("action-outcome", task_id, "--key", "simulated",
                     "--outcome", "succeeded", "--evidence", "Local simulation completed")
        self.command("release", task_id, "--resource", "shared.txt", "--owner", "worker-a")

    def test_exhausted_budgets_allow_bounded_local_verification_and_finish(self):
        self.artifact()
        task_id = self.running(limits={"max_steps": 1, "max_seconds": 1})
        self.command("checkpoint", task_id, "--note", "Last permitted work step")
        time.sleep(1.1)
        self.command("checkpoint", task_id, "--note", "New work is denied", ok=False)
        self.assert_verification(self.command("verify", task_id), True)
        self.assertEqual(self.command("finish", task_id)["task"]["state"], "completed")

    def test_resume_preserves_the_original_deadline(self):
        task_id = self.running(limits={"max_steps": 30, "max_seconds": 1})
        self.command("claim", task_id, "--resource", "deadline-resource.txt", "--owner", "worker")
        self.command("action-prepare", task_id, "--key", "before-expiry",
                     "--description", "Local record requiring later reconciliation")
        original_deadline = self.command("show", task_id)["task"]["deadline"]
        self.command("stop", task_id, "--reason", "Pause before expiry")
        # Exercise the public clock without editing internal database state.
        time.sleep(1.1)
        self.command("resume", task_id, ok=False)
        shown = self.command("show", task_id)["task"]
        self.assertEqual(shown["deadline"], original_deadline)
        self.command("checkpoint", task_id, "--note", "Expired work", ok=False)
        self.command("action-outcome", task_id, "--key", "before-expiry", "--outcome", "succeeded",
                     "--evidence", "Late receipt recording must remain possible")
        self.command("release", task_id, "--resource", "deadline-resource.txt", "--owner", "worker")

    def test_stop_and_block_can_resume_without_resetting_steps_or_deadline(self):
        task_id = self.running()
        self.command("checkpoint", task_id, "--note", "One useful step")
        before = self.command("show", task_id)["task"]
        for command, state in (("stop", "stopped"), ("block", "blocked")):
            with self.subTest(command=command):
                response = self.command(command, task_id, "--reason", "Explicit pause")
                self.assertEqual(response["task"]["state"], state)
                resumed = self.command("resume", task_id)["task"]
                self.assertEqual(resumed["state"], "running")
                self.assertEqual(resumed["steps"], before["steps"])
                self.assertEqual(resumed["deadline"], before["deadline"])

    def test_prepared_action_survives_process_exit_and_cannot_be_prepared_twice(self):
        self.artifact()
        task_id = self.running()
        self.command("action-prepare", task_id, "--key", "remote-write",
                     "--description", "Simulated crash after durable preparation")
        # The prepare process is now gone, with no outcome recorded.
        self.command("finish", task_id, ok=False)
        duplicate = self.command("action-prepare", task_id, "--key", "remote-write",
                                 "--description", "Would duplicate the action", ok=False)
        self.assertEqual(duplicate["error"]["code"], "action_exists")
        self.assertNotEqual(self.command("show", task_id)["task"]["state"], "completed")

    def test_stopped_task_cannot_resume_until_prepared_action_is_reconciled(self):
        task_id = self.running()
        self.command("action-prepare", task_id, "--key", "pending-at-stop",
                     "--description", "Local simulation interrupted before outcome")
        self.command("stop", task_id, "--reason", "Process interruption")
        response = self.command("resume", task_id, ok=False)
        self.assertEqual(response["error"]["code"], "unresolved_actions")
        self.assertEqual(self.command("show", task_id)["task"]["state"], "stopped")
        self.command("action-outcome", task_id, "--key", "pending-at-stop", "--outcome", "succeeded",
                     "--evidence", "Inspected simulated durable receipt")
        self.assertEqual(self.command("resume", task_id)["task"]["state"], "running")

    def test_unknown_action_blocks_finish_until_reconciled(self):
        self.artifact()
        task_id = self.running()
        self.command("action-prepare", task_id, "--key", "uncertain",
                     "--description", "Local uncertainty simulation")
        self.command("action-outcome", task_id, "--key", "uncertain", "--outcome", "unknown",
                     "--evidence", "Process exited before response was recorded")
        self.command("finish", task_id, ok=False)
        self.command("action-outcome", task_id, "--key", "uncertain", "--outcome", "succeeded",
                     "--evidence", "Inspected durable receipt in local fixture")
        self.assertEqual(self.command("finish", task_id)["task"]["state"], "completed")

    def test_failed_action_is_resolved_and_key_remains_reserved(self):
        self.artifact()
        task_id = self.running()
        self.command("action-prepare", task_id, "--key", "failed-attempt",
                     "--description", "Simulate a definitely failed action")
        self.command("action-outcome", task_id, "--key", "failed-attempt", "--outcome", "failed",
                     "--evidence", "Local fixture confirms nothing happened")
        self.command("action-prepare", task_id, "--key", "failed-attempt",
                     "--description", "Reuse is forbidden", ok=False)
        self.command("action-outcome", task_id, "--key", "failed-attempt", "--outcome", "succeeded",
                     "--evidence", "Cannot rewrite a known outcome", ok=False)
        self.assertEqual(self.command("finish", task_id)["task"]["state"], "completed")

    def test_cross_task_resource_claims_reject_conflicting_owners(self):
        first, second = self.running(), self.running()
        self.command("claim", first, "--resource", "shared.txt", "--owner", "alice")
        self.command("claim", second, "--resource", "shared.txt", "--owner", "bob", ok=False)
        self.command("release", first, "--resource", "shared.txt", "--owner", "bob", ok=False)
        self.command("release", second, "--resource", "shared.txt", "--owner", "alice", ok=False)
        self.command("release", first, "--resource", "shared.txt", "--owner", "alice")
        self.command("claim", second, "--resource", "shared.txt", "--owner", "bob")

    def test_absent_case_alias_claims_conflict_across_tasks(self):
        self.require_case_insensitive_workspace()
        for resource, alias in (("Shared.txt", "shared.txt"),
                                ("ÄShared.txt", "äshared.txt")):
            with self.subTest(resource=resource):
                first, second = self.running(), self.running()
                self.assertFalse((self.workspace / resource).exists())
                self.assertFalse((self.workspace / alias).exists())
                self.command("claim", first, "--resource", resource, "--owner", "alice")
                response = self.command("claim", second, "--resource", alias,
                                        "--owner", "bob", ok=False)
                self.assertEqual(response["error"]["code"], "claim_conflict")
                self.assertEqual(self.command("show", first)["task"]["claims"], 1)
                self.assertEqual(self.command("show", second)["task"]["claims"], 0)

    def test_case_alias_release_preserves_owner_and_allows_reclaim(self):
        self.require_case_insensitive_workspace()
        for resource, alias in (("Shared.txt", "shared.txt"),
                                ("ÄShared.txt", "äshared.txt")):
            with self.subTest(resource=resource):
                first, second = self.running(), self.running()
                self.command("claim", first, "--resource", resource, "--owner", "alice")
                response = self.command("release", first, "--resource", alias,
                                        "--owner", "bob", ok=False)
                self.assertEqual(response["error"]["code"], "claim_owner")
                self.assertEqual(self.command("show", first)["task"]["claims"], 1)
                self.command("release", first, "--resource", alias, "--owner", "alice")
                self.assertEqual(self.command("show", first)["task"]["claims"], 0)
                self.command("claim", second, "--resource", alias, "--owner", "bob")
                claim = self.command("show", second)["task"]["recent_claims"]
                self.assertEqual(claim, [{"resource": alias, "owner": "bob"}])

    def test_same_relative_resource_in_separate_workspaces_does_not_conflict(self):
        other_workspace = self.root / "other-workspace"
        other_workspace.mkdir()
        first = self.running()
        second = self.running(workspace=other_workspace)
        self.command("claim", first, "--resource", "shared.txt", "--owner", "alice")
        self.command("claim", second, "--resource", "shared.txt", "--owner", "bob")

    def test_traversal_absolute_and_backslash_paths_are_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        for path in ("../outside.txt", str(outside), "nested/../../outside.txt", "..\\outside.txt"):
            with self.subTest(path=path):
                spec = self.write_spec(criteria=[{"id": "bad", "type": "file_nonempty", "path": path}])
                self.command("new", "--spec", str(spec), ok=False)
        task_id = self.running()
        for path in ("../outside.txt", str(outside), "..\\outside.txt"):
            with self.subTest(resource=path):
                self.command("claim", task_id, "--resource", path, "--owner", "owner", ok=False)

    def test_symlink_escape_is_rejected_at_verification_and_claim(self):
        outside = self.root / "outside.txt"
        outside.write_text("external contents", encoding="utf-8")
        task_id = self.running()
        try:
            (self.workspace / "artifact.txt").symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Host cannot create symlinks: {exc}")
        self.command("verify", task_id, ok=False)
        self.command("finish", task_id, ok=False)
        self.command("claim", task_id, "--resource", "artifact.txt", "--owner", "owner", ok=False)

    def test_directory_symlink_escape_is_rejected(self):
        outside = self.root / "external"
        outside.mkdir()
        (outside / "proof.txt").write_text("outside", encoding="utf-8")
        task_id = self.running(criteria=[{
            "id": "nested", "type": "file_nonempty", "path": "linked/proof.txt",
        }])
        try:
            (self.workspace / "linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Host cannot create symlinks: {exc}")
        self.command("verify", task_id, ok=False)
        self.command("claim", task_id, "--resource", "linked/new.txt", "--owner", "owner", ok=False)

    def test_corrupt_or_missing_spec_returns_a_clear_error(self):
        spec = self.root / "broken.json"
        for content in ("{", "[]", "null"):
            with self.subTest(content=content):
                spec.write_text(content, encoding="utf-8")
                self.command("new", "--spec", str(spec), ok=False)
        self.command("new", "--spec", str(self.root / "absent.json"), ok=False)

    def test_invalid_limits_and_unknown_fields_are_rejected(self):
        for field in ("max_steps", "max_seconds"):
            for invalid in (0, -1, True, "2", 1.5):
                with self.subTest(field=field, value=invalid):
                    limits = {"max_steps": 5, "max_seconds": 60, field: invalid}
                    self.command("new", "--spec", str(self.write_spec(limits=limits)), ok=False)
        cases = [
            self.write_spec(unrecognized=True),
            self.write_spec(limits={"max_steps": 5, "max_seconds": 60, "extra": 1}),
            self.write_spec(criteria=[{
                "id": "artifact", "type": "file_nonempty", "path": "artifact.txt", "extra": 1,
            }]),
            self.write_spec(criteria=[{"id": "bad", "type": "shell", "path": "artifact.txt"}]),
        ]
        for spec in cases:
            with self.subTest(spec=spec.name):
                self.command("new", "--spec", str(spec), ok=False)

    def test_json_pointer_escaping_and_root_equality(self):
        contents = {"a/b": {"~key": [{"value": 3}]}, "ready": True}
        self.artifact(json.dumps(contents), "proof.json")
        task_id = self.running(criteria=[
            {"id": "escaped", "type": "json_equals", "path": "proof.json",
             "pointer": "/a~1b/~0key/0/value", "expected": 3},
            {"id": "root", "type": "json_equals", "path": "proof.json",
             "pointer": "", "expected": contents},
        ])
        verification = self.assert_verification(self.command("verify", task_id), True)
        self.assertEqual({result["id"] for result in verification["results"]}, {"escaped", "root"})

    def test_json_missing_pointer_and_boolean_number_mismatch_fail(self):
        self.artifact('{"value": true}', "proof.json")
        for pointer, expected in (("/missing", None), ("/value", 1)):
            with self.subTest(pointer=pointer):
                task_id = self.running(criteria=[{
                    "id": "json", "type": "json_equals", "path": "proof.json",
                    "pointer": pointer, "expected": expected,
                }])
                self.assert_verification(self.command("verify", task_id, ok=False), False)

    def test_json_numeric_overflow_cannot_pass_even_for_an_unrelated_pointer(self):
        self.artifact('{"value": 1e999, "ready": true}', "proof.json")
        task_id = self.running(criteria=[{
            "id": "json", "type": "json_equals", "path": "proof.json",
            "pointer": "/ready", "expected": True,
        }])
        self.assert_verification(self.command("verify", task_id, ok=False), False)
        self.command("finish", task_id, ok=False)
        self.assertEqual(self.command("show", task_id)["task"]["state"], "running")

    def test_csv_sum_uses_exact_decimal_arithmetic(self):
        self.artifact("amount\n0.1\n0.2\n", "amounts.csv")
        task_id = self.running(criteria=[{
            "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
            "expected": "0.3",
        }])
        self.assert_verification(self.command("verify", task_id), True)
        wrong_id = self.running(criteria=[{
            "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
            "expected": "0.30000000000000000001",
        }])
        self.assert_verification(self.command("verify", wrong_id, ok=False), False)
        tolerant_id = self.running(criteria=[{
            "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
            "expected": "0.30000000000000000001", "tolerance": "0.00000000000000000001",
        }])
        self.assert_verification(self.command("verify", tolerant_id), True)

    def test_csv_sum_handles_signed_values_and_quoted_rows(self):
        path = self.workspace / "amounts.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["label", "amount"])
            writer.writerows([['first, quoted', "100000000000000000000000000000000000000.01"],
                              ["refund", "-100000000000000000000000000000000000000.00"],
                              ["credit", "0.02"]])
        task_id = self.running(criteria=[{
            "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
            "expected": "0.03",
        }])
        self.assert_verification(self.command("verify", task_id), True)

    def test_csv_sum_accepts_long_unrelated_fields(self):
        path = self.workspace / "amounts.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["label", "amount"])
            writer.writerows([["x" * 140000, "0.1"], ["second", "0.2"]])
        task_id = self.running(criteria=[{
            "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
            "expected": "0.3",
        }])
        self.assert_verification(self.command("verify", task_id), True)

    def test_invalid_csv_expectations_and_tolerances_are_rejected(self):
        for key, value in (("expected", "nope"), ("expected", "NaN"), ("expected", "Infinity"),
                           ("expected", 0.3), ("tolerance", "-0.01"), ("tolerance", "NaN")):
            with self.subTest(key=key, value=value):
                criterion = {
                    "id": "total", "type": "csv_sum", "path": "amounts.csv",
                    "column": "amount", "expected": "0.3", key: value,
                }
                self.command("new", "--spec", str(self.write_spec(criteria=[criterion])), ok=False)

    def test_bad_csv_cells_and_missing_columns_cannot_pass(self):
        for content in ("amount\nNaN\n", "amount\nInfinity\n", "amount\nabc\n", "other\n0.3\n"):
            with self.subTest(content=content):
                self.artifact(content, "amounts.csv")
                task_id = self.running(criteria=[{
                    "id": "total", "type": "csv_sum", "path": "amounts.csv", "column": "amount",
                    "expected": "0.3",
                }])
                self.assert_verification(self.command("verify", task_id, ok=False), False)

    def test_completed_tasks_are_immutable(self):
        self.artifact()
        task_id = self.running()
        self.command("action-prepare", task_id, "--key", "known", "--description", "Local record")
        self.command("action-outcome", task_id, "--key", "known", "--outcome", "succeeded",
                     "--evidence", "Simulated receipt")
        self.command("finish", task_id)
        commands = [
            ("start", task_id), ("verify", task_id), ("finish", task_id), ("resume", task_id),
            ("checkpoint", task_id, "--note", "late change"),
            ("stop", task_id, "--reason", "late change"),
            ("block", task_id, "--reason", "late change"),
            ("action-prepare", task_id, "--key", "late", "--description", "late change"),
            ("action-outcome", task_id, "--key", "known", "--outcome", "unknown", "--evidence", "late"),
            ("claim", task_id, "--resource", "shared.txt", "--owner", "late"),
            ("release", task_id, "--resource", "shared.txt", "--owner", "late"),
        ]
        for args in commands:
            with self.subTest(command=args[0]):
                self.command(*args, ok=False)
        self.assertEqual(self.command("show", task_id)["task"]["state"], "completed")

    def test_unknown_task_returns_a_clear_error(self):
        self.command("show", "task-does-not-exist", ok=False)


if __name__ == "__main__":
    if not WORKCTL.is_file():
        raise SystemExit(f"Runtime missing: {WORKCTL}")
    unittest.main(verbosity=2)
