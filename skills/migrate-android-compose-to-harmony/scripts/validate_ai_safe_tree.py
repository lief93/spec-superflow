#!/usr/bin/env python3
"""Fail closed when a model-visible tree contains image or binary payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


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
FORBIDDEN_DIRECTORIES = {
    ".android-to-harmony-ownership",
    ".git",
    ".gradle",
    ".idea",
    "build",
    "node_modules",
    "oh_modules",
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
EMBEDDED_IMAGE_PATTERNS = (
    ("data_image_uri", re.compile(r"data\s*:\s*image/", re.IGNORECASE)),
    (
        "long_base64_payload",
        re.compile(
            r"(?<![A-Za-z0-9+/])"
            r"(?:[A-Za-z0-9+/]{256,}={0,2})"
            r"(?![A-Za-z0-9+/=])"
        ),
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
BUILD_CONFIG_FIELD_PATTERN = re.compile(r"\bbuildConfigField\b")
SENSITIVE_BUILD_CONFIG_NAME_PATTERN = re.compile(
    r"(?i)(?:^|[_-])(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)$"
)
SENSITIVE_CONTENT_PATTERNS = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    (
        "known_credential",
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
    ),
    (
        "credential_literal",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|"
            r"auth[_-]?token|password|passwd|secret)\b"
            r"\s*(?:=|:)\s*[\"'][^\"'\r\n]{8,}[\"']"
        ),
    ),
    (
        "credential_literal",
        re.compile(
            r"(?i)[\"'](?:api_key|apikey|client_secret|secret|access_token|"
            r"auth_token|password|passwd|storePassword|keyPassword)[\"']"
            r"\s*:\s*[\"']"
            r"(?!(?:\$\{|System\.getenv|providers\.|project\.findProperty))"
            r"[^\"'\r\n]{8,}[\"']"
        ),
    ),
    (
        "credential_literal",
        re.compile(
            r"(?is)<(?:string|item)\b[^>]*\bname\s*=\s*"
            r"[\"'](?:api_key|apikey|client_secret|secret|access_token|"
            r"auth_token|password|passwd|storePassword|keyPassword)[\"'][^>]*>"
            r"\s*(?!\$\{)[^<\r\n]{8,}\s*</(?:string|item)\s*>"
        ),
    ),
    (
        "credential_header_literal",
        re.compile(
            r"(?i)[\"'](?:x-api-key|authorization|client-secret)[\"']"
            r"\s*,\s*[\"'][^\"'\r\n]{8,}[\"']"
        ),
    ),
    ("credential_literal", SIGNING_PASSWORD_LITERAL_PATTERN),
    (
        "known_credential",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\."
            r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
    ),
    (
        "credential_url",
        re.compile(
            r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{8,}@"
        ),
    ),
)
PROPERTY_CREDENTIAL_PATTERN = re.compile(
    r"(?im)^\s*(?:api_key|apikey|client_secret|secret|access_token|"
    r"auth_token|password|passwd|storePassword|keyPassword)\s*=\s*"
    r"(?!\$\{|System\.getenv|providers\.|project\.findProperty)"
    r"[^\s#][^\r\n]{7,}$"
)
CREDENTIAL_IDENTIFIER_LITERAL_PATTERN = re.compile(
    r"""(?ix)
    \b(?P<name>[A-Za-z_][A-Za-z0-9_-]{2,})\b
    \s*(?:=|:|\()\s*
    (?P<quote>["'])
    (?P<value>(?:\\.|(?!(?P=quote))[^$\r\n]){8,})
    (?P=quote)
    """
)
QUOTED_CREDENTIAL_LITERAL_PATTERN = re.compile(
    r"""(?ix)
    (?P<key_quote>["'])
    (?P<name>[A-Za-z_][A-Za-z0-9_-]{2,})
    (?P=key_quote)
    \s*:\s*
    (?P<value_quote>["'])
    (?P<value>(?:\\.|(?!(?P=value_quote))[^$\r\n]){8,})
    (?P=value_quote)
    """
)
PROPERTY_IDENTIFIER_LITERAL_PATTERN = re.compile(
    r"""(?imx)
    ^\s*(?P<name>[A-Za-z_][A-Za-z0-9_.-]{2,})\s*=\s*
    (?P<value>[^\s#][^\r\n]{7,})$
    """
)
ANDROID_UI_LABEL_CREDENTIAL_RESOURCE_PATTERN = re.compile(
    r"""(?isx)
    <(?P<tag>string|item)\b
    (?P<attrs>[^>]*?)\bname\s*=\s*(?P<quote>["'])
    (?P<name>password|passwd|passcode|pin)
    (?P=quote)(?P<rest>[^>]*)>
    (?P<value>[^<]{1,64})
    </(?P=tag)\s*>
    """
)
CREDENTIAL_IDENTIFIER_SUFFIXES = (
    "apikey",
    "apitoken",
    "accesstoken",
    "authtoken",
    "clientsecret",
    "secretaccesskey",
    "storepassword",
    "keypassword",
    "password",
    "passwd",
    "secret",
)
SAFE_CREDENTIAL_UI_LABELS = {
    "password",
    "passcode",
    "pin",
    "enter password",
    "confirm password",
    "new password",
    "old password",
    "current password",
}


def is_credential_identifier(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    return any(
        normalized.endswith(suffix)
        for suffix in CREDENTIAL_IDENTIFIER_SUFFIXES
    )


def contains_normalized_credential_literal(
    text: str,
    include_properties: bool = False,
) -> bool:
    for pattern in (
        CREDENTIAL_IDENTIFIER_LITERAL_PATTERN,
        QUOTED_CREDENTIAL_LITERAL_PATTERN,
    ):
        for match in pattern.finditer(text):
            if is_credential_identifier(match.group("name")):
                return True
    if include_properties:
        for match in PROPERTY_IDENTIFIER_LITERAL_PATTERN.finditer(text):
            if not is_credential_identifier(match.group("name")):
                continue
            value = match.group("value").strip()
            if not value.startswith(
                ("${", "System.getenv", "providers.", "project.findProperty")
            ):
                return True
    return False


def strip_android_ui_label_credential_resources(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        normalized_value = re.sub(r"\s+", " ", match.group("value").strip())
        normalized_value = normalized_value.lower().strip(" *:：?？")
        if normalized_value in SAFE_CREDENTIAL_UI_LABELS:
            return ""
        return match.group(0)

    return ANDROID_UI_LABEL_CREDENTIAL_RESOURCE_PATTERN.sub(replace, text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a file tree is safe to expose to an AI model."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-safe-manifest", action="store_true")
    return parser.parse_args()


def is_image_path(path: Path) -> bool:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return True
    if path.suffix.lower() != ".xml":
        return False
    return any(
        parent.name.startswith(("drawable", "mipmap"))
        for parent in path.parents
    )


def is_sensitive_path(path: Path) -> bool:
    return path.name in SENSITIVE_FILENAMES or path.name.startswith(".env.")


def contains_literal_base64_decode_payload(text: str) -> bool:
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


def invocation_arguments(text: str, name_end: int) -> str | None:
    cursor = name_end
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    parenthesized = cursor < len(text) and text[cursor] == "("
    if parenthesized:
        cursor += 1
    start = cursor
    depth = 1 if parenthesized else 0
    quote: str | None = None
    escaped = False
    while cursor < len(text):
        character = text[cursor]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in "\"'":
            quote = character
        elif parenthesized and character == "(":
            depth += 1
        elif parenthesized and character == ")":
            depth -= 1
            if depth == 0:
                return text[start:cursor]
        elif not parenthesized and character in "\r\n;":
            return text[start:cursor]
        cursor += 1
    return None if parenthesized else text[start:cursor]


def split_top_level_arguments(arguments: str) -> list[str]:
    result: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(arguments):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "\"'":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            result.append(arguments[start:index].strip())
            start = index + 1
    result.append(arguments[start:].strip())
    return result


def string_literal(expression: str) -> tuple[str, str] | None:
    expression = expression.strip()
    if len(expression) < 2 or expression[0] not in "\"'":
        return None
    quote = expression[0]
    escaped = False
    for index in range(1, len(expression)):
        character = expression[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            if expression[index + 1 :].strip():
                return None
            return quote, expression[1:index]
    return None


def contains_build_config_credential_literal(text: str) -> bool:
    for match in BUILD_CONFIG_FIELD_PATTERN.finditer(text):
        arguments_text = invocation_arguments(text, match.end())
        if arguments_text is None:
            continue
        arguments = split_top_level_arguments(arguments_text)
        if len(arguments) < 3:
            continue
        field_literal = string_literal(arguments[1])
        value_literal = string_literal(arguments[2])
        if field_literal is None or value_literal is None:
            continue
        _field_quote, field_name = field_literal
        value_quote, value = value_literal
        if SENSITIVE_BUILD_CONFIG_NAME_PATTERN.search(field_name) is None:
            continue
        if value_quote == '"' and "$" in value:
            continue
        meaningful_value = (
            value.replace('\\"', "")
            .replace("\\'", "")
            .replace('"', "")
            .replace("'", "")
            .strip()
        )
        if meaningful_value:
            return True
    return False


SAFE_MANIFEST = ".android-to-harmony-safe.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_entries(
    path: Path,
) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    if path.is_symlink():
        return [], [path], [], []
    if path.is_file():
        return [path], [], [], []
    if not path.is_dir():
        return [], [], [], [path]
    files: list[Path] = []
    symbolic_links: list[Path] = []
    forbidden_directories: list[Path] = []
    special_entries: list[Path] = []
    for current_root, directories, filenames in os.walk(path):
        current = Path(current_root)
        kept_directories: list[str] = []
        for directory in sorted(directories):
            child = current / directory
            if child.is_symlink():
                symbolic_links.append(child)
            elif directory in FORBIDDEN_DIRECTORIES:
                forbidden_directories.append(child)
            else:
                kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in sorted(filenames):
            child = current / filename
            if child.is_symlink():
                symbolic_links.append(child)
            elif child.is_file():
                files.append(child)
            else:
                special_entries.append(child)
    return files, symbolic_links, forbidden_directories, special_entries


def is_safe_relative_path(relative: str) -> bool:
    path = Path(relative)
    return (
        bool(relative)
        and "\x00" not in relative
        and "\\" not in relative
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == relative
    )


def validate_manifest_coverage(
    root: Path,
    files: list[Path],
) -> list[dict[str, str]]:
    manifest_path = root / SAFE_MANIFEST
    if manifest_path not in files:
        return []
    violations: list[dict[str, str]] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return [{"path": SAFE_MANIFEST, "reason": "invalid_safe_manifest"}]
    if not isinstance(manifest, dict):
        return [{"path": SAFE_MANIFEST, "reason": "invalid_safe_manifest"}]
    text_files = manifest.get("text_files")
    hashes = manifest.get("text_file_sha256")
    if (
        manifest.get("schema") != "android-to-harmony.safe-snapshot.v1"
        or not isinstance(text_files, list)
        or not all(isinstance(relative, str) for relative in text_files)
        or not isinstance(hashes, dict)
    ):
        return [{"path": SAFE_MANIFEST, "reason": "invalid_safe_manifest"}]
    if len(text_files) != len(set(text_files)):
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "duplicate_manifest_path"}
        )
    unsafe = next(
        (
            relative
            for relative in text_files
            if not is_safe_relative_path(relative)
        ),
        None,
    )
    if unsafe is not None:
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "unsafe_manifest_path"}
        )
    if set(hashes) != set(text_files):
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "manifest_hash_set_mismatch"}
        )
    if manifest.get("text_file_count") != len(text_files):
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "manifest_count_mismatch"}
        )

    actual_files = {
        file_path.relative_to(root).as_posix()
        for file_path in files
    }
    expected_files = set(text_files)
    expected_files.add(SAFE_MANIFEST)
    if actual_files != expected_files:
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "manifest_tree_mismatch"}
        )

    for relative in text_files:
        expected_hash = hashes.get(relative)
        if (
            not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
            or not is_safe_relative_path(relative)
        ):
            violations.append(
                {"path": SAFE_MANIFEST, "reason": "invalid_manifest_hash"}
            )
            break
        file_path = root / relative
        if (
            file_path not in files
            or file_path.is_symlink()
            or not file_path.is_file()
        ):
            continue
        if sha256_file(file_path) != expected_hash:
            violations.append(
                {"path": relative, "reason": "manifest_hash_mismatch"}
            )
            break
    return violations


def validate(
    path: Path,
    require_safe_manifest: bool = False,
) -> dict[str, Any]:
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    if not path.exists():
        return {"ok": False, "violations": [{"path": str(path), "reason": "not_found"}]}

    root = path if path.is_dir() else path.parent
    violations: list[dict[str, str]] = []
    checked_files = 0
    (
        files,
        symbolic_links,
        forbidden_directories,
        special_entries,
    ) = collect_entries(path)

    for symbolic_link in symbolic_links:
        relative = symbolic_link.relative_to(root).as_posix()
        violations.append({"path": relative, "reason": "symbolic_link"})

    for forbidden_directory in forbidden_directories:
        relative = forbidden_directory.relative_to(root).as_posix()
        violations.append({"path": relative, "reason": "forbidden_directory"})

    for special_entry in special_entries:
        relative = special_entry.relative_to(root).as_posix()
        violations.append({"path": relative, "reason": "special_file"})

    if (
        require_safe_manifest
        and path.is_dir()
        and root / SAFE_MANIFEST not in files
    ):
        violations.append(
            {"path": SAFE_MANIFEST, "reason": "missing_safe_manifest"}
        )

    for file_path in files:
        checked_files += 1
        relative = file_path.relative_to(root).as_posix()
        if is_image_path(file_path):
            violations.append({"path": relative, "reason": "image_file"})
            continue
        if is_sensitive_path(file_path):
            violations.append(
                {"path": relative, "reason": "sensitive_configuration"}
            )
            continue
        try:
            content = file_path.read_bytes()
        except OSError:
            violations.append({"path": relative, "reason": "unreadable_file"})
            continue
        if b"\x00" in content:
            violations.append({"path": relative, "reason": "binary_file"})
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            violations.append({"path": relative, "reason": "not_utf8"})
            continue
        for reason, pattern in EMBEDDED_IMAGE_PATTERNS:
            if pattern.search(text) is not None:
                violations.append({"path": relative, "reason": reason})
                break
        else:
            if contains_literal_base64_decode_payload(text):
                violations.append(
                    {
                        "path": relative,
                        "reason": "base64_decode_literal_payload",
                    }
                )
                continue
            if contains_build_config_credential_literal(text):
                violations.append(
                    {"path": relative, "reason": "credential_literal"}
                )
                continue
            credential_scan_text = (
                strip_android_ui_label_credential_resources(text)
                if file_path.suffix.lower() == ".xml"
                else text
            )
            if contains_normalized_credential_literal(
                credential_scan_text,
                include_properties=file_path.suffix.lower() == ".properties",
            ):
                violations.append(
                    {"path": relative, "reason": "credential_literal"}
                )
                continue
            for reason, pattern in SENSITIVE_CONTENT_PATTERNS:
                if pattern.search(credential_scan_text) is not None:
                    violations.append({"path": relative, "reason": reason})
                    break
            else:
                if (
                    file_path.suffix.lower() == ".properties"
                    and PROPERTY_CREDENTIAL_PATTERN.search(text) is not None
                ):
                    violations.append(
                        {
                            "path": relative,
                            "reason": "credential_property_literal",
                        }
                    )

    if path.is_dir():
        violations.extend(validate_manifest_coverage(root, files))

    return {
        "ok": not violations,
        "schema": "android-to-harmony.ai-safe-validation.v1",
        "root": str(root),
        "checked_file_count": checked_files,
        "violation_count": len(violations),
        "violations": violations,
    }


def main() -> int:
    args = parse_args()
    result = validate(args.path, args.require_safe_manifest)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
