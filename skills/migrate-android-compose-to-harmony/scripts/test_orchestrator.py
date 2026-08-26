#!/usr/bin/env python3
"""Behavior tests for the resumable migration-agent CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import migration_agent
from evidence_attestation import attach_attestation, load_ownership_secret


SCRIPTS = Path(__file__).resolve().parent
AGENT = SCRIPTS / "migration_agent.py"
HASH_TARGET = SCRIPTS / "hash_target_source.py"
EVIDENCE_RUNNER = SCRIPTS / "evidence_runner.py"
CAPTURE_EXECUTION_PLAN = SCRIPTS / "capture_execution_plan_regressions.py"
SLICE_GATES = ("build", "unit_tests", "ui_tests", "device_test")
EVIDENCE_GATES = SLICE_GATES + ("visual_review",)


def run_agent(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AGENT), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def run_script(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def create_compose_source(root: Path) -> Path:
    source = root / "android-source"
    (source / "app/src/main/java/com/example/sample/theme").mkdir(parents=True)
    (source / "settings.gradle.kts").write_text(
        'pluginManagement { repositories { google(); mavenCentral() } }\n'
        'include(":app")\n',
        encoding="utf-8",
    )
    (source / "app/build.gradle.kts").write_text(
        'plugins { id("com.android.application") }\n'
        "dependencies { implementation(\"androidx.compose.ui:ui:1.7.0\") }\n",
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/MainActivity.kt"
    ).write_text(
        """
package com.example.sample

class MainActivity
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/HomeScreen.kt"
    ).write_text(
        """
package com.example.sample

import com.example.sample.theme.AppTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun HomeScreen() {
    AppTheme {
        Text("Hello")
    }
}
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/SettingsScreen.kt"
    ).write_text(
        """
package com.example.sample

import com.example.sample.theme.AppTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun SettingsScreen() {
    AppTheme {
        Text("Settings")
    }
}
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/HomeViewModel.kt"
    ).write_text(
        """
package com.example.sample

class HomeViewModel
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/SettingsViewModel.kt"
    ).write_text(
        """
package com.example.sample

class SettingsViewModel
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/SharedSessionManager.kt"
    ).write_text(
        """
package com.example.sample

class SharedSessionManager
""".lstrip(),
        encoding="utf-8",
    )
    (
        source
        / "app/src/main/java/com/example/sample/theme/AppTheme.kt"
    ).write_text(
        """
package com.example.sample.theme

import androidx.compose.runtime.Composable

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    content()
}
""".lstrip(),
        encoding="utf-8",
    )
    return source


