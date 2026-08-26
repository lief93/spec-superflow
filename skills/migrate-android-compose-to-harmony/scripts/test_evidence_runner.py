#!/usr/bin/env python3
"""Security and truthfulness tests for the controlled evidence runner."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import migration_agent
from evidence_attestation import (
    OWNERSHIP_DIRECTORY,
    OWNERSHIP_KIND,
    OWNERSHIP_REFERENCE_SCHEMA,
    OWNERSHIP_SCHEMA,
    classify_argv,
    classify_probe_argv,
    has_valid_attestation,
    ownership_record_path,
)
from evidence_runner import (
    RunnerError,
    extract_hypium_report_from_aa_stdout,
    parse_hypium_text_report,
)


SCRIPTS = Path(__file__).resolve().parent
RUNNER = SCRIPTS / "evidence_runner.py"
FAKE_TOOL = """#!/usr/bin/env python3
import pathlib
import sys

arguments = sys.argv[1:]

def option(name):
    if name not in arguments:
        return None
    return arguments[arguments.index(name) + 1]

report = option("--write-report")
if report is not None:
    path = pathlib.Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0"/>\\n',
        encoding="utf-8",
    )

hypium = option("--write-hypium")
if hypium is not None:
    path = pathlib.Path(hypium)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "class=Demo\\n"
        "test=first\\n"
        "result=Success\\n"
        "test=second\\n"
        "result=Success\\n"
        "Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0\\n",
        encoding="utf-8",
    )

output = option("--write-output")
if output is not None:
    path = pathlib.Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("fresh:" + str(path.stat().st_mtime_ns if path.exists() else 0)).encode())

