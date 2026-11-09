"""Build/verify the fixed Climate Advisor contribution snapshot, never apply it.

Standard library only. This maintenance tool is Apache-2.0; its eight-file
upstream-specific payload is MIT. Hashes establish integrity, not authenticity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

BASE_COMMIT = "68c6c2d7ea63a921afed7a391253e448fb6a5ceb"
UPSTREAM_URL = "https://github.com/gunkl/ClimateAdvisor.git"
PAYLOAD_PATHS = (
    "custom_components/climate_advisor/adaptive_mode_preview.py",
    "custom_components/climate_advisor/sleep_timing.py",
    "custom_components/climate_advisor/sleep_trajectory.py",
    "docs/adaptive-mode-preview.md",
    "docs/sleep-trajectory-preview.md",
    "tests/test_adaptive_mode_preview.py",
    "tests/test_sleep_timing.py",
    "tests/test_sleep_trajectory.py",
)
DEFAULT_BUNDLE = (
    Path(__file__).resolve().parents[1] / "contributions" / "climate-advisor"
)


class BundleError(ValueError):
    """An unsafe, stale or malformed snapshot; nothing should be applied."""


def _check_path(
    path: Path, *, directory: bool = False, allow_missing: bool = False
) -> bool:
    """Reject redirects before reading, including Windows directory junctions."""
    path = path.absolute()
    for component in reversed((path, *path.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError as exc:
            if component == path and allow_missing:
                return False
            raise BundleError(f"Missing path: {component}") from exc
        except OSError as exc:
            raise BundleError(f"Cannot inspect {component}: {exc}") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise BundleError(f"Linked/redirected paths are not supported: {component}")
        if component != path or directory:
            if not stat.S_ISDIR(metadata.st_mode):
                raise BundleError(f"Expected a directory: {component}")
        elif not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BundleError(f"Expected a regular, non-linked file: {component}")
    return True


def _read_file(path: Path) -> bytes:
    _check_path(path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise BundleError(f"Cannot read {path}: {exc}") from exc


def _payload(data: bytes, name: str, *, normalize: bool = False) -> bytes:
    if normalize:
        data = data.replace(b"\r\n", b"\n")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError(f"Expected UTF-8 text: {name}") from exc
    if not data or not data.endswith(b"\n") or b"\0" in data or b"\r" in data:
        raise BundleError(
            f"Expected nonempty LF text with a final newline and no NUL: {name}"
        )
    return data


def _git(source: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-pager", "--no-optional-locks", "-C", str(source), *arguments],
            capture_output=True,
            check=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BundleError(
            f"Read-only Git check failed ({' '.join(arguments)}): {exc}"
        ) from exc
    return result.stdout


def read_source(source: Path) -> dict[str, bytes]:
    """Read exactly the approved additions from an otherwise unchanged pinned root."""
    source = source.absolute()
    _check_path(source, directory=True)
    try:
        git_root = Path(
            _git(source, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        )
    except UnicodeDecodeError as exc:
        raise BundleError("Git checkout root is not UTF-8") from exc
    if git_root.resolve() != source.resolve():
        raise BundleError(
            "--source must be the actual Git checkout root, not a subdirectory"
        )
    if _git(source, "rev-parse", "--verify", "HEAD").strip() != BASE_COMMIT.encode(
        "ascii"
    ):
        raise BundleError(f"Source HEAD must equal the pinned base {BASE_COMMIT}")
    status = _git(source, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    expected = [b"?? " + name.encode("ascii") for name in PAYLOAD_PATHS] + [b""]
    if sorted(status.split(b"\0")) != sorted(expected):
        raise BundleError(
            "Source Git status must contain exactly the eight untracked payload files; "
            "no tracked/staged changes or unrelated untracked files"
        )
    return {
        name: _payload(_read_file(source / name), name, normalize=True)
        for name in PAYLOAD_PATHS
    }


def _headers(name: str) -> list[bytes]:
    return [
        f"diff --git a/{name} b/{name}".encode("ascii"),
        b"new file mode 100644",
        b"--- /dev/null",
        f"+++ b/{name}".encode("ascii"),
    ]


def _make_patch(files: dict[str, bytes]) -> bytes:
    lines = []
    for name in PAYLOAD_PATHS:
        content = files[name][:-1].split(b"\n")
        lines.extend(_headers(name))
        lines.append(f"@@ -0,0 +1,{len(content)} @@".encode("ascii"))
        lines.extend(b"+" + line for line in content)
    return b"\n".join(lines) + b"\n"


def parse_patch(data: bytes) -> dict[str, bytes]:
    """Decode only our ordered, addition-only format; never trust patch paths."""
    _payload(data, "preview.patch")
    lines = data[:-1].split(b"\n")
    cursor = 0
    files = {}
    for name in PAYLOAD_PATHS:
        if lines[cursor : cursor + 4] != _headers(name):
            raise BundleError(f"Invalid addition headers or path/order for {name}")
        cursor += 4
        if cursor >= len(lines):
            raise BundleError(f"Missing hunk for {name}")
        match = re.fullmatch(rb"@@ -0,0 \+1,([1-9][0-9]*) @@", lines[cursor])
        if match is None:
            raise BundleError(f"Invalid addition hunk for {name}")
        try:
            count = int(match[1])
        except ValueError as exc:
            raise BundleError(f"Invalid hunk length for {name}") from exc
        cursor += 1
        if count > len(lines) - cursor:
            raise BundleError(f"Truncated addition for {name}")
        content = lines[cursor : cursor + count]
        if any(not line.startswith(b"+") for line in content):
            raise BundleError(f"Only added lines are allowed for {name}")
        files[name] = _payload(b"\n".join(line[1:] for line in content) + b"\n", name)
        cursor += count
    if cursor != len(lines):
        raise BundleError("Unexpected trailing patch content or extra files")
    return files


def _digest(name: str, data: bytes) -> dict[str, str | int]:
    return {
        "path": name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _make_manifest(patch_bytes: bytes, files: dict[str, bytes]) -> bytes:
    manifest = {
        "schema_version": 1,
        "upstream": {"url": UPSTREAM_URL, "base_commit": BASE_COMMIT},
        "license": "MIT",
        "patch": _digest("preview.patch", patch_bytes),
        "files": [_digest(name, files[name]) for name in PAYLOAD_PATHS],
    }
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_bundle(
    directory: Path = DEFAULT_BUNDLE, *, source: Path | None = None
) -> dict[str, bytes]:
    """Verify bytes and metadata without Git or executing the payload by default."""
    patch_bytes = _read_file(directory / "preview.patch")
    files = parse_patch(patch_bytes)
    # Comparing canonical bytes also rejects duplicate keys, extra fields and
    # altered provenance without accepting a more permissive JSON interpretation.
    if _read_file(directory / "manifest.json") != _make_manifest(patch_bytes, files):
        raise BundleError(
            "Bundle manifest does not match the canonical payload hashes/metadata"
        )
    if source is not None and read_source(source) != files:
        raise BundleError(
            "Source files differ from the verified bundle; review drift before rebuilding"
        )
    return files


def build_bundle(
    source: Path, directory: Path = DEFAULT_BUNDLE, *, replace: bool = False
) -> bool:
    """Write only the generated pair; False means identical existing output."""
    source, directory = source.absolute(), directory.absolute()
    _check_path(directory, directory=True)
    _check_path(source, directory=True)
    if directory.resolve().is_relative_to(source.resolve()):
        raise BundleError("Bundle output must be outside the source checkout")
    files = read_source(source)
    patch_bytes = _make_patch(files)
    outputs = {
        "preview.patch": patch_bytes,
        "manifest.json": _make_manifest(patch_bytes, files),
    }
    pending = {}
    # Preflight both destinations before any write, so refusal never updates one.
    for name, content in outputs.items():
        destination = directory / name
        if _check_path(destination, allow_missing=True):
            if _read_file(destination) == content:
                continue
            if not replace:
                raise BundleError(
                    f"Different existing {name}; review changes and use --replace intentionally"
                )
        pending[destination] = content
    try:
        for destination, content in pending.items():
            destination.write_bytes(content)
    except OSError as exc:
        raise BundleError(
            "Bundle write failed; the pair may be incomplete. Verify before use, "
            "then regenerate deliberately with --replace"
        ) from exc
    return bool(pending)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify", help="Verify the fixed bundle without applying/executing it"
    )
    verify.add_argument(
        "--source",
        type=Path,
        help="Also compare a pinned, otherwise unchanged checkout",
    )
    build = commands.add_parser(
        "build", help="Export only the eight approved additions"
    )
    build.add_argument("--source", type=Path, required=True)
    build.add_argument(
        "--replace",
        action="store_true",
        help="Allow replacing different generated output",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            files = verify_bundle(DEFAULT_BUNDLE, source=args.source)
            print(
                f"Verified {len(files)} MIT payload files against pinned base {BASE_COMMIT}."
            )
        else:
            changed = build_bundle(args.source, DEFAULT_BUNDLE, replace=args.replace)
            print(
                "Built 8-file contribution bundle."
                if changed
                else "Bundle already matches; no files written."
            )
    except BundleError as exc:
        print(f"Bundle error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