def tree_hashes(*roots: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = f"{root.name}/{path.relative_to(root).as_posix()}"
                hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def write_evidence(
    target: Path,
    run_root: Path,
    gate: str,
    target_revision: str,
    status: str = "passed",
    filename: str | None = None,
    started_at: str = "2026-07-24T12:00:00+00:00",
    slice_ids: list[str] | None = None,
    demand_ids: list[str] | None = None,
) -> str:
    del target_revision, started_at
    target = target.resolve()
    run_root = run_root.resolve()
    deveco_root = target.parent / "controlled-deveco"
    is_ui_run = gate == "ui_tests" and status != "blocked"
    if gate in {"build", "unit_tests"}:
        tool = deveco_root / "Contents/tools/hvigor/bin/hvigorw"
    elif is_ui_run:
        tool = (
            deveco_root
            / "Contents/sdk/default/openharmony/toolchains/hdc"
        )
    else:
        tool = deveco_root / "Contents/tools/xdevice/bin/xdevice"
    tool.parent.mkdir(parents=True, exist_ok=True)
    tool.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import sys

arguments = sys.argv[1:]
hdc_arguments = arguments
if len(hdc_arguments) >= 2 and hdc_arguments[0] == "-t":
    hdc_arguments = hdc_arguments[2:]
if pathlib.Path(sys.argv[0]).name == "hdc" and hdc_arguments[:2] == ["install", "-r"]:
    print("install bundle successfully.")
    sys.exit(0)
if pathlib.Path(sys.argv[0]).name == "hdc" and hdc_arguments[:3] == ["shell", "aa", "test"]:
    print(
        "start ability successfully.\\n"
        "OHOS_REPORT_SUM: 1\\n"
        "OHOS_REPORT_STATUS: class=DemoUiTest\\n"
        "OHOS_REPORT_STATUS: class=DemoUiTest\\n"
        "OHOS_REPORT_STATUS: current=1\\n"
        "OHOS_REPORT_STATUS: id=JS\\n"
        "OHOS_REPORT_STATUS: numtests=1\\n"
        "OHOS_REPORT_STATUS: stream=\\n"
        "OHOS_REPORT_STATUS: test=opensDemo\\n"
        "OHOS_REPORT_STATUS_CODE: 1\\n"
        "OHOS_REPORT_STATUS: class=DemoUiTest\\n"
        "OHOS_REPORT_STATUS: current=1\\n"
        "OHOS_REPORT_STATUS: id=JS\\n"
        "OHOS_REPORT_STATUS: numtests=1\\n"
        "OHOS_REPORT_STATUS: stream=\\n"
        "OHOS_REPORT_STATUS: test=opensDemo\\n"
        "OHOS_REPORT_STATUS_CODE: 0\\n"
        "OHOS_REPORT_STATUS: consuming=20\\n"
        "OHOS_REPORT_STATUS: class=DemoUiTest\\n"
        "OHOS_REPORT_STATUS: suiteconsuming=20\\n"
        "OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0\\n"
        "OHOS_REPORT_CODE: 0\\n"
        "OHOS_REPORT_STATUS: taskconsuming=20\\n"
        "TestFinished-ResultCode: 0\\n"
        "TestFinished-ResultMsg: your test finished!!!\\n"
        "user test finished."
    )
    sys.exit(int(os.environ.get("MIGRATION_TEST_HDC_EXIT", "0")))
if "--report-out" in sys.argv:
    output = pathlib.Path(sys.argv[sys.argv.index("--report-out") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"/>\\n',
        encoding="utf-8",
    )
if "--artifact-out" in sys.argv:
    output = pathlib.Path(sys.argv[sys.argv.index("--artifact-out") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(("test-hap:" + " ".join(sys.argv)).encode("utf-8"))
sys.exit(7 if "--fail" in sys.argv else 0)
""",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    name = filename or gate
    report = target / ".migration/test-results" / f"{name}.xml"
    output_artifact = target / ".migration/test-outputs" / f"{name}.hap"
    ui_main_hap = target / ".migration/test-outputs" / f"{name}-main.hap"
    ui_test_hap = target / ".migration/test-outputs" / f"{name}-test.hap"
    if is_ui_run:
        ui_main_hap.parent.mkdir(parents=True, exist_ok=True)
        ui_main_hap.write_bytes(b"main-hap")
        ui_test_hap.write_bytes(b"test-hap")
    if gate in {"device_test", "visual_review"} and status != "blocked":
        mode = "record"
    else:
        mode = "probe" if status == "blocked" else "run"
    arguments = [
        mode,
        "--target",
        str(target),
        "--run-root",
        str(run_root),
        "--gate",
        gate,
        "--name",
        name,
    ]
    for slice_id in slice_ids or ["test-slice"]:
        arguments.extend(("--slice-id", slice_id))
    for demand_id in demand_ids or ["demand:test"]:
        arguments.extend(("--demand-id", demand_id))
    if gate == "unit_tests" and status != "blocked":
        arguments.extend(
            (
                "--test-report",
                str(report),
                "--test-report-format",
                "junit",
            )
        )
    if is_ui_run:
        arguments.extend(
            (
                "--test-report-from-stdout",
                "--test-report-format",
                "hypium-text",
                "--ui-main-hap",
                str(ui_main_hap),
                "--ui-test-hap",
                str(ui_test_hap),
            )
        )
    if gate == "build":
        arguments.extend(("--output-artifact", str(output_artifact)))
    if gate in {"ui_tests", "device_test"}:
        arguments.extend(
            (
                "--device-kind",
                "emulator",
                "--device-id",
                "test-emulator",
                "--os-version",
                "HarmonyOS 6.0",
                "--api-version",
                "24",
            )
        )
    if gate == "device_test" and status != "blocked":
        arguments.extend(
            (
                "--record-status",
                status,
                "--scenario-step",
                "Launch the migrated demand",
                "--scenario-step",
                "Verify result",
                "--expected",
                "Demand behavior is preserved",
                "--actual",
                "Demand behavior is preserved",
                "--provider",
                "QA Zhang",
                "--provider-kind",
                "human",
            )
        )
    if gate == "visual_review":
        arguments.extend(
            (
                "--record-status",
                status,
                "--actual",
                "The code-defined layout matches the authorized reference.",
                "--notes",
                "Reviewed locally without exposing image bytes to the model.",
                "--evidence-owner",
                "Li Hua",
            )
        )
    if status == "blocked":
        arguments.extend(
            (
                "--blocker",
                "No online signed device",
                "--next-action",
                "Connect an emulator and rerun",
            )
        )
    if is_ui_run:
        command = [
            str(tool),
            "-t",
            "test-emulator",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.test",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
            "-s",
            "timeout",
            "60000",
        ]
    else:
        action = {
            "build": "assembleHap",
            "unit_tests": "test",
            "ui_tests": "run",
            "device_test": "run",
        }.get(gate)
        command = (
            [str(tool), action]
            if action is not None and mode != "record"
            else []
        )
        if gate == "unit_tests" and status != "blocked":
            command.extend(("--report-out", str(report)))
        if gate == "build":
            command.extend(("--artifact-out", str(output_artifact)))
        if command and status in {"blocked", "failed"}:
            command.append("--fail")
    command_arguments = ("--", *command) if command else ()
    environment = os.environ.copy()
    environment["DEVECO_HOME"] = str(deveco_root)
    environment["DEVECO_SDK_HOME"] = str(deveco_root / "Contents/sdk")
    environment["MIGRATION_TEST_HDC_EXIT"] = (
        "7" if is_ui_run and status == "failed" else "0"
    )
    result = run_script(
        EVIDENCE_RUNNER,
        *arguments,
        *command_arguments,
        environment=environment,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)["evidence"]


def target_revision(target: Path) -> str:
    result = run_script(HASH_TARGET, "--target", str(target))
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)["manifest_hash"]


def write_inventory_reconciliation(target: Path, run_root: Path) -> None:
    state = json.loads(
        (run_root / "agent-state.json").read_text(encoding="utf-8")
    )
    payload = {
        "schema": "android-to-harmony.inventory-reconciliation.v1",
        "status": "authoritative",
        "all_snapshot_files_reviewed": True,
        "snapshot_manifest_sha256": state["artifacts"][
            "snapshot_manifest_sha256"
        ],
        "contract_sha256": state["artifacts"]["contract_sha256"],
        "reviewer": "forward-test-agent",
        "reviewed_at": "2026-07-24T12:01:00+00:00",
    }
    (target / ".migration/inventory-reconciliation.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def assert_capability_artifacts(
    test_case: unittest.TestCase,
    result: dict[str, object],
    run_root: Path,
) -> None:
    capability_artifacts = result["capability_artifacts"]
    test_case.assertTrue(capability_artifacts["current"])
    test_case.assertEqual(capability_artifacts["status"], "current")
    test_case.assertGreater(capability_artifacts["node_count"], 0)
    test_case.assertGreaterEqual(capability_artifacts["fact_pack_count"], 1)
    paths = capability_artifacts["paths"]
    for key in (
        "skill_tree_manifest",
        "capability_graph",
        "fact_pack_dir",
        "review_queue",
        "gate_evidence_bundle",
        "gate_report",
        "execution_plan",
        "execution_task_state",
    ):
        test_case.assertTrue(
            Path(paths[key]).exists(),
            f"missing capability artifact {key}",
        )
    test_case.assertIsInstance(capability_artifacts["plan_identity"], str)
    test_case.assertIsInstance(capability_artifacts["task_state_identity"], str)
    test_case.assertEqual(
        Path(paths["capability_graph"]).resolve(),
        (run_root / "capability-graph.json").resolve(),
    )
    graph = json.loads(
        (run_root / "capability-graph.json").read_text(encoding="utf-8")
    )
    test_case.assertEqual(
        graph["schema"],
        "android-to-harmony.capability-graph.v1",
    )
    report = json.loads(
        (run_root / "gate-report.json").read_text(encoding="utf-8")
    )
    test_case.assertEqual(
        report["schema"],
        "android-to-harmony.gate-report.v1",
    )
    bundle = json.loads(
        (run_root / "gate-evidence-bundle.json").read_text(encoding="utf-8")
    )
    test_case.assertEqual(
        bundle["schema"],
        "android-to-harmony.gate-evidence-bundle.v1",
    )
    manifest = json.loads(
        (run_root / "skill-tree-manifest.json").read_text(encoding="utf-8")
    )
    review_queue = json.loads(
        (run_root / "review-queue.json").read_text(encoding="utf-8")
    )
    execution_plan = json.loads(
        (run_root / "execution-plan.json").read_text(encoding="utf-8")
    )
    test_case.assertEqual(
        manifest["tree_sha256"],
        capability_artifacts["skill_tree_digest"],
    )
    test_case.assertEqual(
        review_queue["schema"],
        "android-to-harmony.review-queue.v1",
    )
    test_case.assertEqual(
        execution_plan["schema"],
        "android-to-harmony.execution-plan.v1",
    )


class MigrationAgentTests(unittest.TestCase):
    def test_capture_execution_plan_regressions_freezes_complete_banking_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reuse = create_compose_source(root / "reuse")
            subprocess.run(["git", "init", "-q", str(reuse)], check=True)
            subprocess.run(
                ["git", "-C", str(reuse), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(reuse), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(reuse), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(reuse), "commit", "-qm", "fixture"],
                check=True,
            )
            source_url = "https://github.com/alexandr7035/Banking-App-Mock-Compose.git"
            subprocess.run(
                ["git", "-C", str(reuse), "remote", "add", "origin", source_url],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(reuse), "rev-parse", "HEAD"],
                text=True,
            ).strip()
            change = root / "change"
            evidence = change / "evidence"
            central = evidence / "skill-identities"
            central.mkdir(parents=True)
            manifest = central / "bundled-skill-tree-manifest.json"
            binding = central / "repo-skill-binding.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.skill-tree-manifest.v1",
                        "local_root": "skills/migrate-android-compose-to-harmony",
                        "file_count": 1,
                        "tree_sha256": "a" * 64,
                        "files": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            binding.write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.repo-skill-binding.v1",
                        "bundled_skill_path": "skills/migrate-android-compose-to-harmony",
                        "manifest_path": "skill-identities/bundled-skill-tree-manifest.json",
                        "bundled_tree_sha256": "a" * 64,
                        "file_count": 1,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            subtree = evidence / "execution-plan-dag-v1/banking"
            captured = run_script(
                CAPTURE_EXECUTION_PLAN,
                "--change-dir",
                str(change),
                "--project",
                "banking",
                "--source-url",
                source_url,
                "--expected-revision",
                revision,
                "--source-dir",
                str(evidence / "sources/banking/source"),
                "--reuse-candidate",
                str(reuse),
                "--project-name",
                "BankingExecutionPlanDag",
                "--bundle-name",
                "com.specsuperflow.banking.executionplandag",
                "--run-root",
                str(subtree / "run-root"),
                "--target-dir",
                str(subtree / "target"),
                "--evidence-subtree",
                str(subtree),
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            payload = json.loads(captured.stdout)
            self.assertEqual(payload["source_revision"], revision)
            required = [
                "contract/migration-contract.json",
                "capability-graph.json",
                "fact-packs",
                "review-queue.json",
                "gate-report.json",
                "execution-plan.json",
                "frozen-task-state.json",
                "logs/01-start.stdout.txt",
                "logs/01-start.stderr.txt",
                "logs/01-start.command.log",
                "logs/02-status.stdout.txt",
                "logs/02-status.stderr.txt",
                "logs/02-status.command.log",
                "exit/01-start.exit.json",
                "exit/02-status.exit.json",
                "tests/start-status.test.log",
                "skill-identity-reference.json",
                "source-identity.json",
            ]
            for relative in required:
                self.assertTrue((subtree / relative).exists(), relative)
            reference = json.loads(
                (subtree / "skill-identity-reference.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                reference["manifest_sha256"],
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                reference["binding_sha256"],
                hashlib.sha256(binding.read_bytes()).hexdigest(),
            )
            source_identity = json.loads(
                (subtree / "source-identity.json").read_text(encoding="utf-8")
            )
            self.assertEqual(source_identity["remote_url"], source_url)
            self.assertEqual(source_identity["revision"], revision)

            unknown = run_script(CAPTURE_EXECUTION_PLAN, "--command", "echo unsafe")
            self.assertNotEqual(unknown.returncode, 0)

    def test_capture_execution_plan_regressions_rejects_wrong_banking_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "remote", "add", "origin", "https://example.com/wrong.git"],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                text=True,
            ).strip()
            change = root / "change"
            change.mkdir()
            subtree = change / "evidence/execution-plan-dag-v1/banking"
            rejected = run_script(
                CAPTURE_EXECUTION_PLAN,
                "--change-dir",
                str(change),
                "--project",
                "banking",
                "--source-url",
                "https://github.com/alexandr7035/Banking-App-Mock-Compose.git",
                "--expected-revision",
                revision,
                "--source-dir",
                str(source),
                "--project-name",
                "BankingExecutionPlanDag",
                "--bundle-name",
                "com.specsuperflow.banking.executionplandag",
                "--run-root",
                str(subtree / "run-root"),
                "--target-dir",
                str(subtree / "target"),
                "--evidence-subtree",
                str(subtree),
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("remote", rejected.stdout)
    def test_validator_rejects_resigned_legacy_ui_evidence_without_installs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            target = target.resolve()
            revision = target_revision(target)
            reference = write_evidence(
                target,
                run_root,
                "ui_tests",
                revision,
            )
            evidence_path = target / reference
            evidence = json.loads(
                evidence_path.read_text(encoding="utf-8")
            )
            for field in (
                "test_invocation",
                "installed_haps",
                "test_command_executed",
            ):
                evidence.pop(field)
            evidence.pop("attestation")
            secret = load_ownership_secret(target)
            self.assertIsNotNone(secret)
            attach_attestation(evidence, target, secret)
            evidence_path.write_text(
                json.dumps(evidence, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(migration_agent.OrchestrationError):
                migration_agent.validate_evidence_record(
                    evidence_path,
                    target,
                )

    def test_validator_rejects_resigned_ui_install_binding_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            target = target.resolve()
            revision = target_revision(target)
            reference = write_evidence(
                target,
                run_root,
                "ui_tests",
                revision,
            )
            evidence_path = target / reference
            pristine = json.loads(
                evidence_path.read_text(encoding="utf-8")
            )
            migration_agent.validate_evidence_record(evidence_path, target)
            command_log_path = target / pristine["artifact"]
            report_path = target / pristine["test_report"]["path"]
            original_command_log = command_log_path.read_bytes()
            original_report = report_path.read_bytes()
            secret = load_ownership_secret(target)
            self.assertIsNotNone(secret)

            def wrong_invocation_device(evidence: dict[str, object]) -> None:
                evidence["test_invocation"]["device_id"] = "other-device"

            def wrong_install_device(evidence: dict[str, object]) -> None:
                evidence["installed_haps"][0]["argv"][2] = "other-device"
                evidence["installed_haps"][0]["command"] = shlex.join(
                    evidence["installed_haps"][0]["argv"]
                )

            def wrong_post_install_hash(evidence: dict[str, object]) -> None:
                evidence["installed_haps"][0][
                    "post_install_sha256"
                ] = "0" * 64

            def skipped_test_command(evidence: dict[str, object]) -> None:
                evidence["test_command_executed"] = False

            def wrong_report_source(evidence: dict[str, object]) -> None:
                evidence["test_report"]["source_kind"] = "file"

            def tampered_report_content(evidence: dict[str, object]) -> None:
                report_path.write_bytes(b"not a Hypium report\n")
                evidence["test_report"]["sha256"] = hashlib.sha256(
                    report_path.read_bytes()
                ).hexdigest()
                evidence["test_report"]["size"] = report_path.stat().st_size

            def tampered_command_log(evidence: dict[str, object]) -> None:
                command_log_path.write_text(
                    "test_command_executed=false\n"
                    "[Fail][E005003] Install HAP failed\n",
                    encoding="utf-8",
                )
                evidence["artifact_sha256"] = hashlib.sha256(
                    command_log_path.read_bytes()
                ).hexdigest()
                evidence["artifact_size"] = (
                    command_log_path.stat().st_size
                )

            mutations = {
                "invocation device": wrong_invocation_device,
                "install device": wrong_install_device,
                "post-install hash": wrong_post_install_hash,
                "test command skipped": skipped_test_command,
                "report source": wrong_report_source,
                "report content": tampered_report_content,
                "command log": tampered_command_log,
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    command_log_path.write_bytes(original_command_log)
                    report_path.write_bytes(original_report)
                    evidence = json.loads(json.dumps(pristine))
                    mutate(evidence)
                    evidence.pop("attestation")
                    attach_attestation(evidence, target, secret)
                    evidence_path.write_text(
                        json.dumps(evidence, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(
                        migration_agent.OrchestrationError
                    ):
                        migration_agent.validate_evidence_record(
                            evidence_path,
                            target,
                        )

    def test_verified_slice_requires_every_demand_on_every_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            slices = target / ".migration/slices"
            slices.mkdir(parents=True)
            references: list[str] = []
            evidence: dict[str, dict[str, object]] = {}
            for gate in SLICE_GATES:
                reference = f".migration/evidence/{gate}-first.json"
                references.append(reference)
                evidence[reference] = {
                    "gate": gate,
                    "status": "passed",
                    "slice_ids": ["tasks"],
                    "demand_ids": ["tasks-list"],
                }
            ledger_path = slices / "tasks.json"
            ledger = {
                "schema": "android-to-harmony.slice-ledger.v1",
                "id": "tasks",
                "batch_id": "features",
                "status": "verified",
                "source_files": ["Tasks.kt"],
                "demand_ids": ["tasks-list", "tasks-loading"],
                "required_gates": list(SLICE_GATES),
                "evidence": references,
            }
            ledger_path.write_text(
                json.dumps(ledger, indent=2) + "\n",
                encoding="utf-8",
            )

            incomplete = migration_agent.collect_slice_progress(
                target,
                [{"id": "features", "source_files": ["Tasks.kt"]}],
                evidence,
            )
            self.assertEqual(incomplete[0], [])
            self.assertIn(
                "slice_ledger",
                [item["gate"] for item in incomplete[4]],
            )

            for gate in SLICE_GATES:
                reference = f".migration/evidence/{gate}-second.json"
                references.append(reference)
                evidence[reference] = {
                    "gate": gate,
                    "status": "passed",
                    "slice_ids": ["tasks"],
                    "demand_ids": ["tasks-loading"],
                }
            ledger["evidence"] = references
            ledger_path.write_text(
                json.dumps(ledger, indent=2) + "\n",
                encoding="utf-8",
            )
            complete = migration_agent.collect_slice_progress(
                target,
                [{"id": "features", "source_files": ["Tasks.kt"]}],
                evidence,
            )
            self.assertEqual(
                [item["id"] for item in complete[0]],
                ["tasks"],
            )
            self.assertEqual(complete[4], [])

    def test_start_creates_owned_resumable_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"

            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
                "--sdk-version",
                "6.1.1(24)",
            )

            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            result = json.loads(started.stdout)
            self.assertTrue(result["ok"])
            self.assertEqual(result["next_phase"], "implement_and_verify_slice")
            self.assertTrue((run_root / "snapshot").is_dir())
            self.assertTrue((run_root / "migration-contract.json").is_file())
            self.assertTrue((target / ".migration/state.json").is_file())

            state = json.loads(
                (run_root / "agent-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                state["schema"], "android-to-harmony.agent-state.v1"
            )
            self.assertEqual(
                state["generator"], "migrate-android-compose-to-harmony"
            )
            self.assertEqual(state["ownership"]["run_root"], str(run_root.resolve()))
            self.assertEqual(state["paths"]["source"], str(source.resolve()))
            self.assertEqual(state["paths"]["target"], str(target.resolve()))
            self.assertEqual(state["project"]["sdk_version"], "6.1.1(24)")
            self.assertIn(
                '"targetSdkVersion": "6.1.1(24)"',
                (target / "build-profile.json5").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                state["inventory"]["status"], "candidate_requires_review"
            )
            self.assertFalse(state["inventory"]["authoritative"])
            assert_capability_artifacts(self, result, run_root)

    def test_claim_target_ownership_upgrades_a_validated_legacy_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            target_state_path = target / ".migration/state.json"
            target_state = json.loads(
                target_state_path.read_text(encoding="utf-8")
            )
            target_state.pop("ownership")
            target_state_path.write_text(
                json.dumps(target_state, indent=2) + "\n",
                encoding="utf-8",
            )
            target_key = hashlib.sha256(
                str(target.resolve()).encode("utf-8")
            ).hexdigest()
            ownership_record = (
                target.parent
                / ".android-to-harmony-ownership"
                / f"{target_key}.json"
            )
            ownership_record.unlink()

            before = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(before.returncode, 0, before.stdout)
            before_status = json.loads(before.stdout)
            self.assertFalse(before_status["target"]["ownership_ready"])
            self.assertIn(
                "target_ownership",
                [item["gate"] for item in before_status["pending_gates"]],
            )

            claimed = run_agent(
                "claim-target-ownership",
                "--run-root",
                str(run_root),
            )
            self.assertEqual(claimed.returncode, 0, claimed.stdout)
            self.assertTrue(json.loads(claimed.stdout)["changed"])
            repeated = run_agent(
                "claim-target-ownership",
                "--run-root",
                str(run_root),
            )
            self.assertEqual(repeated.returncode, 0, repeated.stdout)
            self.assertFalse(json.loads(repeated.stdout)["changed"])

            after = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(after.returncode, 0, after.stdout)
            after_status = json.loads(after.stdout)
            self.assertTrue(after_status["target"]["ownership_ready"])
            self.assertNotIn(
                "target_ownership",
                [item["gate"] for item in after_status["pending_gates"]],
            )

    def test_claim_target_ownership_repairs_only_record_permissions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            target_state_path = target / ".migration/state.json"
            original_state = target_state_path.read_bytes()
            target_key = hashlib.sha256(
                str(target.resolve()).encode("utf-8")
            ).hexdigest()
            ownership_record = (
                target.parent
                / ".android-to-harmony-ownership"
                / f"{target_key}.json"
            )
            original_record = ownership_record.read_bytes()
            ownership_record.chmod(0o644)

            claimed = run_agent(
                "claim-target-ownership",
                "--run-root",
                str(run_root),
            )

            self.assertEqual(claimed.returncode, 0, claimed.stdout)
            result = json.loads(claimed.stdout)
            self.assertTrue(result["changed"])
            self.assertTrue(result["ownership_ready"])
            self.assertEqual(ownership_record.read_bytes(), original_record)
            self.assertEqual(
                ownership_record.stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(target_state_path.read_bytes(), original_state)

    def test_resume_and_status_report_pending_work_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            before = tree_hashes(run_root, target)

            status_result = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(
                status_result.returncode,
                0,
                status_result.stdout + status_result.stderr,
            )
            status = json.loads(status_result.stdout)
            self.assertEqual(
                status["inventory"]["status"], "candidate_requires_review"
            )
            self.assertTrue(status["inventory"]["candidate"])
            self.assertFalse(status["inventory"]["authoritative"])
            self.assertEqual(status["verified_slices"], [])
            self.assertGreater(len(status["pending_batches"]), 0)
            self.assertEqual(status["blocked_gates"], [])
            self.assertGreater(len(status["next_executable_tasks"]), 0)
            self.assertEqual(status["blocked_tasks"], [])
            self.assertTrue(status["target"]["scaffold_only"])
            self.assertFalse(status["complete"])
            assert_capability_artifacts(self, status, run_root)

            resumed_result = run_agent("resume", "--run-root", str(run_root))
            self.assertEqual(
                resumed_result.returncode,
                0,
                resumed_result.stdout + resumed_result.stderr,
            )
            resumed = json.loads(resumed_result.stdout)
            self.assertEqual(
                resumed["pending_batches"], status["pending_batches"]
            )
            self.assertEqual(resumed["next_phase"], status["next_phase"])
            self.assertEqual(
                resumed["next_executable_tasks"],
                status["next_executable_tasks"],
            )
            self.assertEqual(resumed["blocked_tasks"], status["blocked_tasks"])
            assert_capability_artifacts(self, resumed, run_root)
            self.assertEqual(tree_hashes(run_root, target), before)

    def test_status_marks_execution_plan_artifact_stale_when_persisted_plan_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            plan_path = run_root / "execution-plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["next_executable_tasks"] = []
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            status_result = run_agent("status", "--run-root", str(run_root))
            self.assertNotEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertFalse(status["ok"])
            self.assertEqual(status["failed_stage"], "execution_plan")
            self.assertIn(
                "execution plan identity does not match canonical immutable payload",
                status["error"],
            )

    def test_resume_rejects_tampered_gate_report_identity_and_executable_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)

            gate_report_path = run_root / "gate-report.json"
            gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
            gate_report["nodes"] = gate_report["nodes"][:-1]
            gate_report_path.write_text(
                json.dumps(gate_report, indent=2) + "\n",
                encoding="utf-8",
            )

            resumed = run_agent("resume", "--run-root", str(run_root))
            self.assertNotEqual(resumed.returncode, 0, resumed.stdout)
            payload = json.loads(resumed.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["failed_stage"], "execution_plan")
            self.assertIn("gate report", payload["error"])

    def test_resume_unlocks_downstream_tasks_after_prerequisite_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            task_state_path = run_root / "execution-task-state.json"
            task_state = json.loads(task_state_path.read_text(encoding="utf-8"))
            pending_task_ids = [
                task_id
                for task_id, record in task_state["tasks"].items()
                if record["status"] == "pending"
            ]
            ready_task_ids = [
                task_id
                for task_id, record in task_state["tasks"].items()
                if record["status"] == "ready"
            ]
            self.assertGreater(len(pending_task_ids), 0)
            self.assertGreater(len(ready_task_ids), 0)
            for task_id in ready_task_ids:
                task_state["tasks"][task_id]["status"] = "completed"
            task_state["task_state_identity"] = hashlib.sha256(
                (
                    json.dumps(
                        {
                            "schema": task_state["schema"],
                            "plan_identity": task_state["plan_identity"],
                            "tasks": task_state["tasks"],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            task_state_path.write_text(
                json.dumps(task_state, indent=2) + "\n",
                encoding="utf-8",
            )
            resumed = run_agent("resume", "--run-root", str(run_root))
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            payload = json.loads(resumed.stdout)
            self.assertTrue(set(payload["next_executable_tasks"]).issuperset(set(pending_task_ids)))

    def test_task_state_updates_do_not_change_execution_plan_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            started_payload = json.loads(started.stdout)
            task_state_path = run_root / "execution-task-state.json"
            task_state = json.loads(task_state_path.read_text(encoding="utf-8"))
            first_task_id = sorted(task_state["tasks"])[0]
            task_state["tasks"][first_task_id]["status"] = "completed"
            task_state["task_state_identity"] = hashlib.sha256(
                (
                    json.dumps(
                        {
                            "schema": task_state["schema"],
                            "plan_identity": task_state["plan_identity"],
                            "tasks": task_state["tasks"],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            task_state_path.write_text(
                json.dumps(task_state, indent=2) + "\n",
                encoding="utf-8",
            )
            status = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            payload = json.loads(status.stdout)
            self.assertEqual(payload["plan_identity"], started_payload["plan_identity"])
            self.assertNotEqual(payload["task_state_identity"], started_payload["task_state_identity"])

    def test_start_resume_and_status_preserve_execution_plan_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            started_payload = json.loads(started.stdout)
            resumed = run_agent("resume", "--run-root", str(run_root))
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            resumed_payload = json.loads(resumed.stdout)
            status = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(started_payload["plan_identity"], resumed_payload["plan_identity"])
            self.assertEqual(started_payload["plan_identity"], status_payload["plan_identity"])
            self.assertEqual(started_payload["task_state_identity"], resumed_payload["task_state_identity"])
            self.assertEqual(started_payload["task_state_identity"], status_payload["task_state_identity"])
            self.assertEqual(started_payload["next_executable_tasks"], resumed_payload["next_executable_tasks"])
            self.assertEqual(started_payload["next_executable_tasks"], status_payload["next_executable_tasks"])

    def test_start_resume_and_status_expose_current_execution_plan_and_task_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            def canonical_plan_identity(projected_plan: dict[str, object]) -> str:
                payload = json.loads(json.dumps(projected_plan))
                payload.pop("plan_identity", None)
                return hashlib.sha256(
                    (
                        json.dumps(
                            payload,
                            indent=2,
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                ).hexdigest()

            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            started_payload = json.loads(started.stdout)
            started_plan = started_payload.get("execution_plan")
            started_task_state = started_payload.get("execution_task_state")
            self.assertIsInstance(started_plan, dict)
            self.assertIsInstance(started_task_state, dict)
            canonical_identity = canonical_plan_identity(started_plan)
            self.assertEqual(started_payload["plan_identity"], canonical_identity)
            self.assertEqual(started_plan["plan_identity"], started_payload["plan_identity"])
            self.assertEqual(
                started_task_state["task_state_identity"],
                started_payload["task_state_identity"],
            )
            self.assertEqual(
                started_task_state["plan_identity"],
                started_payload["plan_identity"],
            )
            self.assertEqual(
                started_plan,
                json.loads((run_root / "execution-plan.json").read_text(encoding="utf-8")),
            )
            self.assertEqual(
                started_task_state,
                json.loads(
                    (run_root / "execution-task-state.json").read_text(encoding="utf-8")
                ),
            )
            self.assertNotIn("seed_task_states", started_plan)
            self.assertNotIn("task_views", started_plan)
            self.assertNotIn("next_executable_tasks", started_plan)
            self.assertNotIn("blocked_tasks", started_plan)
            for task_state in started_task_state["tasks"].values():
                self.assertIn(task_state["status"], {"ready", "pending", "blocked", "completed"})
            for task in started_plan["tasks"]:
                self.assertNotIn("status", task)
            blocked_fixture = json.loads(json.dumps(started_plan))
            blocked_fixture["seed_task_states"] = {
                task_id: {"status": "blocked"}
                for task_id in started_task_state["tasks"]
            }
            blocked_fixture["next_executable_tasks"] = []
            blocked_fixture["blocked_tasks"] = sorted(started_task_state["tasks"])
            blocked_fixture["task_views"] = []
            blocked_fixture["tasks"][0]["status"] = "blocked"
            blocked_fixture["plan_identity"] = "stale-identity"
            projected_blocked_fixture = migration_agent.project_immutable_execution_plan(
                blocked_fixture
            )
            blocked_fixture_identity = canonical_plan_identity(
                projected_blocked_fixture
            )
            self.assertEqual(
                projected_blocked_fixture["plan_identity"],
                blocked_fixture_identity,
            )
            self.assertEqual(blocked_fixture_identity, canonical_identity)
            self.assertNotIn("seed_task_states", projected_blocked_fixture)
            self.assertNotIn("task_views", projected_blocked_fixture)
            self.assertNotIn("next_executable_tasks", projected_blocked_fixture)
            self.assertNotIn("blocked_tasks", projected_blocked_fixture)
            for task in projected_blocked_fixture["tasks"]:
                self.assertNotIn("status", task)

            ready_task_ids = list(started_payload["next_executable_tasks"])
            self.assertGreater(len(ready_task_ids), 0)
            task_state_path = run_root / "execution-task-state.json"
            updated_task_state = json.loads(
                task_state_path.read_text(encoding="utf-8")
            )
            updated_task_state["tasks"][ready_task_ids[0]]["status"] = "completed"
            updated_task_state["task_state_identity"] = migration_agent.sha256_bytes(
                (
                    json.dumps(
                        migration_agent.task_state_identity_payload(updated_task_state),
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8")
            )
            task_state_path.write_text(
                json.dumps(updated_task_state, indent=2) + "\n",
                encoding="utf-8",
            )
            expected_joined = migration_agent.join_execution_plan_state(
                started_plan,
                updated_task_state,
            )

            resumed = run_agent("resume", "--run-root", str(run_root))
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            resumed_payload = json.loads(resumed.stdout)
            status = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            status_payload = json.loads(status.stdout)
            for payload in (resumed_payload, status_payload):
                self.assertEqual(payload["execution_plan"], started_plan)
                self.assertEqual(payload["plan_identity"], started_payload["plan_identity"])
                self.assertEqual(payload["execution_plan"]["plan_identity"], started_payload["plan_identity"])
                self.assertNotIn("seed_task_states", payload["execution_plan"])
                self.assertNotIn("task_views", payload["execution_plan"])
                self.assertNotIn("next_executable_tasks", payload["execution_plan"])
                self.assertNotIn("blocked_tasks", payload["execution_plan"])
                for task in payload["execution_plan"]["tasks"]:
                    self.assertNotIn("status", task)
                self.assertEqual(
                    payload["execution_task_state"],
                    json.loads(task_state_path.read_text(encoding="utf-8")),
                )
                self.assertEqual(
                    payload["task_state_identity"],
                    payload["execution_task_state"]["task_state_identity"],
                )
                self.assertNotEqual(
                    payload["task_state_identity"],
                    started_payload["task_state_identity"],
                )
                self.assertEqual(
                    payload["execution_task_state"]["plan_identity"],
                    started_payload["plan_identity"],
                )
                self.assertEqual(
                    payload["next_executable_tasks"],
                    expected_joined["next_executable_tasks"],
                )
                self.assertEqual(
                    payload["blocked_tasks"],
                    expected_joined["blocked_tasks"],
                )

    def test_migration_agent_rejects_stale_input_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            task_state_path = run_root / "execution-task-state.json"
            original_task_state = json.loads(task_state_path.read_text(encoding="utf-8"))
            task_state = json.loads(json.dumps(original_task_state))
            task_state["task_state_identity"] = "bad-state"
            task_state_path.write_text(json.dumps(task_state, indent=2) + "\n", encoding="utf-8")
            status = run_agent("status", "--run-root", str(run_root))
            self.assertNotEqual(status.returncode, 0)
            payload = json.loads(status.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["failed_stage"], "execution_plan")
            self.assertEqual(payload.get("next_executable_tasks"), None)

    def test_resume_rejects_tampered_snapshot_without_overwriting_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            migrated_page = target / "entry/src/main/ets/pages/Index.ets"
            migrated_page.write_text(
                "@Entry\n@Component\nstruct MigratedPage {}\n",
                encoding="utf-8",
            )
            snapshot_source = (
                run_root
                / "snapshot/app/src/main/java/com/example/sample/MainActivity.kt"
            )
            snapshot_source.write_text(
                snapshot_source.read_text(encoding="utf-8") + "\n// tampered\n",
                encoding="utf-8",
            )

            resumed = run_agent("resume", "--run-root", str(run_root))

            self.assertNotEqual(resumed.returncode, 0)
            result = json.loads(resumed.stdout)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failed_stage"], "validate_snapshot")
            self.assertEqual(
                migrated_page.read_text(encoding="utf-8"),
                "@Entry\n@Component\nstruct MigratedPage {}\n",
            )

    def test_resume_rejects_missing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            (run_root / "migration-contract.json").unlink()

            resumed = run_agent("resume", "--run-root", str(run_root))

            self.assertNotEqual(resumed.returncode, 0)
            result = json.loads(resumed.stdout)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failed_stage"], "validate_contract")
            self.assertIn("missing or changed", result["error"])

    def test_start_refuses_existing_unowned_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            run_root.mkdir()
            sentinel = run_root / "keep.txt"
            sentinel.write_text("do not replace", encoding="utf-8")

            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )

            self.assertNotEqual(started.returncode, 0)
            result = json.loads(started.stdout)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failed_stage"], "preflight")
            self.assertIn("not owned", result["error"])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")
            self.assertFalse((run_root / "agent-state.json").exists())
            self.assertFalse(target.exists())

    def test_start_rolls_back_new_paths_when_intake_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"

            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "invalid",
            )

            self.assertNotEqual(started.returncode, 0)
            self.assertFalse(run_root.exists())
            self.assertFalse(target.exists())

    def test_status_rejects_verified_slice_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            contract = json.loads(
                (run_root / "migration-contract.json").read_text(encoding="utf-8")
            )
            batch = contract["migration_batches"][0]
            slices = target / ".migration/slices"
            slices.mkdir()
            (slices / "first.json").write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.slice-ledger.v1",
                        "id": "first-slice",
                        "batch_id": batch["id"],
                        "status": "verified",
                        "source_files": batch["source_files"],
                        "demand_ids": ["demand:first"],
                        "required_gates": list(SLICE_GATES),
                    }
                ),
                encoding="utf-8",
            )

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertEqual(status["verified_slices"], [])
            self.assertIn(
                batch["id"],
                [item["id"] for item in status["pending_batches"]],
            )
            self.assertIn(
                "slice_ledger",
                [item["gate"] for item in status["blocked_gates"]],
            )
            self.assertEqual(status["next_phase"], "resolve_blocked_gate")
            self.assertTrue(status["target"]["scaffold_only"])
            self.assertFalse(status["complete"])

    def test_status_reports_evidenced_slice_and_blocked_device_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            contract = json.loads(
                (run_root / "migration-contract.json").read_text(encoding="utf-8")
            )
            batch = contract["migration_batches"][0]
            slices = target / ".migration/slices"
            slices.mkdir()
            evidence_refs = [
                ".migration/evidence/build.json",
                ".migration/evidence/unit_tests.json",
                ".migration/evidence/ui_tests.json",
                ".migration/evidence/device_test.json",
            ]
            (slices / "first.json").write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.slice-ledger.v1",
                        "id": "first-slice",
                        "batch_id": batch["id"],
                        "status": "implemented",
                        "source_files": batch["source_files"],
                        "demand_ids": ["demand:first"],
                        "required_gates": list(SLICE_GATES),
                        "evidence": evidence_refs,
                    }
                ),
                encoding="utf-8",
            )
            migrated_page = target / "entry/src/main/ets/pages/Index.ets"
            migrated_page.write_text(
                migrated_page.read_text(encoding="utf-8") + "\n// migrated\n",
                encoding="utf-8",
            )
            revision = target_revision(target)
            write_evidence(
                target,
                run_root,
                "build",
                revision,
                slice_ids=["first-slice"],
                demand_ids=["demand:first"],
            )
            write_evidence(
                target,
                run_root,
                "unit_tests",
                revision,
                slice_ids=["first-slice"],
                demand_ids=["demand:first"],
            )
            ui_evidence_reference = write_evidence(
                target,
                run_root,
                "ui_tests",
                revision,
                slice_ids=["first-slice"],
                demand_ids=["demand:first"],
            )
            ui_evidence = json.loads(
                (target / ui_evidence_reference).read_text(encoding="utf-8")
            )
            self.assertEqual(
                ui_evidence["runner_type"],
                "harmony_ui_device_runner",
            )
            self.assertEqual(
                ui_evidence["test_report"]["source_kind"],
                "command_stdout",
            )
            self.assertTrue(ui_evidence["test_command_executed"])
            self.assertEqual(
                [
                    (installed["role"], installed["status"])
                    for installed in ui_evidence["installed_haps"]
                ],
                [("main", "passed"), ("test", "passed")],
            )
            self.assertEqual(ui_evidence["execution_status"], "executed")
            write_evidence(
                target,
                run_root,
                "device_test",
                revision,
                status="blocked",
                slice_ids=["first-slice"],
                demand_ids=["demand:first"],
            )

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertEqual(status["verified_slices"], [])
            self.assertEqual(
                [item["id"] for item in status["implemented_slices"]],
                ["first-slice"],
            )
            self.assertNotIn(
                batch["id"],
                [item["id"] for item in status["pending_batches"]],
            )
            self.assertIn(
                "device_test",
                [item["gate"] for item in status["blocked_gates"]],
            )
            self.assertFalse(status["target"]["scaffold_only"])
            self.assertFalse(status["complete"])

    def test_status_reaches_complete_only_with_reconciled_current_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            contract = json.loads(
                (run_root / "migration-contract.json").read_text(encoding="utf-8")
            )
            slices = target / ".migration/slices"
            slices.mkdir()
            evidence_refs = [
                ".migration/evidence/build.json",
                ".migration/evidence/unit_tests.json",
                ".migration/evidence/ui_tests-unrelated.json",
                ".migration/evidence/device_test.json",
            ]
            slice_ids = [
                f"slice-{index}"
                for index, _batch in enumerate(contract["migration_batches"])
            ]
            for index, batch in enumerate(contract["migration_batches"]):
                (slices / f"slice-{index}.json").write_text(
                    json.dumps(
                        {
                            "schema": "android-to-harmony.slice-ledger.v1",
                            "id": f"slice-{index}",
                            "batch_id": batch["id"],
                            "status": "verified",
                            "source_files": batch["source_files"],
                            "demand_ids": ["demand:complete"],
                            "required_gates": list(SLICE_GATES),
                            "evidence": evidence_refs,
                            "human_visual_check_required": index == 0,
                        }
                    ),
                    encoding="utf-8",
                )
            migrated_page = target / "entry/src/main/ets/pages/Index.ets"
            migrated_page.write_text(
                migrated_page.read_text(encoding="utf-8") + "\n// migrated\n",
                encoding="utf-8",
            )
            write_inventory_reconciliation(target, run_root)
            revision = target_revision(target)
            for gate in ("build", "unit_tests", "device_test"):
                write_evidence(
                    target,
                    run_root,
                    gate,
                    revision,
                    slice_ids=slice_ids,
                    demand_ids=["demand:complete"],
                )
            write_evidence(
                target,
                run_root,
                "ui_tests",
                revision,
                filename="ui_tests-unrelated",
                slice_ids=["unrelated-slice"],
                demand_ids=["demand:unrelated"],
            )

            unrelated_result = run_agent(
                "status",
                "--run-root",
                str(run_root),
            )
            self.assertEqual(
                unrelated_result.returncode,
                0,
                unrelated_result.stdout,
            )
            unrelated_status = json.loads(unrelated_result.stdout)
            self.assertFalse(unrelated_status["complete"])
            self.assertEqual(unrelated_status["verified_slices"], [])
            self.assertIn(
                "slice_ledger",
                [item["gate"] for item in unrelated_status["blocked_gates"]],
            )

            for index, _batch in enumerate(contract["migration_batches"]):
                ledger_path = slices / f"slice-{index}.json"
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                ledger["status"] = "implemented"
                ledger.pop("evidence", None)
                ledger_path.write_text(
                    json.dumps(ledger, indent=2) + "\n",
                    encoding="utf-8",
                )
            implemented_revision = target_revision(target)
            for gate in EVIDENCE_GATES:
                write_evidence(
                    target,
                    run_root,
                    gate,
                    implemented_revision,
                    filename=f"{gate}-final",
                    slice_ids=slice_ids,
                    demand_ids=["demand:complete"],
                )
            for index, _batch in enumerate(contract["migration_batches"]):
                ledger_path = slices / f"slice-{index}.json"
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                ledger["status"] = "verified"
                ledger["evidence"] = [
                    ".migration/evidence/build-final.json",
                    ".migration/evidence/unit_tests-final.json",
                    ".migration/evidence/ui_tests-final.json",
                    ".migration/evidence/device_test-final.json",
                ]
                ledger_path.write_text(
                    json.dumps(ledger, indent=2) + "\n",
                    encoding="utf-8",
                )
            self.assertEqual(target_revision(target), implemented_revision)

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertTrue(status["inventory"]["authoritative"], status)
            self.assertEqual(status["pending_batches"], [])
            self.assertEqual(status["pending_gates"], [])
            self.assertEqual(status["blocked_gates"], [])
            self.assertEqual(status["next_phase"], "complete")
            self.assertTrue(status["complete"])

            artifact = (
                target / ".migration/evidence/artifacts/ui_tests-final.log"
            )
            artifact.write_text("tampered artifact\n", encoding="utf-8")
            tampered_result = run_agent(
                "status",
                "--run-root",
                str(run_root),
            )
            self.assertEqual(tampered_result.returncode, 0, tampered_result.stdout)
            tampered_status = json.loads(tampered_result.stdout)
            self.assertFalse(tampered_status["complete"])
            self.assertIn(
                "evidence",
                [item["gate"] for item in tampered_status["blocked_gates"]],
            )

    def test_build_outputs_do_not_make_scaffold_look_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            for relative in (
                ".hvigor/cache.bin",
                "entry/build/generated.bin",
                "oh_modules/cache.bin",
                ".migration/evidence/build.log",
            ):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("generated\n", encoding="utf-8")

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertTrue(status["target"]["scaffold_only"])

    def test_handwritten_evidence_and_wrong_gate_command_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            revision = target_revision(target)
            relative = write_evidence(
                target,
                run_root,
                "build",
                revision,
                filename="forged",
            )
            record_path = target / relative
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record.pop("attestation")
            artifact = target / record["artifact"]
            artifact.write_text("placeholder: trust me\n", encoding="utf-8")
            record["artifact_sha256"] = hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest()
            record_path.write_text(
                json.dumps(record, indent=2) + "\n",
                encoding="utf-8",
            )

            status_result = run_agent("status", "--run-root", str(run_root))
            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertFalse(status["complete"])
            self.assertIn(
                "evidence",
                [item["gate"] for item in status["blocked_gates"]],
            )

            wrong_main_hap = (
                target.resolve()
                / ".migration/test-outputs/wrong-gate-main.hap"
            )
            wrong_test_hap = (
                target.resolve()
                / ".migration/test-outputs/wrong-gate-test.hap"
            )
            wrong_main_hap.parent.mkdir(parents=True, exist_ok=True)
            wrong_main_hap.write_bytes(b"wrong-main-hap")
            wrong_test_hap.write_bytes(b"wrong-test-hap")
            wrong_gate = run_script(
                EVIDENCE_RUNNER,
                "run",
                "--target",
                str(target.resolve()),
                "--run-root",
                str(run_root.resolve()),
                "--gate",
                "ui_tests",
                "--name",
                "build-cannot-be-ui",
                "--slice-id",
                "test-slice",
                "--demand-id",
                "demand:test",
                "--device-kind",
                "emulator",
                "--device-id",
                "test-emulator",
                "--os-version",
                "HarmonyOS 6.0",
                "--api-version",
                "24",
                "--test-report-from-stdout",
                "--test-report-format",
                "hypium-text",
                "--ui-main-hap",
                str(wrong_main_hap),
                "--ui-test-hap",
                str(wrong_test_hap),
                "--",
                str(
                    target.resolve().parent
                    / "controlled-deveco/Contents/tools/hvigor/bin/hvigorw"
                ),
                "assembleHap",
                environment={
                    **os.environ,
                    "DEVECO_HOME": str(
                        target.resolve().parent / "controlled-deveco"
                    ),
                    "DEVECO_SDK_HOME": str(
                        target.resolve().parent
                        / "controlled-deveco/Contents/sdk"
                    ),
                },
            )
            self.assertNotEqual(wrong_gate.returncode, 0)
            self.assertIn("command argv", wrong_gate.stdout)

    def test_latest_current_evidence_supersedes_stale_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            old_revision = target_revision(target)
            for gate in EVIDENCE_GATES:
                write_evidence(
                    target,
                    run_root,
                    gate,
                    old_revision,
                    filename=f"{gate}-old",
                )
            page = target / "entry/src/main/ets/pages/Index.ets"
            page.write_text(
                page.read_text(encoding="utf-8") + "\n// current revision\n",
                encoding="utf-8",
            )
            current_revision = target_revision(target)
            for gate in EVIDENCE_GATES:
                write_evidence(
                    target,
                    run_root,
                    gate,
                    current_revision,
                    filename=f"{gate}-new",
                    started_at="2026-07-24T13:00:00+00:00",
                )

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            self.assertEqual(status["blocked_gates"], [])
            self.assertEqual(
                status["latest_evidence"],
                {gate: "passed" for gate in EVIDENCE_GATES},
            )

    def test_latest_stale_evidence_blocks_instead_of_using_older_pass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            revision = target_revision(target)
            write_evidence(
                target,
                run_root,
                "build",
                revision,
                filename="build-old",
            )
            page = target / "entry/src/main/ets/pages/Index.ets"
            page.write_text(
                page.read_text(encoding="utf-8") + "\n// makes evidence stale\n",
                encoding="utf-8",
            )

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertEqual(status_result.returncode, 0, status_result.stdout)
            status = json.loads(status_result.stdout)
            build_blockers = [
                item
                for item in status["blocked_gates"]
                if item["gate"] == "build"
            ]
            self.assertEqual(len(build_blockers), 1)
            self.assertIn("stale", build_blockers[0]["reason"])

    def test_status_rejects_symlinked_target_migration_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)
            external = root / "external-migration"
            (target / ".migration").rename(external)
            (target / ".migration").symlink_to(external, target_is_directory=True)

            status_result = run_agent("status", "--run-root", str(run_root))

            self.assertNotEqual(status_result.returncode, 0)
            status = json.loads(status_result.stdout)
            self.assertEqual(status["failed_stage"], "validate_target")
            self.assertIn("symbolic link", status["error"])

    def test_status_and_resume_reject_tampered_asset_ledger_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = create_compose_source(root)
            run_root = root / "migration-run"
            target = root / "HarmonySample"
            started = run_agent(
                "start",
                "--source",
                str(source),
                "--run-root",
                str(run_root),
                "--target",
                str(target),
                "--project-name",
                "Harmony Sample",
                "--bundle-name",
                "com.example.harmonysample",
            )
            self.assertEqual(started.returncode, 0, started.stdout)

            asset = target / "entry/src/main/resources/base/media/icon.png"
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(b"approved-image")
            (target / ".migration/assets.json").write_text(
                json.dumps(
                    {
                        "schema": "android-to-harmony.asset-ledger.v1",
                        "assets": {
                            asset.relative_to(target).as_posix(): {
                                "asset_path": "app/src/main/res/drawable/icon.png",
                                "bytes": asset.stat().st_size,
                                "destination_sha256": hashlib.sha256(
                                    asset.read_bytes()
                                ).hexdigest(),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            valid_revision = target_revision(target)
            self.assertTrue(valid_revision.startswith("sha256:"))

            asset.write_bytes(b"tampered-image")
            for command in ("status", "resume"):
                result = run_agent(command, "--run-root", str(run_root))
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertEqual(
                    payload["failed_stage"],
                    "validate_target_revision",
                )
                self.assertIn(
                    "asset ledger",
                    payload["error"],
                )


if __name__ == "__main__":
    unittest.main()
