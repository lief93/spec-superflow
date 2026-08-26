#!/usr/bin/env python3
"""Security regressions for model-visible snapshots and destructive retries."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
PREPARE = SCRIPTS / "prepare_safe_snapshot.py"
VALIDATE = SCRIPTS / "validate_ai_safe_tree.py"
INITIALIZE = SCRIPTS / "init_harmony_project.py"
ATTACH_CONTRACT = SCRIPTS / "attach_contract_to_target.py"


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def contract_fixture(source_root: Path, snapshot_root: Path) -> dict[str, object]:
    return {
        "schema": "android-to-harmony.migration-contract.v1",
        "source": {
            "safe_snapshot_root": str(snapshot_root),
            "original_root": str(source_root),
            "git": {"revision": "0123456789abcdef"},
        },
        "privacy": {
            "absolute_image_absence_proven": False,
            "embedded_image_scan": {"policy": "test", "status": "no_match"},
            "credential_literal_scan": {"policy": "test", "status": "no_match"},
        },
        "inventory": {
            "status": "candidate_requires_review",
            "authoritative": False,
            "text_file_count": 0,
            "gradle_modules": [],
        },
        "dependencies": [],
        "ui": {},
        "business": {},
        "platform_capabilities": [],
        "migration_batches": [],
        "risks": [],
        "completion_gates": ["Review candidate inventory"],
    }


class SecurityHardeningTests(unittest.TestCase):
    def test_rejects_common_normalized_credential_literals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "android"
            snapshot = root / "snapshot"
            source.mkdir()
            unsafe_files = {
                "PasswordCall.kt": 'password("literal-password")\n',
                "AwsSecret.kt": (
                    'val awsSecretAccessKey = "literal-aws-secret-value"\n'
                ),
                "CamelApiToken.kt": (
                    'val apiToken = "literal-api-token-value"\n'
                ),
                "KebabJson.json": (
                    '{"service-api-token":"literal-json-token-value"}\n'
                ),
                "ProviderToken.kt": (
                    'val token = "sk-proj-abcdefghijklmnopqrstuvwx"\n'
                ),
            }
            for relative, content in unsafe_files.items():
                (source / relative).write_text(content, encoding="utf-8")
            (source / "Safe.kt").write_text(
                'val apiToken = System.getenv("API_TOKEN")\n'
                'password(providers.gradleProperty("PASSWORD").get())\n',
                encoding="utf-8",
            )

            prepared = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )

            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            manifest = json.loads(
                (snapshot / ".android-to-harmony-safe.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                {entry["path"] for entry in manifest["blocked_files"]},
                set(unsafe_files),
            )
            self.assertTrue((snapshot / "Safe.kt").is_file())

            validated = run_script(VALIDATE, str(source))
            self.assertNotEqual(validated.returncode, 0)
            violations = json.loads(validated.stdout)["violations"]
            self.assertEqual(
                {
                    entry["path"]
                    for entry in violations
                    if entry["reason"] in {
                        "credential_literal",
                        "known_credential",
                    }
                },
                set(unsafe_files),
            )

    def test_rejects_signing_password_assignment_and_call_literals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "android"
            snapshot = root / "snapshot"
            source.mkdir()
            unsafe_files = {
                "KotlinAssignment.gradle.kts": (
                    'storePassword = "literal-store-password"\n'
                ),
                "KotlinCall.gradle.kts": (
                    'keyPassword("literal-key-password")\n'
                ),
                "GroovyAssignment.gradle": (
                    "keyPassword = 'groovy-key-password'\n"
                ),
                "GroovyCall.gradle": (
                    "storePassword 'groovy-store-password'\n"
                ),
            }
            for relative, content in unsafe_files.items():
                (source / relative).write_text(content, encoding="utf-8")
            (source / "Safe.gradle.kts").write_text(
                'storePassword = providers.gradleProperty("STORE_PASSWORD").orNull\n'
                'keyPassword(System.getenv("KEY_PASSWORD"))\n',
                encoding="utf-8",
            )

            prepared = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )

            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            manifest = json.loads(
                (snapshot / ".android-to-harmony-safe.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                {entry["path"] for entry in manifest["blocked_files"]},
                set(unsafe_files),
            )
            self.assertTrue((snapshot / "Safe.gradle.kts").is_file())

            validated = run_script(VALIDATE, str(source))
            self.assertNotEqual(validated.returncode, 0)
            violations = json.loads(validated.stdout)["violations"]
            self.assertEqual(
                {
                    entry["path"]
                    for entry in violations
                    if entry["reason"] == "credential_literal"
                },
                set(unsafe_files),
            )

    def test_rejects_sensitive_build_config_field_literals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "android"
            snapshot = root / "snapshot"
            source.mkdir()
            unsafe_files = {
                "KotlinApiKey.gradle.kts": (
                    'buildConfigField("String", "BACKEND_API_KEY", '
                    '"\\"literal-api-key\\"")\n'
                ),
                "KotlinSecret.gradle.kts": (
                    'buildConfigField(\n'
                    '    "String",\n'
                    '    "CLIENT_SECRET",\n'
                    '    "\\"literal-client-secret\\""\n'
                    ')\n'
                ),
                "GroovyToken.gradle": (
                    "buildConfigField 'String', 'ACCESS_TOKEN', "
                    '\'"literal-access-token"\'\n'
                ),
                "GroovyPassword.gradle": (
                    "buildConfigField('String', 'SERVICE_PASSWORD', "
                    '\'"literal-password"\')\n'
                ),
            }
            for relative, content in unsafe_files.items():
                (source / relative).write_text(content, encoding="utf-8")
            (source / "Safe.gradle.kts").write_text(
                'buildConfigField("String", "BACKEND_API_KEY", '
                'providers.gradleProperty("API_KEY").get())\n'
                'buildConfigField("String", "PUBLIC_URL", '
                '"\\"https://example.test\\"")\n'
                'buildConfigField("Int", "TOKEN_COUNT", "10")\n',
                encoding="utf-8",
            )

            prepared = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )

            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            manifest = json.loads(
                (snapshot / ".android-to-harmony-safe.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                {entry["path"] for entry in manifest["blocked_files"]},
                set(unsafe_files),
            )
            self.assertTrue((snapshot / "Safe.gradle.kts").is_file())

            validated = run_script(VALIDATE, str(source))
            self.assertNotEqual(validated.returncode, 0)
            violations = json.loads(validated.stdout)["violations"]
            self.assertEqual(
                {
                    entry["path"]
                    for entry in violations
                    if entry["reason"] == "credential_literal"
                },
                set(unsafe_files),
            )

    def test_rejects_contiguous_base64_surrounded_by_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "android"
            snapshot = root / "snapshot"
            source.mkdir()
            encoded = base64.b64encode(bytes(range(256)) * 2).decode("ascii")
            (source / "Wrapped.kt").write_text(
                f"val opaque = ({encoded});\n",
                encoding="utf-8",
            )
            (source / "Threshold.kt").write_text(
                f'val shortValue = "{"A" * 255}"\n',
                encoding="utf-8",
            )

            prepared = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )

            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            manifest = json.loads(
                (snapshot / ".android-to-harmony-safe.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["blocked_files"],
                [{"path": "Wrapped.kt", "reason": "embedded_image_payload"}],
            )
            self.assertTrue((snapshot / "Threshold.kt").is_file())
            self.assertNotIn(encoded, prepared.stdout)

            validated = run_script(VALIDATE, str(source))
            self.assertNotEqual(validated.returncode, 0)
            violations = json.loads(validated.stdout)["violations"]
            self.assertIn(
                {"path": "Wrapped.kt", "reason": "long_base64_payload"},
                violations,
            )
            self.assertNotIn(
                {"path": "Threshold.kt", "reason": "long_base64_payload"},
                violations,
            )

    def test_attach_allows_symlink_above_normalized_target_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real_parent = root / "real-parent"
            target = real_parent / "HarmonyFixture"
            real_parent.mkdir()
            initialized = run_script(
                INITIALIZE,
                "--output",
                str(target),
                "--project-name",
                "HarmonyFixture",
                "--bundle-name",
                "com.example.harmonyfixture",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)

            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    contract_fixture(root / "android", root / "snapshot")
                ),
                encoding="utf-8",
            )
            alias = root / "linked-parent"
            alias.symlink_to(real_parent, target_is_directory=True)
            attached = run_script(
                ATTACH_CONTRACT,
                "--contract",
                str(contract),
                "--target",
                str(alias / target.name),
            )

            self.assertEqual(attached.returncode, 0, attached.stdout)
            self.assertTrue(
                (target / ".migration/source-contract.json").is_file()
            )

    def test_attach_rejects_symlinked_migration_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "HarmonyFixture"
            initialized = run_script(
                INITIALIZE,
                "--output",
                str(target),
                "--project-name",
                "HarmonyFixture",
                "--bundle-name",
                "com.example.harmonyfixture",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    contract_fixture(root / "android", root / "snapshot")
                ),
                encoding="utf-8",
            )
            real_migration = root / "external-migration"
            (target / ".migration").rename(real_migration)
            (target / ".migration").symlink_to(
                real_migration,
                target_is_directory=True,
            )
            state_path = real_migration / "state.json"
            original_state = state_path.read_bytes()

            attached = run_script(
                ATTACH_CONTRACT,
                "--contract",
                str(contract),
                "--target",
                str(target),
            )

            self.assertNotEqual(attached.returncode, 0)
            error = json.loads(attached.stdout)["error"]
            self.assertIn("symbolic link", error)
            self.assertIn(".migration", error)
            self.assertEqual(state_path.read_bytes(), original_state)
            self.assertFalse(
                (real_migration / "source-contract.json").exists()
            )

    def test_snapshot_force_rejects_forged_internal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original_source = root / "original-android"
            replacement_source = root / "replacement-android"
            owned_snapshot = root / "owned-snapshot"
            forged_snapshot = root / "ordinary-directory"
            original_source.mkdir()
            replacement_source.mkdir()
            (original_source / "settings.gradle.kts").write_text(
                'rootProject.name = "Original"\n',
                encoding="utf-8",
            )
            (replacement_source / "settings.gradle.kts").write_text(
                'rootProject.name = "Replacement"\n',
                encoding="utf-8",
            )
            prepared = run_script(
                PREPARE,
                "--source",
                str(original_source),
                "--snapshot",
                str(owned_snapshot),
            )
            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            shutil.copytree(owned_snapshot, forged_snapshot)
            forged_manifest_path = (
                forged_snapshot / ".android-to-harmony-safe.json"
            )
            forged_manifest = json.loads(
                forged_manifest_path.read_text(encoding="utf-8")
            )
            forged_manifest["snapshot_root"] = str(forged_snapshot)
            forged_manifest_path.write_text(
                json.dumps(forged_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            original_bytes = (
                forged_snapshot / "settings.gradle.kts"
            ).read_bytes()

            replaced = run_script(
                PREPARE,
                "--source",
                str(replacement_source),
                "--snapshot",
                str(forged_snapshot),
                "--force",
            )

            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn(
                "external ownership",
                json.loads(replaced.stdout)["error"],
            )
            self.assertEqual(
                (forged_snapshot / "settings.gradle.kts").read_bytes(),
                original_bytes,
            )

    def test_snapshot_force_rejects_rehashed_internal_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "android"
            snapshot = root / "snapshot"
            source.mkdir()
            (source / "settings.gradle.kts").write_text(
                'rootProject.name = "Generated"\n',
                encoding="utf-8",
            )
            prepared = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )
            self.assertEqual(prepared.returncode, 0, prepared.stdout)
            copied_file = snapshot / "settings.gradle.kts"
            copied_file.write_text(
                'rootProject.name = "UserOwned"\n',
                encoding="utf-8",
            )
            manifest_path = snapshot / ".android-to-harmony-safe.json"
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            manifest["text_file_sha256"]["settings.gradle.kts"] = (
                hashlib.sha256(copied_file.read_bytes()).hexdigest()
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            replaced = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
                "--force",
            )

            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn(
                "external ownership",
                json.loads(replaced.stdout)["error"],
            )
            self.assertIn(
                "UserOwned",
                copied_file.read_text(encoding="utf-8"),
            )

    def test_initializer_force_rejects_forged_internal_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            owned_output = root / "owned-project"
            forged_output = root / "ordinary-directory"
            initialized = run_script(
                INITIALIZE,
                "--output",
                str(owned_output),
                "--project-name",
                "Original Project",
                "--bundle-name",
                "com.example.original",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            shutil.copytree(owned_output, forged_output)
            index = forged_output / "entry/src/main/ets/pages/Index.ets"
            original_bytes = index.read_bytes()

            replaced = run_script(
                INITIALIZE,
                "--output",
                str(forged_output),
                "--project-name",
                "Replacement Project",
                "--bundle-name",
                "com.example.replacement",
                "--force",
            )

            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn(
                "external ownership",
                json.loads(replaced.stdout)["error"],
            )
            self.assertEqual(index.read_bytes(), original_bytes)

    def test_initializer_force_rejects_rehashed_internal_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "HarmonyFixture"
            initialized = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "Original Project",
                "--bundle-name",
                "com.example.original",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            relative_index = "entry/src/main/ets/pages/Index.ets"
            index = output / relative_index
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n// user-owned change\n",
                encoding="utf-8",
            )
            state_path = output / ".migration/state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["generated_file_sha256"][relative_index] = (
                hashlib.sha256(index.read_bytes()).hexdigest()
            )
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            replaced = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "Replacement Project",
                "--bundle-name",
                "com.example.replacement",
                "--force",
            )

            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn(
                "external ownership",
                json.loads(replaced.stdout)["error"],
            )
            self.assertIn(
                "user-owned change",
                index.read_text(encoding="utf-8"),
            )

    def test_initializer_force_rejects_world_readable_ownership_secret(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "HarmonyFixture"
            initialized = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "Original Project",
                "--bundle-name",
                "com.example.original",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stdout)
            state_path = output / ".migration/state.json"
            original_state = state_path.read_bytes()
            target_key = hashlib.sha256(
                str(output).encode("utf-8")
            ).hexdigest()
            ownership_record = (
                output.parent
                / ".android-to-harmony-ownership"
                / f"{target_key}.json"
            )
            ownership_record.chmod(0o644)

            replaced = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "Replacement Project",
                "--bundle-name",
                "com.example.replacement",
                "--force",
            )

            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn(
                "external ownership",
                json.loads(replaced.stdout)["error"],
            )
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_snapshot_does_not_replace_unowned_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "android"
            snapshot = root / "empty-snapshot"
            source.mkdir()
            snapshot.mkdir()
            original_inode = snapshot.stat().st_ino
            (source / "settings.gradle.kts").write_text(
                'rootProject.name = "Fixture"\n',
                encoding="utf-8",
            )

            without_force = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
            )
            with_force = run_script(
                PREPARE,
                "--source",
                str(source),
                "--snapshot",
                str(snapshot),
                "--force",
            )

            self.assertNotEqual(without_force.returncode, 0)
            self.assertNotEqual(with_force.returncode, 0)
            self.assertEqual(snapshot.stat().st_ino, original_inode)
            self.assertEqual(list(snapshot.iterdir()), [])

    def test_initializer_does_not_replace_unowned_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "empty-project"
            output.mkdir()
            original_inode = output.stat().st_ino

            without_force = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "HarmonyFixture",
                "--bundle-name",
                "com.example.harmonyfixture",
            )
            with_force = run_script(
                INITIALIZE,
                "--output",
                str(output),
                "--project-name",
                "HarmonyFixture",
                "--bundle-name",
                "com.example.harmonyfixture",
                "--force",
            )

            self.assertNotEqual(without_force.returncode, 0)
            self.assertNotEqual(with_force.returncode, 0)
            self.assertEqual(output.stat().st_ino, original_inode)
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
