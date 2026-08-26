#!/usr/bin/env python3
"""Create a text-only Android source snapshot for AI-assisted migration."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_ai_safe_tree import (
    contains_build_config_credential_literal,
    contains_normalized_credential_literal,
    strip_android_ui_label_credential_resources,
    validate as validate_ai_safe_tree,
)


POLICY_VERSION = 3
OWNERSHIP_SCHEMA = "android-to-harmony.external-ownership.v1"
OWNERSHIP_REFERENCE_SCHEMA = "android-to-harmony.ownership-reference.v1"
OWNERSHIP_DIRECTORY = ".android-to-harmony-ownership"
OWNERSHIP_KIND = "safe-snapshot"
MAX_TEXT_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = {
    ".aidl",
    ".cfg",
    ".gradle",
    ".java",
    ".json",
    ".kts",
    ".kt",
    ".md",
    ".pro",
    ".properties",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {
    ".gitignore",
    "gradlew",
    "proguard-rules.pro",
}
IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".psd",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}
FONT_SUFFIXES = {
    ".otf",
    ".ttf",
}
SENSITIVE_FILENAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "agconnect-services.json",
    "google-services.json",
    "keystore.properties",
    "local.properties",
    "secrets.properties",
}
SENSITIVE_SUFFIXES = {
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".pem",
}
PRUNED_DIRECTORIES = {
    OWNERSHIP_DIRECTORY,
    ".git",
    ".gradle",
    ".idea",
    ".kotlin",
    ".tmp",
    "build",
    "captures",
    "node_modules",
    "out",
}
EMBEDDED_IMAGE_PATTERNS = (
    re.compile(r"data\s*:\s*image/", re.IGNORECASE),
    re.compile(
        r"(?<![A-Za-z0-9+/])"
        r"(?:[A-Za-z0-9+/]{256,}={0,2})"
        r"(?![A-Za-z0-9+/=])"
    ),
)
BASE64_DECODE_CALL_PATTERN = re.compile(
    r"\b(?:Base64\.decode|decodeBase64|base64Decode)\s*"
    r"\((.{0,16384}?)\)",
    re.DOTALL,
)
BASE64_STRING_LITERAL_PATTERN = re.compile(
    r"[\"']([A-Za-z0-9+/]{16,}={0,2})[\"']"
)
SIGNING_PASSWORD_LITERAL_PATTERN = re.compile(
    r"""(?ix)
    \b(?:storePassword|keyPassword)\b
    (?:\s*=\s*|\s*\(\s*|\s+)
    (?P<quote>["'])
    (?P<value>(?:\\.|(?!(?P=quote))[^$\r\n])+)
    (?P=quote)
    """
)
SENSITIVE_CONTENT_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    re.compile(
        r"\b(?:"
        r"AKIA[0-9A-Z]{16}|"
        r"AIza[0-9A-Za-z_-]{30,}|"
        r"github_pat_[A-Za-z0-9_]{20,}|"
        r"gh[pousr]_[A-Za-z0-9]{20,}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,}|"
        r"sk-proj-[A-Za-z0-9_-]{16,}|"
        r"sk_(?:live|test)_[A-Za-z0-9]{16,}"
        r")\b"
    ),
    re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|"
        r"auth[_-]?token|password|passwd|secret)\b"
        r"\s*(?:=|:)\s*[\"'][^\"'\r\n]{8,}[\"']"
    ),
    re.compile(
        r"(?i)[\"'](?:api_key|apikey|client_secret|secret|access_token|"
        r"auth_token|password|passwd|storePassword|keyPassword)[\"']"
        r"\s*:\s*[\"']"
        r"(?!(?:\$\{|System\.getenv|providers\.|project\.findProperty))"
        r"[^\"'\r\n]{8,}[\"']"
    ),
    re.compile(
        r"(?is)<(?:string|item)\b[^>]*\bname\s*=\s*"
        r"[\"'](?:api_key|apikey|client_secret|secret|access_token|"
        r"auth_token|password|passwd|storePassword|keyPassword)[\"'][^>]*>"
        r"\s*(?!\$\{)[^<\r\n]{8,}\s*</(?:string|item)\s*>"
    ),
    re.compile(
        r"(?i)[\"'](?:x-api-key|authorization|client-secret)[\"']"
        r"\s*,\s*[\"'][^\"'\r\n]{8,}[\"']"
    ),
    SIGNING_PASSWORD_LITERAL_PATTERN,
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\."
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(
        r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{8,}@"
    ),
)
PROPERTY_CREDENTIAL_PATTERN = re.compile(
    r"(?im)^\s*(?:api_key|apikey|client_secret|secret|access_token|"
    r"auth_token|password|passwd|storePassword|keyPassword)\s*=\s*"
    r"(?!\$\{|System\.getenv|providers\.|project\.findProperty)"
    r"[^\s#][^\r\n]{7,}$"
)


class SnapshotError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy only audited UTF-8 source text into an AI-safe snapshot."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES


def is_local_only_asset(path: Path) -> bool:
    if path.suffix.lower() in IMAGE_SUFFIXES | FONT_SUFFIXES:
        return True
    if path.suffix.lower() != ".xml":
        return False
    return any(
        parent.name.startswith(("drawable", "mipmap"))
        for parent in path.parents
    )


def is_sensitive_path(path: Path) -> bool:
    return path.name in SENSITIVE_FILENAMES or path.name.startswith(".env.")


def contains_embedded_image(text: str) -> bool:
    if any(pattern.search(text) is not None for pattern in EMBEDDED_IMAGE_PATTERNS):
        return True
    for call in BASE64_DECODE_CALL_PATTERN.finditer(text):
        joined = "".join(
            BASE64_STRING_LITERAL_PATTERN.findall(call.group(1))
        )
        if (
            len(joined) >= 256
            and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", joined) is not None
        ):
            return True
    return False


def contains_credential_literal(text: str, path: Path) -> bool:
    credential_scan_text = (
        strip_android_ui_label_credential_resources(text)
        if path.suffix.lower() == ".xml"
        else text
    )
    if contains_build_config_credential_literal(text):
        return True
    if contains_normalized_credential_literal(
        credential_scan_text,
        include_properties=path.suffix.lower() == ".properties",
    ):
        return True
    if any(pattern.search(credential_scan_text) is not None for pattern in SENSITIVE_CONTENT_PATTERNS):
        return True
    return (
        path.suffix.lower() == ".properties"
        and PROPERTY_CREDENTIAL_PATTERN.search(text) is not None
    )


def read_audited_text(path: Path) -> tuple[str | None, str | None]:
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        return None, "text_file_too_large"
    content = path.read_bytes()
    if b"\x00" in content:
        return None, "nul_byte_detected"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None, "not_utf8"
    if contains_embedded_image(text):
        return None, "embedded_image_payload"
    if contains_credential_literal(text, path):
        return None, "potential_credential"
    return text, None


def collect_source_entries(
    root: Path,
) -> tuple[list[Path], list[Path], list[Path]]:
    files: list[Path] = []
    symbolic_links: list[Path] = []
    pruned_directories: list[Path] = []
    for current_root, directories, filenames in os.walk(root):
        current = Path(current_root)
        kept_directories: list[str] = []
        for directory in sorted(directories):
            child = current / directory
            if child.is_symlink():
                symbolic_links.append(child)
            elif directory in PRUNED_DIRECTORIES:
                pruned_directories.append(child)
            else:
                kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink():
                symbolic_links.append(path)
            elif path.is_file():
                files.append(path)
    return files, symbolic_links, pruned_directories


def normalized_path(path: Path, role: str) -> Path:
    absolute = Path(os.path.abspath(os.path.expanduser(str(path))))
    if absolute.is_symlink():
        raise SnapshotError(f"{role} directory must not be a symbolic link: {absolute}")
    return absolute.resolve()


def ownership_record_path(target: Path) -> Path:
    target_key = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    return target.parent / OWNERSHIP_DIRECTORY / f"{target_key}.json"


def load_external_ownership(target: Path) -> str | None:
    record_path = ownership_record_path(target)
    if (
        record_path.parent.is_symlink()
        or not record_path.is_file()
        or record_path.is_symlink()
    ):
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    secret = record.get("secret")
    if (
        record.get("schema") != OWNERSHIP_SCHEMA
        or record.get("kind") != OWNERSHIP_KIND
        or record.get("target_root") != str(target)
        or not isinstance(secret, str)
        or re.fullmatch(r"[0-9a-f]{64}", secret) is None
    ):
        return None
    return secret


def claim_external_ownership(target: Path) -> str:
    existing = load_external_ownership(target)
    if existing is not None:
        return existing
    record_path = ownership_record_path(target)
    ownership_directory = record_path.parent
    if ownership_directory.is_symlink():
        raise SnapshotError(
            f"external ownership directory must not be a symbolic link: "
            f"{ownership_directory}"
        )
    if ownership_directory.exists() and not ownership_directory.is_dir():
        raise SnapshotError(
            f"external ownership path is not a directory: "
            f"{ownership_directory}"
        )
    ownership_directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    if record_path.exists() or record_path.is_symlink():
        raise SnapshotError(
            "external ownership record is invalid; refusing to replace it"
        )
    secret = secrets.token_hex(32)
    record = {
        "schema": OWNERSHIP_SCHEMA,
        "kind": OWNERSHIP_KIND,
        "target_root": str(target),
        "secret": secret,
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{record_path.name}.prepare-",
        dir=ownership_directory,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, record_path)
        except FileExistsError as error:
            raced = load_external_ownership(target)
            if raced is not None:
                return raced
            raise SnapshotError(
                "external ownership record changed while it was being created"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)
    return secret


def ownership_signature(
    payload: dict[str, Any],
    target: Path,
    secret: str,
) -> str:
    unsigned_payload = {
        key: value
        for key, value in payload.items()
        if key != "ownership"
    }
    message = json.dumps(
        {
            "kind": OWNERSHIP_KIND,
            "target_root": str(target),
            "payload": unsigned_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        bytes.fromhex(secret),
        message,
        hashlib.sha256,
    ).hexdigest()


def attach_ownership_proof(
    payload: dict[str, Any],
    target: Path,
    secret: str,
) -> None:
    payload["ownership"] = {
        "schema": OWNERSHIP_REFERENCE_SCHEMA,
        "signature": ownership_signature(payload, target, secret),
    }


def has_external_ownership_proof(
    target: Path,
    payload: dict[str, Any],
) -> bool:
    reference = payload.get("ownership")
    secret = load_external_ownership(target)
    if not isinstance(reference, dict) or secret is None:
        return False
    signature = reference.get("signature")
    return (
        reference.get("schema") == OWNERSHIP_REFERENCE_SCHEMA
        and isinstance(signature, str)
        and re.fullmatch(r"[0-9a-f]{64}", signature) is not None
        and hmac.compare_digest(
            signature,
            ownership_signature(payload, target, secret),
        )
    )


def contains_git_repository(path: Path) -> bool:
    for current_root, directories, _filenames in os.walk(path):
        if ".git" in directories or Path(current_root, ".git").is_file():
            return True
        directories[:] = [
            directory
            for directory in directories
            if not Path(current_root, directory).is_symlink()
        ]
    return False


def owns_existing_snapshot(snapshot: Path) -> bool:
    marker = snapshot / ".android-to-harmony-safe.json"
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        recorded_root = normalized_path(
            Path(manifest.get("snapshot_root", "")),
            "recorded snapshot",
        )
    except (
        AttributeError,
        json.JSONDecodeError,
        OSError,
        SnapshotError,
        TypeError,
        UnicodeDecodeError,
    ):
        return False
    marker_matches = (
        manifest.get("schema") == "android-to-harmony.safe-snapshot.v1"
        and recorded_root == snapshot
        and has_external_ownership_proof(snapshot, manifest)
    )
    if not marker_matches:
        return False
    validation = validate_ai_safe_tree(
        snapshot,
        require_safe_manifest=True,
    )
    return bool(validation.get("ok"))


def validate_destination(source: Path, snapshot: Path, force: bool) -> None:
    if (
        source == snapshot
        or source in snapshot.parents
        or snapshot in source.parents
    ):
        raise SnapshotError(
            "source and snapshot directories must not contain one another"
        )
    if snapshot.name == OWNERSHIP_DIRECTORY:
        raise SnapshotError(
            "snapshot must not use the reserved external ownership "
            f"directory name: {OWNERSHIP_DIRECTORY}"
        )
    if snapshot.exists():
        if not snapshot.is_dir():
            raise SnapshotError(f"snapshot exists and is not a directory: {snapshot}")
        if not force:
            raise SnapshotError("snapshot already exists; pass --force to replace it")
        if not owns_existing_snapshot(snapshot):
            raise SnapshotError(
                "refusing to replace a directory without a pristine "
                "safe-snapshot marker, matching file hashes, and matching "
                "external ownership proof; legacy outputs without an "
                "external ownership record must be recreated at a new path"
            )
        if contains_git_repository(snapshot):
            raise SnapshotError("refusing to replace a Git repository")
    snapshot.parent.mkdir(parents=True, exist_ok=True)


def commit_snapshot(temporary: Path, snapshot: Path) -> None:
    if not snapshot.exists():
        os.replace(temporary, snapshot)
        return

    backup = Path(
        tempfile.mkdtemp(prefix=f".{snapshot.name}.backup-", dir=snapshot.parent)
    )
    backup.rmdir()
    os.replace(snapshot, backup)
    try:
        os.replace(temporary, snapshot)
    except OSError:
        os.replace(backup, snapshot)
        raise
    shutil.rmtree(backup)


def git_metadata(source: Path) -> dict[str, Any]:
    def run_git(*arguments: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(source), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    repository_root = run_git("rev-parse", "--show-toplevel")
    if repository_root is None or Path(repository_root).resolve() != source:
        return {
            "is_repository": False,
            "revision": None,
            "branch": None,
            "dirty": False,
            "dirty_entry_count": 0,
        }

    revision = run_git("rev-parse", "HEAD")
    branch = run_git("branch", "--show-current")
    status = run_git("status", "--porcelain")
    return {
        "is_repository": revision is not None,
        "revision": revision,
        "branch": branch,
        "dirty": bool(status),
        "dirty_entry_count": len(status.splitlines()) if status else 0,
    }


def create_snapshot(source: Path, snapshot: Path, force: bool) -> dict[str, Any]:
    source = normalized_path(source, "source")
    snapshot = normalized_path(snapshot, "snapshot")
    if not source.is_dir():
        raise SnapshotError(f"source directory does not exist: {source}")
    if (source / ".android-to-harmony-safe.json").is_file():
        raise SnapshotError(
            "source is already an Android-to-Harmony safe snapshot; "
            "validate and analyze it directly instead of preparing it again"
        )
    validate_destination(source, snapshot, force)
    ownership_secret = claim_external_ownership(snapshot)

    copied_text_files: list[str] = []
    text_file_hashes: dict[str, str] = {}
    local_only_assets: list[dict[str, Any]] = []
    blocked_files: list[dict[str, str]] = []
    ignored_files: list[dict[str, str]] = []

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{snapshot.name}.prepare-", dir=snapshot.parent)
    )
    try:
        files, symbolic_links, pruned_directories = collect_source_entries(source)
        blocked_files.extend(
            {
                "path": relative_path(path, source),
                "reason": "symbolic_link",
            }
            for path in symbolic_links
        )

        for path in files:
            relative = relative_path(path, source)
            if is_local_only_asset(path):
                local_only_assets.append(
                    {
                        "path": relative,
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
                continue
            if is_sensitive_path(path):
                blocked_files.append(
                    {"path": relative, "reason": "sensitive_configuration"}
                )
                continue
            if path.suffix.lower() in SENSITIVE_SUFFIXES:
                blocked_files.append(
                    {"path": relative, "reason": "sensitive_file_type"}
                )
                continue
            if not is_text_candidate(path):
                ignored_files.append(
                    {
                        "path": relative,
                        "reason": "unsupported_file_type",
                        "suffix": path.suffix.lower() or "<none>",
                    }
                )
                continue

            text, reason = read_audited_text(path)
            if reason is not None:
                blocked_files.append({"path": relative, "reason": reason})
                continue

            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text or "", encoding="utf-8")
            copied_text_files.append(relative)
            text_file_hashes[relative] = sha256_file(destination)

        manifest = {
            "schema": "android-to-harmony.safe-snapshot.v1",
            "policy_version": POLICY_VERSION,
            "source_root": str(source),
            "snapshot_root": str(snapshot),
            "source_git": git_metadata(source),
            "text_file_count": len(copied_text_files),
            "text_files": copied_text_files,
            "text_file_sha256": text_file_hashes,
            "local_only_asset_count": len(local_only_assets),
            "local_only_assets": local_only_assets,
            "blocked_file_count": len(blocked_files),
            "blocked_files": blocked_files,
            "ignored_file_count": len(ignored_files),
            "ignored_files": ignored_files,
            "pruned_directory_count": len(pruned_directories),
            "pruned_directories": [
                {
                    "path": relative_path(path, source),
                    "reason": "generated_or_repository_metadata",
                }
                for path in pruned_directories
            ],
            "guarantees": {
                "known_image_paths_copied": False,
                "embedded_image_scan": {
                    "policy": "android-to-harmony.embedded-image-scan.v2",
                    "status": "no_match",
                    "coverage": (
                        "data:image URIs and contiguous Base64 payloads "
                        "of 256 or more characters"
                    ),
                },
                "absolute_image_absence_proven": False,
                "credential_literal_scan": {
                    "policy": "android-to-harmony.credential-literal-scan.v3",
                    "status": "no_match",
                },
                "utf8_text_only": True,
                "contains_symbolic_links": False,
                "file_hashes_recorded": True,
            },
        }
        attach_ownership_proof(manifest, snapshot, ownership_secret)
        manifest_path = temporary / ".android-to-harmony-safe.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        commit_snapshot(temporary, snapshot)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    args = parse_args()
    try:
        manifest = create_snapshot(args.source, args.snapshot, args.force)
    except (OSError, SnapshotError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": "android-to-harmony.command-result.v1",
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "schema": "android-to-harmony.command-result.v1",
                "snapshot_root": manifest["snapshot_root"],
                "text_file_count": manifest["text_file_count"],
                "local_only_asset_count": manifest["local_only_asset_count"],
                "blocked_file_count": manifest["blocked_file_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