empty_output = option("--touch-output")
if empty_output is not None:
    path = pathlib.Path(empty_output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

if "--hdc-fail-marker" in arguments:
    print("[Fail][E001005] Device not found or connected")
if "stderrFailureMarker" in arguments:
    print(
        "  \\x1b[31m[Fail][E001005] Device not found or connected\\x1b[0m",
        file=sys.stderr,
    )

hdc_arguments = arguments
if len(hdc_arguments) >= 2 and hdc_arguments[0] == "-t":
    hdc_arguments = hdc_arguments[2:]
trace = pathlib.Path(sys.argv[0]).with_suffix(".trace")
with trace.open("a", encoding="utf-8") as stream:
    stream.write("\\t".join(arguments) + "\\n")
if pathlib.Path(sys.argv[0]).name == "hdc" and hdc_arguments[:2] == ["install", "-r"]:
    if "fail-install" in hdc_arguments[2]:
        print("[Fail][E005003] Install HAP failed")
        sys.exit(0)
    if "mutate-install" in hdc_arguments[2]:
        pathlib.Path(hdc_arguments[2]).write_bytes(b"mutated-hap")
    if "entry-ohosTest" in hdc_arguments[2]:
        print("install bundle successfully.")
    else:
        print(
            "[Info]App install path:/data/app/el1/bundle/public/"
            "com.example.evidence msg:install bundle successfully."
        )
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

exit_code = option("--exit")
print("controlled fake tool")
sys.exit(int(exit_code) if exit_code is not None else 0)
"""


def json_signature(payload: dict[str, object], target: Path, secret: str) -> str:
    message = json.dumps(
        {
            "kind": OWNERSHIP_KIND,
            "target_root": str(target),
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(bytes.fromhex(secret), message, hashlib.sha256).hexdigest()


class EvidenceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".evidence-runner-test-",
            dir=SCRIPTS,
        )
        self.root = Path(self.temporary.name)
        self.target = self.root / "target"
        self.run_root = self.root / "run"
        self.tools = self.root / "tools"
        self.deveco = self.root / "DevEco-Studio"
        self.sdk = self.deveco / "Contents/sdk"
        self.target.mkdir()
        self.run_root.mkdir()
        self.tools.mkdir()
        (self.target / ".migration").mkdir()
        required_files = (
            "build-profile.json5",
            "hvigorfile.ts",
            "oh-package.json5",
            "oh-package-lock.json5",
            "hvigor/hvigor-config.json5",
            "AppScope/app.json5",
            "AppScope/resources/base/element/string.json",
            "entry/build-profile.json5",
            "entry/hvigorfile.ts",
            "entry/oh-package.json5",
        )
        for relative in required_files:
            path = self.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        self.secret = "ab" * 32
        source = self.root / "source-not-read"
        snapshot = self.run_root / "snapshot"
        snapshot.mkdir()
        manifest_path = snapshot / ".android-to-harmony-safe.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.safe-snapshot.v1",
                    "snapshot_root": str(snapshot),
                    "source_root": str(source),
                }
            ),
            encoding="utf-8",
        )
        contract_path = self.run_root / "migration-contract.json"
        contract_payload = {
            "schema": "android-to-harmony.migration-contract.v1",
            "generator": "migrate-android-compose-to-harmony",
            "source": {
                "safe_snapshot_root": str(snapshot),
                "original_root": str(source),
            },
            "migration_batches": [{"id": "test-batch"}],
        }
        contract_path.write_text(
            json.dumps(contract_payload),
            encoding="utf-8",
        )
        contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
        contract_owner_path = self.run_root / "migration-contract.json.owner.json"
        contract_owner_path.write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.contract-owner.v1",
                    "generator": "migrate-android-compose-to-harmony",
                    "output_name": contract_path.name,
                    "contract_sha256": contract_hash,
                }
            ),
            encoding="utf-8",
        )

        ownership_directory = self.root / OWNERSHIP_DIRECTORY
        ownership_directory.mkdir(mode=0o700)
        ownership_path = ownership_record_path(self.target)
        ownership_path.write_text(
            json.dumps(
                {
                    "schema": OWNERSHIP_SCHEMA,
                    "kind": OWNERSHIP_KIND,
                    "target_root": str(self.target),
                    "secret": self.secret,
                }
            ),
            encoding="utf-8",
        )
        ownership_path.chmod(0o600)
        target_contract_payload = json.loads(json.dumps(contract_payload))
        target_contract_payload["source"]["safe_snapshot_root"] = (
            "<local-safe-snapshot>"
        )
        target_contract_payload["source"]["original_root"] = (
            "<local-android-source>"
        )
        target_contract_path = self.target / ".migration/source-contract.json"
        target_contract_path.write_text(
            json.dumps(target_contract_payload),
            encoding="utf-8",
        )
        target_state: dict[str, object] = {
            "schema": "android-to-harmony.project-state.v1",
            "generator": "migrate-android-compose-to-harmony",
            "project_name": "Evidence Test",
            "bundle_name": "com.example.evidence",
            "output_root": ".",
            "contract": {
                "copied_path": ".migration/source-contract.json",
                "sha256": hashlib.sha256(
                    target_contract_path.read_bytes()
                ).hexdigest(),
            },
        }
        target_state["ownership"] = {
            "schema": OWNERSHIP_REFERENCE_SCHEMA,
            "signature": json_signature(
                target_state.copy(),
                self.target,
                self.secret,
            ),
        }
        target_state_path = self.target / ".migration/state.json"
        target_state_path.write_text(
            json.dumps(target_state),
            encoding="utf-8",
        )
        (self.run_root / "agent-state.json").write_text(
            json.dumps(
                {
                    "schema": "android-to-harmony.agent-state.v1",
                    "generator": "migrate-android-compose-to-harmony",
                    "paths": {
                        "source": str(source),
                        "snapshot": str(snapshot),
                        "contract": str(contract_path),
                        "contract_owner": str(contract_owner_path),
                        "target": str(self.target),
                    },
                    "ownership": {
                        "schema": "android-to-harmony.run-ownership.v1",
                        "run_root": str(self.run_root),
                        "run_id": "test-run",
                    },
                    "artifacts": {
                        "snapshot_manifest_sha256": hashlib.sha256(
                            manifest_path.read_bytes()
                        ).hexdigest(),
                        "contract_sha256": contract_hash,
                        "contract_owner_sha256": hashlib.sha256(
                            contract_owner_path.read_bytes()
                        ).hexdigest(),
                        "target_state_path": str(target_state_path),
                    },
                    "project": {
                        "name": "Evidence Test",
                        "bundle_name": "com.example.evidence",
                    },
                    "batch_ids": ["test-batch"],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_tool(
        self,
        name: str,
        *,
        directory: Path | None = None,
        executable: bool = True,
    ) -> Path:
        if directory is not None:
            parent = directory
        elif name.casefold() in {"hvigorw", "hvigorw.bat", "hvigorw.cmd"}:
            parent = self.deveco / "Contents/tools/hvigor/bin"
        elif name.casefold() in {"xdevice", "xdevice.exe"}:
            parent = self.deveco / "Contents/tools/xdevice/bin"
        elif name.casefold() in {"hdc", "hdc.exe"}:
            parent = self.sdk / "default/openharmony/toolchains"
        else:
            parent = self.tools
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / name
        path.write_text(FAKE_TOOL, encoding="utf-8")
        path.chmod(0o755 if executable else 0o644)
        return path

    def runner_arguments(
        self,
        mode: str,
        gate: str,
        name: str,
        *extra: str,
    ) -> list[str]:
        return [
            mode,
            "--target",
            str(self.target),
            "--run-root",
            str(self.run_root),
            "--gate",
            gate,
            "--name",
            name,
            "--slice-id",
            "slice:test",
            "--demand-id",
            "demand:test",
            *extra,
        ]

    def run_runner(
        self,
        mode: str,
        gate: str,
        name: str,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["DEVECO_HOME"] = str(self.deveco)
        environment["DEVECO_SDK_HOME"] = str(self.sdk)
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                *self.runner_arguments(mode, gate, name, *extra),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def evidence(self, name: str) -> dict[str, object]:
        return json.loads(
            (self.target / f".migration/evidence/{name}.json").read_text(
                encoding="utf-8"
            )
        )

    def test_classifier_requires_task_at_the_defined_position(self) -> None:
        self.assertIsNotNone(
            classify_argv("build", ["/external/hvigorw", "assembleHap"])
        )
        self.assertIsNone(
            classify_argv(
                "build",
                ["/external/hvigorw", "--mode", "assembleHap"],
            )
        )
        self.assertIsNone(
            classify_argv(
                "ui_tests",
                ["/external/hvigorw", "assembleHap", "onDeviceTest"],
            )
        )
        self.assertIsNone(
            classify_probe_argv(
                "ui_tests",
                ["/external/hvigorw", "assembleHap"],
            )
        )
        self.assertIsNotNone(
            classify_probe_argv(
                "device_test",
                ["/external/hdc", "list", "targets"],
            )
        )

    def test_successful_unit_run_owns_fresh_junit_and_executable(self) -> None:
        tool = self.make_tool("hvigorw")
        report = self.target / "entry/build/results.xml"
        result = self.run_runner(
            "run",
            "unit_tests",
            "unit-fresh",
            "--test-report",
            str(report),
            "--",
            str(tool),
            "test",
            "--write-report",
            str(report),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("unit-fresh")
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["tests"]["passed"], 2)
        self.assertEqual(evidence["argv"][0], str(tool))
        self.assertEqual(evidence["executable"]["resolved_path"], str(tool))
        self.assertEqual(
            evidence["tool_origin"]["source_environment"],
            "DEVECO_HOME",
        )
        self.assertEqual(
            evidence["executable"]["sha256"],
            hashlib.sha256(tool.read_bytes()).hexdigest(),
        )
        owned_report = self.target / evidence["test_report"]["path"]
        self.assertTrue(owned_report.is_file())
        self.assertEqual(
            evidence["test_report"]["sha256"],
            hashlib.sha256(owned_report.read_bytes()).hexdigest(),
        )
        self.assertTrue(has_valid_attestation(evidence, self.target))

    def test_old_junit_is_quarantined_and_restored_when_not_regenerated(
        self,
    ) -> None:
        tool = self.make_tool("hvigorw")
        report = self.target / "entry/build/results.xml"
        report.parent.mkdir(parents=True)
        report.write_text(
            '<testsuite tests="99" failures="0" errors="0" skipped="0"/>',
            encoding="utf-8",
        )
        result = self.run_runner(
            "run",
            "unit_tests",
            "unit-stale",
            "--test-report",
            str(report),
            "--",
            str(tool),
            "test",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("unit-stale")
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["exit_code"], 0)
        self.assertEqual(evidence["tests"], {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        })
        self.assertEqual(evidence["test_report"]["status"], "missing")
        self.assertIn(
            "not generated",
            " ".join(evidence["validation_errors"]),
        )
        self.assertIn("tests=\"99\"", report.read_text(encoding="utf-8"))
        self.assertFalse(
            (self.target / ".migration/evidence/artifacts/unit-stale.junit.xml").exists()
        )

    def test_identical_report_content_is_accepted_when_command_recreates_it(
        self,
    ) -> None:
        tool = self.make_tool("hvigorw")
        report = self.target / "entry/build/results.xml"
        report.parent.mkdir(parents=True)
        expected = (
            '<testsuite tests="2" failures="0" errors="0" skipped="0"/>\n'
        )
        report.write_text(expected, encoding="utf-8")
        result = self.run_runner(
            "run",
            "unit_tests",
            "unit-identical",
            "--test-report",
            str(report),
            "--",
            str(tool),
            "test",
            "--write-report",
            str(report),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("unit-identical")
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(report.read_text(encoding="utf-8"), expected)

    def test_hypium_text_report_is_strictly_parsed_and_owned(self) -> None:
        tool = self.make_tool("hvigorw")
        report = self.target / "entry/.test/results/test_result.txt"
        result = self.run_runner(
            "run",
            "unit_tests",
            "unit-hypium",
            "--test-report",
            str(report),
            "--test-report-format",
            "hypium-text",
            "--",
            str(tool),
            "test",
            "--write-hypium",
            str(report),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("unit-hypium")
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["tests"]["passed"], 2)
        self.assertEqual(evidence["test_report"]["format"], "hypium-text")
        self.assertTrue(
            (
                self.target
                / ".migration/evidence/artifacts/unit-hypium.hypium.txt"
            ).is_file()
        )

        inconsistent = self.target / "bad-hypium.txt"
        inconsistent.write_text(
            "test=only\n"
            "result=Success\n"
            "Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RunnerError, "test/result pairs"):
            parse_hypium_text_report(inconsistent)

    def test_hdc_aa_stdout_is_strictly_converted_to_hypium(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=20\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=20\n"
            "TestFinished-ResultCode: 0\n"
            "user test finished.\n"
        )
        report = extract_hypium_report_from_aa_stdout(stdout)
        self.assertEqual(
            report.decode("utf-8"),
            "test=DemoUiTest#opensDemo\n"
            "result=Success\n"
            "Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0\n",
        )
        with self.assertRaisesRegex(RunnerError, "final summary"):
            extract_hypium_report_from_aa_stdout(
                stdout.replace("OHOS_REPORT_RESULT:", "MISSING_RESULT:")
            )
        with self.assertRaisesRegex(RunnerError, "summary counts"):
            extract_hypium_report_from_aa_stdout(
                stdout.replace("Pass: 1", "Pass: 0")
            )
        with self.assertRaisesRegex(RunnerError, "device failure marker"):
            extract_hypium_report_from_aa_stdout(
                "  \x1b[31m[Fail][E001005] Device not found\x1b[0m\n"
                + stdout
            )

    def test_hdc_aa_stdout_accepts_multiple_suite_sums(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=FirstSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=first\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=FirstSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=first\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=10\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=SecondSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=second\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=SecondSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=second\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=12\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 2, Failure: 0, "
            "Error: 0, Pass: 2, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=22\n"
            "TestFinished-ResultCode: 0\n"
            "user test finished.\n"
        )
        self.assertEqual(
            extract_hypium_report_from_aa_stdout(stdout).decode("utf-8"),
            "test=FirstSuite#first\n"
            "result=Success\n"
            "test=SecondSuite#second\n"
            "result=Success\n"
            "Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0\n",
        )

    def test_hdc_aa_stdout_accepts_error_only_report_code(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=ErrorSuite\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=raisesError\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=ErrorSuite\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=raisesError\n"
            "OHOS_REPORT_STATUS_CODE: -1\n"
            "OHOS_REPORT_STATUS: consuming=10\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, "
            "Error: 1, Pass: 0, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=10\n"
            "TestFinished-ResultCode: 0\n"
            "user test finished.\n"
        )
        self.assertEqual(
            extract_hypium_report_from_aa_stdout(stdout).decode("utf-8"),
            "test=ErrorSuite#raisesError\n"
            "result=Error\n"
            "Tests run: 1, Failure: 0, Error: 1, Pass: 0, Ignore: 0\n",
        )

    def test_hdc_aa_stdout_rejects_out_of_order_completion_markers(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=20\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, "
            "Error: 0, Pass: 1, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=20\n"
            "user test finished.\n"
            "TestFinished-ResultCode: 0\n"
        )
        with self.assertRaisesRegex(RunnerError, "markers are out of order"):
            extract_hypium_report_from_aa_stdout(stdout)

    def test_hdc_aa_stdout_rejects_events_outside_execution_window(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=DemoUiTest\n"
            "OHOS_REPORT_STATUS: numtests=1\n"
            "OHOS_REPORT_STATUS: test=opensDemo\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=20\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, "
            "Error: 0, Pass: 1, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=20\n"
            "TestFinished-ResultCode: 0\n"
            "user test finished.\n"
        )
        variants = {
            "late suite sum": stdout.replace(
                "OHOS_REPORT_SUM: 1\n",
                "",
            ).replace(
                "OHOS_REPORT_CODE: 0\n",
                "OHOS_REPORT_SUM: 1\nOHOS_REPORT_CODE: 0\n",
            ),
            "late class status": stdout.replace(
                "OHOS_REPORT_CODE: 0\n",
                "OHOS_REPORT_STATUS: class=LateSuite\n"
                "OHOS_REPORT_CODE: 0\n",
            ),
            "late skip reason": stdout.replace(
                "OHOS_REPORT_CODE: 0\n",
                "OHOS_REPORT_STATUS: skipReason=late\n"
                "OHOS_REPORT_CODE: 0\n",
            ),
            "case before start": stdout.replace(
                "start ability successfully.\n",
                "",
            ).replace(
                "OHOS_REPORT_STATUS_CODE: 1\n",
                "OHOS_REPORT_STATUS_CODE: 1\n"
                "start ability successfully.\n",
                1,
            ),
        }
        for label, invalid_stdout in variants.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    RunnerError,
                    "outside the execution window",
                ):
                    extract_hypium_report_from_aa_stdout(invalid_stdout)

    def test_hdc_aa_stdout_accepts_consistent_skip_spec_count(self) -> None:
        stdout = (
            "start ability successfully.\n"
            "OHOS_REPORT_SUM: 2\n"
            "OHOS_REPORT_STATUS: class=SkipSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=passes\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: class=SkipSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=passes\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: consuming=10\n"
            "OHOS_REPORT_STATUS: class=SkipSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=isSkipped\n"
            "OHOS_REPORT_STATUS_CODE: 1\n"
            "OHOS_REPORT_STATUS: skipReason=not supported\n"
            "OHOS_REPORT_STATUS: class=SkipSuite\n"
            "OHOS_REPORT_STATUS: numtests=2\n"
            "OHOS_REPORT_STATUS: test=isSkipped\n"
            "OHOS_REPORT_STATUS_CODE: 0\n"
            "OHOS_REPORT_STATUS: skipReason=not supported\n"
            "OHOS_REPORT_STATUS: consuming=0\n"
            "OHOS_REPORT_RESULT: stream=Tests run: 2, Failure: 0, "
            "Error: 0, Pass: 1, Ignore: 1, SkipSpec: 1\n"
            "OHOS_REPORT_CODE: 0\n"
            "OHOS_REPORT_STATUS: taskconsuming=10\n"
            "TestFinished-ResultCode: 0\n"
            "user test finished.\n"
        )
        self.assertEqual(
            extract_hypium_report_from_aa_stdout(stdout).decode("utf-8"),
            "test=SkipSuite#passes\n"
            "result=Success\n"
            "test=SkipSuite#isSkipped\n"
            "result=Ignore\n"
            "Tests run: 2, Failure: 0, Error: 0, Pass: 1, Ignore: 1\n",
        )
        with self.assertRaisesRegex(RunnerError, "SkipSpec count"):
            extract_hypium_report_from_aa_stdout(
                stdout.replace("SkipSpec: 1", "SkipSpec: 2")
            )

    def test_device_hdc_stdout_report_is_owned_and_device_bound(self) -> None:
        tool = self.make_tool("hdc")
        main_hap = self.target / "entry/build/default/entry-default.hap"
        test_hap = self.target / "entry/build/default/entry-ohosTest.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "device_test",
            "device-hdc-stdout",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
            "-s",
            "timeout",
            "60000",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("device-hdc-stdout")
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["tests"]["passed"], 1)
        self.assertEqual(evidence["execution_status"], "executed")
        self.assertEqual(evidence["test_report"]["source_kind"], "command_stdout")
        self.assertEqual(
            evidence["test_report"]["source"],
            evidence["artifact"],
        )
        self.assertEqual(
            [
                (
                    installed["role"],
                    installed["path"],
                    installed["sha256"],
                    installed["size"],
                    installed["exit_code"],
                )
                for installed in evidence["installed_haps"]
            ],
            [
                (
                    "main",
                    "entry/build/default/entry-default.hap",
                    hashlib.sha256(b"main-hap").hexdigest(),
                    len(b"main-hap"),
                    0,
                ),
                (
                    "test",
                    "entry/build/default/entry-ohosTest.hap",
                    hashlib.sha256(b"test-hap").hexdigest(),
                    len(b"test-hap"),
                    0,
                ),
            ],
        )
        trace_lines = tool.with_suffix(".trace").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(trace_lines), 3)
        self.assertIn(
            "\tinstall\t-r\tentry/build/default/entry-default.hap",
            trace_lines[0],
        )
        self.assertIn(
            "\tinstall\t-r\tentry/build/default/entry-ohosTest.hap",
            trace_lines[1],
        )
        self.assertIn("\tshell\taa\ttest\t", trace_lines[2])
        self.assertTrue(has_valid_attestation(evidence, self.target))

        mismatch = self.run_runner(
            "run",
            "ui_tests",
            "ui-hdc-device-mismatch",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "different-emulator",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
        )
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("device id", mismatch.stdout)
        self.assertFalse(
            (
                self.target
                / ".migration/evidence/ui-hdc-device-mismatch.json"
            ).exists()
        )

    def test_ui_hdc_stdout_rejects_device_failure_from_stderr(self) -> None:
        tool = self.make_tool("hdc")
        main_hap = self.target / "entry/build/default/entry-default.hap"
        test_hap = self.target / "entry/build/default/entry-ohosTest.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "ui_tests",
            "ui-hdc-stderr-failure",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
            "-s",
            "class",
            "stderrFailureMarker",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("ui-hdc-stderr-failure")
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["exit_code"], 0)
        self.assertEqual(evidence["test_report"]["status"], "invalid")
        self.assertIn(
            "device failure marker",
            " ".join(evidence["validation_errors"]),
        )
        self.assertNotIn("execution_status", evidence)

    def test_ui_hdc_install_failure_stops_before_test_execution(self) -> None:
        tool = self.make_tool("hdc")
        main_hap = self.target / "entry/build/default/fail-install-main.hap"
        test_hap = self.target / "entry/build/default/entry-ohosTest.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "ui_tests",
            "ui-hdc-install-failure",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("ui-hdc-install-failure")
        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["test_command_executed"])
        self.assertNotIn("execution_status", evidence)
        self.assertEqual(evidence["tests"]["passed"], 0)
        self.assertEqual(evidence["test_report"]["status"], "invalid")
        self.assertEqual(len(evidence["installed_haps"]), 1)
        self.assertEqual(evidence["installed_haps"][0]["role"], "main")
        self.assertEqual(evidence["installed_haps"][0]["status"], "failed")
        self.assertIn(
            "reported an HDC failure",
            " ".join(evidence["validation_errors"]),
        )
        trace_lines = tool.with_suffix(".trace").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(trace_lines), 1)
        self.assertIn("\tinstall\t-r\t", trace_lines[0])
        log = (
            self.target / evidence["artifact"]
        ).read_text(encoding="utf-8")
        self.assertIn("[install:main]", log)
        self.assertIn("[Fail][E005003] Install HAP failed", log)
        self.assertNotIn("[stdout]", log)

    def test_ui_hdc_test_hap_install_failure_stops_test_execution(self) -> None:
        tool = self.make_tool("hdc")
        main_hap = self.target / "entry/build/default/entry-default.hap"
        test_hap = self.target / "entry/build/default/fail-install-test.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "ui_tests",
            "ui-hdc-test-install-failure",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("ui-hdc-test-install-failure")
        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["test_command_executed"])
        self.assertNotIn("execution_status", evidence)
        self.assertEqual(
            [
                (installed["role"], installed["status"])
                for installed in evidence["installed_haps"]
            ],
            [("main", "passed"), ("test", "failed")],
        )
        self.assertIn(
            "test HAP install reported an HDC failure",
            evidence["validation_errors"],
        )
        trace_lines = tool.with_suffix(".trace").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(trace_lines), 2)
        self.assertTrue(
            all("\tinstall\t-r\t" in line for line in trace_lines)
        )

    def test_ui_hdc_rejects_hap_changed_during_install(self) -> None:
        tool = self.make_tool("hdc")
        main_hap = self.target / "entry/build/default/mutate-install-main.hap"
        test_hap = self.target / "entry/build/default/entry-ohosTest.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "ui_tests",
            "ui-hdc-mutated-install",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("ui-hdc-mutated-install")
        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["test_command_executed"])
        self.assertNotIn("execution_status", evidence)
        self.assertEqual(len(evidence["installed_haps"]), 1)
        installed = evidence["installed_haps"][0]
        self.assertEqual(installed["status"], "failed")
        self.assertNotEqual(
            installed["sha256"],
            installed["post_install_sha256"],
        )
        self.assertIn(
            "main HAP changed while it was installed",
            evidence["validation_errors"],
        )
        trace_lines = tool.with_suffix(".trace").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(trace_lines), 1)
        self.assertIn("\tinstall\t-r\t", trace_lines[0])
        consumed = migration_agent.validate_evidence_record(
            self.target / ".migration/evidence/ui-hdc-mutated-install.json",
            self.target,
        )
        self.assertEqual(consumed["status"], "failed")

    def test_ui_hdc_rejects_invalid_hap_inputs_before_execution(self) -> None:
        tool = self.make_tool("hdc")
        artifacts = self.target / "entry/build/default"
        artifacts.mkdir(parents=True, exist_ok=True)
        main_hap = artifacts / "entry-default.hap"
        test_hap = artifacts / "entry-ohosTest.hap"
        empty_hap = artifacts / "empty.hap"
        wrong_extension = artifacts / "entry-default.zip"
        outside_hap = self.root / "outside.hap"
        directory_hap = artifacts / "directory.hap"
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        empty_hap.touch()
        wrong_extension.write_bytes(b"not-a-hap")
        outside_hap.write_bytes(b"outside-hap")
        directory_hap.mkdir()
        cases = (
            ("same", main_hap, main_hap, "must be different"),
            ("empty", empty_hap, test_hap, "non-empty regular file"),
            (
                "missing",
                artifacts / "missing.hap",
                test_hap,
                "non-empty regular file",
            ),
            (
                "extension",
                wrong_extension,
                test_hap,
                "must be a HAP",
            ),
            ("outside", outside_hap, test_hap, "inside the target"),
            (
                "directory",
                directory_hap,
                test_hap,
                "must be a regular file",
            ),
        )
        for label, invalid_main, candidate_test, expected in cases:
            with self.subTest(label=label):
                evidence_name = f"ui-invalid-hap-{label}"
                result = self.run_runner(
                    "run",
                    "ui_tests",
                    evidence_name,
                    "--test-report-from-stdout",
                    "--test-report-format",
                    "hypium-text",
                    "--ui-main-hap",
                    str(invalid_main),
                    "--ui-test-hap",
                    str(candidate_test),
                    "--device-kind",
                    "emulator",
                    "--device-id",
                    "emulator-1",
                    "--os-version",
                    "HarmonyOS 6",
                    "--api-version",
                    "24",
                    "--",
                    str(tool),
                    "-t",
                    "emulator-1",
                    "shell",
                    "aa",
                    "test",
                    "-b",
                    "com.example.evidence",
                    "-m",
                    "entry_test",
                    "-s",
                    "unittest",
                    "OpenHarmonyTestRunner",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                self.assertFalse(
                    (
                        self.target
                        / f".migration/evidence/{evidence_name}.json"
                    ).exists()
                )
        self.assertFalse(tool.with_suffix(".trace").exists())

    def test_ui_run_rejects_file_report_device_runners(self) -> None:
        tool = self.make_tool("xdevice")
        report = self.target / "entry/build/ui-results.xml"
        result = self.run_runner(
            "run",
            "ui_tests",
            "ui-fresh",
            "--test-report",
            str(report),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "run",
            "--write-report",
            str(report),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controlled HDC stdout", result.stdout)
        self.assertFalse(report.exists())
        self.assertFalse(
            (self.target / ".migration/evidence/ui-fresh.json").exists()
        )

    def test_failed_test_command_records_real_exit_without_fake_count(self) -> None:
        tool = self.make_tool("hvigorw")
        report = self.target / "entry/build/missing.xml"
        result = self.run_runner(
            "run",
            "unit_tests",
            "unit-failed",
            "--test-report",
            str(report),
            "--",
            str(tool),
            "test",
            "--exit",
            "7",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("unit-failed")
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["exit_code"], 7)
        self.assertEqual(evidence["test_report"]["status"], "missing")
        self.assertEqual(evidence["tests"]["failed"], 0)

    def test_build_pass_requires_fresh_declared_hap(self) -> None:
        tool = self.make_tool("hvigorw")
        hap = self.target / "entry/build/default/app.hap"
        result = self.run_runner(
            "run",
            "build",
            "build-fresh",
            "--output-artifact",
            str(hap),
            "--",
            str(tool),
            "assembleHap",
            "--write-output",
            str(hap),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("build-fresh")
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(
            evidence["output_artifacts"],
            [
                {
                    "path": "entry/build/default/app.hap",
                    "sha256": hashlib.sha256(hap.read_bytes()).hexdigest(),
                    "size": hap.stat().st_size,
                }
            ],
        )

        stale_hap = self.target / "entry/build/default/stale.hap"
        stale_hap.write_bytes(b"old")
        stale = self.run_runner(
            "run",
            "build",
            "build-stale",
            "--output-artifact",
            str(stale_hap),
            "--",
            str(tool),
            "assembleHap",
        )
        self.assertEqual(stale.returncode, 0, stale.stdout + stale.stderr)
        stale_evidence = self.evidence("build-stale")
        self.assertEqual(stale_evidence["status"], "failed")
        self.assertEqual(stale_evidence["output_artifacts"], [])
        self.assertEqual(stale_hap.read_bytes(), b"old")

        touched_hap = self.target / "entry/build/default/touched.hap"
        touched_hap.write_bytes(b"old")
        touched = self.run_runner(
            "run",
            "build",
            "build-touched",
            "--output-artifact",
            str(touched_hap),
            "--",
            str(tool),
            "assembleHap",
            "--touch-output",
            str(touched_hap),
        )
        self.assertEqual(touched.returncode, 0, touched.stdout + touched.stderr)
        touched_evidence = self.evidence("build-touched")
        self.assertEqual(touched_evidence["status"], "failed")
        self.assertIn(
            "is empty",
            " ".join(touched_evidence["validation_errors"]),
        )

    def test_rejects_target_symlink_and_non_executable_tools_without_residue(
        self,
    ) -> None:
        in_target = self.make_tool(
            "hvigorw",
            directory=self.target / "local-tools",
        )
        output = self.target / "entry/build/app.hap"
        rejected = self.run_runner(
            "run",
            "build",
            "target-tool",
            "--output-artifact",
            str(output),
            "--",
            str(in_target),
            "assembleHap",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("outside target", rejected.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())

        real = self.make_tool("real-hvigorw")
        link_directory = self.root / "linked-tools"
        link_directory.mkdir()
        linked = link_directory / "hvigorw"
        linked.symlink_to(real)
        symlink_result = self.run_runner(
            "run",
            "build",
            "linked-tool",
            "--output-artifact",
            str(output),
            "--",
            str(linked),
            "assembleHap",
        )
        self.assertNotEqual(symlink_result.returncode, 0)
        self.assertIn("symbolic link", symlink_result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())

        non_executable = self.make_tool(
            "hvigorw",
            directory=self.root / "non-executable",
            executable=False,
        )
        nonexec_result = self.run_runner(
            "run",
            "build",
            "nonexec-tool",
            "--output-artifact",
            str(output),
            "--",
            str(non_executable),
            "assembleHap",
        )
        self.assertNotEqual(nonexec_result.returncode, 0)
        self.assertIn("not executable", nonexec_result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())

    def test_rejects_symlink_in_report_path_before_execution(self) -> None:
        tool = self.make_tool("hvigorw")
        outside = self.root / "outside"
        outside.mkdir()
        linked_parent = self.target / "linked-results"
        linked_parent.symlink_to(outside, target_is_directory=True)
        report = linked_parent / "result.xml"
        result = self.run_runner(
            "run",
            "unit_tests",
            "linked-report",
            "--test-report",
            str(report),
            "--",
            str(tool),
            "test",
            "--write-report",
            str(report),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symbolic link", result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())
        self.assertFalse((outside / "result.xml").exists())

    def test_device_and_visual_records_have_no_command_claim(self) -> None:
        device = self.run_runner(
            "record",
            "device_test",
            "device-record",
            "--record-status",
            "passed",
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--provider",
            "QA Zhang",
            "--provider-kind",
            "human",
            "--scenario-step",
            "Launch demand",
            "--expected",
            "Demand is usable",
            "--actual",
            "Demand is usable",
        )
        self.assertEqual(device.returncode, 0, device.stdout + device.stderr)
        device_evidence = self.evidence("device-record")
        self.assertEqual(device_evidence["status"], "passed")
        self.assertEqual(device_evidence["provider"], "QA Zhang")
        self.assertEqual(device_evidence["provider_kind"], "human")
        self.assertNotIn("argv", device_evidence)
        self.assertNotIn("command", device_evidence)

        visual = self.run_runner(
            "record",
            "visual_review",
            "visual-record",
            "--record-status",
            "failed",
            "--actual",
            "Spacing differs",
            "--notes",
            "Header needs adjustment",
            "--evidence-owner",
            "Li Hua",
        )
        self.assertEqual(visual.returncode, 0, visual.stdout + visual.stderr)
        visual_evidence = self.evidence("visual-record")
        self.assertEqual(visual_evidence["status"], "failed")
        self.assertEqual(visual_evidence["provider_kind"], "human")
        self.assertNotIn("device", visual_evidence)
        self.assertNotIn("argv", visual_evidence)

        automation = self.run_runner(
            "record",
            "visual_review",
            "fake-visual",
            "--record-status",
            "passed",
            "--actual",
            "Looks correct",
            "--notes",
            "Automated assertion",
            "--evidence-owner",
            "test automation",
        )
        self.assertNotEqual(automation.returncode, 0)
        self.assertIn("identify a human", automation.stdout)
        self.assertFalse(
            (self.target / ".migration/evidence/fake-visual.json").exists()
        )

        fake_device = self.run_runner(
            "record",
            "device_test",
            "fake-device",
            "--record-status",
            "passed",
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--provider",
            "test automation",
            "--provider-kind",
            "human",
            "--scenario-step",
            "Launch demand",
            "--expected",
            "Demand is usable",
            "--actual",
            "Demand is usable",
        )
        self.assertNotEqual(fake_device.returncode, 0)
        self.assertIn("identify a human", fake_device.stdout)
        self.assertFalse(
            (self.target / ".migration/evidence/fake-device.json").exists()
        )

    def test_untrusted_same_name_tool_cannot_attest_execution(self) -> None:
        tool = self.make_tool("hdc", directory=self.tools)
        main_hap = self.target / "entry/build/default/entry-default.hap"
        test_hap = self.target / "entry/build/default/entry-ohosTest.hap"
        main_hap.parent.mkdir(parents=True, exist_ok=True)
        main_hap.write_bytes(b"main-hap")
        test_hap.write_bytes(b"test-hap")
        result = self.run_runner(
            "run",
            "ui_tests",
            "untrusted-ui",
            "--test-report-from-stdout",
            "--test-report-format",
            "hypium-text",
            "--ui-main-hap",
            str(main_hap),
            "--ui-test-hap",
            str(test_hap),
            "--device-kind",
            "emulator",
            "--device-id",
            "emulator-1",
            "--os-version",
            "HarmonyOS 6",
            "--api-version",
            "24",
            "--",
            str(tool),
            "-t",
            "emulator-1",
            "shell",
            "aa",
            "test",
            "-b",
            "com.example.evidence",
            "-m",
            "entry_test",
            "-s",
            "unittest",
            "OpenHarmonyTestRunner",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trusted Harmony toolchain root", result.stdout)
        self.assertFalse(
            (self.target / ".migration/evidence/untrusted-ui.json").exists()
        )

    def test_probe_is_device_only_and_cannot_relabel_build(self) -> None:
        hdc = self.make_tool("hdc")
        result = self.run_runner(
            "probe",
            "ui_tests",
            "offline",
            "--blocker",
            "No online device",
            "--next-action",
            "Connect emulator",
            "--",
            str(hdc),
            "list",
            "targets",
            "--exit",
            "9",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.evidence("offline")
        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(evidence["probe_exit_code"], 9)
        self.assertEqual(
            evidence["probe_failure"],
            {"kind": "nonzero_exit", "exit_code": 9},
        )
        self.assertEqual(evidence["device"], "unavailable")

        marker_failure = self.run_runner(
            "probe",
            "ui_tests",
            "offline-marker",
            "--blocker",
            "No online device",
            "--next-action",
            "Connect emulator",
            "--",
            str(hdc),
            "list",
            "targets",
            "--hdc-fail-marker",
        )
        self.assertEqual(
            marker_failure.returncode,
            0,
            marker_failure.stdout + marker_failure.stderr,
        )
        marker_evidence = self.evidence("offline-marker")
        self.assertEqual(marker_evidence["status"], "blocked")
        self.assertEqual(marker_evidence["probe_exit_code"], 0)
        self.assertEqual(
            marker_evidence["probe_failure"],
            {
                "kind": "hdc_failure_marker",
                "code": "E001005",
                "message": "Device not found or connected",
            },
        )

        unexpected_success = self.run_runner(
            "probe",
            "device_test",
            "successful-probe",
            "--blocker",
            "Claimed unavailable",
            "--next-action",
            "Investigate",
            "--",
            str(hdc),
            "list",
            "targets",
        )
        self.assertNotEqual(unexpected_success.returncode, 0)
        self.assertIn("unexpectedly succeeded", unexpected_success.stdout)
        self.assertFalse(
            (
                self.target
                / ".migration/evidence/artifacts/successful-probe.log"
            ).exists()
        )
        self.assertFalse(
            list(
                (
                    self.target / ".migration/evidence/artifacts"
                ).glob(".successful-probe.run-*")
            )
        )

        hvigor = self.make_tool("hvigorw")
        build_as_ui = self.run_runner(
            "probe",
            "ui_tests",
            "fake-ui",
            "--blocker",
            "Unsigned",
            "--next-action",
            "Sign",
            "--",
            str(hvigor),
            "assembleHap",
            "--exit",
            "8",
        )
        self.assertNotEqual(build_as_ui.returncode, 0)
        self.assertIn("gate category", build_as_ui.stdout)
        self.assertFalse(
            (self.target / ".migration/evidence/fake-ui.json").exists()
        )

    def test_external_secret_without_target_marker_proof_is_insufficient(
        self,
    ) -> None:
        state_path = self.target / ".migration/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["ownership"]["signature"] = "00" * 32
        state_path.write_text(json.dumps(state), encoding="utf-8")
        tool = self.make_tool("hvigorw")
        output = self.target / "entry/build/app.hap"
        result = self.run_runner(
            "run",
            "build",
            "unowned",
            "--output-artifact",
            str(output),
            "--",
            str(tool),
            "assembleHap",
            "--write-output",
            str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ownership proof is invalid", result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())

    @unittest.skipIf(os.name == "nt", "POSIX ownership permissions")
    def test_world_readable_ownership_secret_is_rejected(self) -> None:
        ownership_record_path(self.target).chmod(0o644)
        tool = self.make_tool("hvigorw")
        output = self.target / "entry/build/app.hap"
        result = self.run_runner(
            "run",
            "build",
            "readable-secret",
            "--output-artifact",
            str(output),
            "--",
            str(tool),
            "assembleHap",
            "--write-output",
            str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no valid external ownership secret", result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())

    def test_tampered_owned_run_artifact_is_rejected(self) -> None:
        contract = self.run_root / "migration-contract.json"
        contract.write_text('{"tampered":true}\n', encoding="utf-8")
        tool = self.make_tool("hvigorw")
        output = self.target / "entry/build/app.hap"
        result = self.run_runner(
            "run",
            "build",
            "tampered-run",
            "--output-artifact",
            str(output),
            "--",
            str(tool),
            "assembleHap",
            "--write-output",
            str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("migration contract is missing or changed", result.stdout)
        self.assertFalse((self.target / ".migration/evidence").exists())


if __name__ == "__main__":
    unittest.main()
