"""Local contribution packaging; Git responses are mocked, code is never applied."""

import hashlib
import io
import json
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import climate_advisor_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PATHS = (
    "custom_components/climate_advisor/adaptive_mode_preview.py",
    "custom_components/climate_advisor/sleep_timing.py",
    "custom_components/climate_advisor/sleep_trajectory.py",
    "docs/adaptive-mode-preview.md",
    "docs/sleep-trajectory-preview.md",
    "tests/test_adaptive_mode_preview.py",
    "tests/test_sleep_timing.py",
    "tests/test_sleep_trajectory.py",
)
BASE = "68c6c2d7ea63a921afed7a391253e448fb6a5ceb"


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "checkout with spaces"
        self.output = self.root / "bundle"
        self.source.mkdir()
        self.output.mkdir()
        self.payloads = {}
        for name in EXPECTED_PATHS:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            content = f'# {name}\nvalue = "café"\n\n'.encode()
            path.write_bytes(content)
            self.payloads[name] = content
        self.git_root = self.source.as_posix().encode() + b"\n"
        self.head = BASE.encode() + b"\n"
        self.status = b"".join(
            b"?? " + name.encode() + b"\0" for name in EXPECTED_PATHS
        )
        runner = patch.object(bundle.subprocess, "run", side_effect=self.git_response)
        self.git = runner.start()
        self.addCleanup(runner.stop)

    def git_response(self, command, **kwargs):
        self.assertEqual(
            command[:4], ["git", "--no-pager", "--no-optional-locks", "-C"]
        )
        self.assertEqual(Path(command[4]), self.source)
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertGreater(kwargs["timeout"], 0)
        self.assertNotIn("shell", kwargs)
        commands = {
            ("rev-parse", "--show-toplevel"): self.git_root,
            ("rev-parse", "--verify", "HEAD"): self.head,
            ("status", "--porcelain=v1", "-z", "--untracked-files=all"): self.status,
        }
        self.assertIn(tuple(command[5:]), commands)
        return subprocess.CompletedProcess(
            command, 0, commands[tuple(command[5:])], b""
        )

    def build(self, **kwargs):
        return bundle.build_bundle(self.source, self.output, **kwargs)

    def verify(self, **kwargs):
        return bundle.verify_bundle(self.output, **kwargs)

    def generated(self):
        return {
            name: (self.output / name).read_bytes()
            for name in ("preview.patch", "manifest.json")
        }

    def test_fixed_allowlist_base_and_license(self):
        self.assertEqual(bundle.PAYLOAD_PATHS, EXPECTED_PATHS)
        self.assertEqual(bundle.BASE_COMMIT, BASE)
        self.build()
        manifest = json.loads((self.output / "manifest.json").read_bytes())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["upstream"],
            {
                "url": "https://github.com/gunkl/ClimateAdvisor.git",
                "base_commit": BASE,
            },
        )
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(
            [item["path"] for item in manifest["files"]], list(EXPECTED_PATHS)
        )

    def test_deterministic_build_round_trip_and_source_unchanged(self):
        self.assertTrue(self.build())
        first = self.generated()
        self.assertEqual(self.verify(source=self.source), self.payloads)
        self.assertFalse(self.build())
        self.assertEqual(first, self.generated())
        self.assertEqual(
            {name: (self.source / name).read_bytes() for name in EXPECTED_PATHS},
            self.payloads,
        )
        self.assertEqual({path.name for path in self.output.iterdir()}, set(first))
        for content in first.values():
            self.assertNotIn(str(self.source).encode(), content)
            self.assertNotIn(b"\r", content)
            self.assertTrue(content.endswith(b"\n"))

    def test_crlf_source_normalizes_to_the_same_artifact(self):
        self.build()
        first = self.generated()
        for name, content in self.payloads.items():
            (self.source / name).write_bytes(content.replace(b"\n", b"\r\n"))
        self.assertFalse(self.build())
        self.assertEqual(first, self.generated())
        self.assertEqual(self.verify(source=self.source), self.payloads)

    def test_manifest_sizes_and_hashes_are_independently_checkable(self):
        self.build()
        manifest = json.loads((self.output / "manifest.json").read_bytes())
        patch_bytes = (self.output / "preview.patch").read_bytes()
        self.assertEqual(
            manifest["patch"],
            {
                "path": "preview.patch",
                "bytes": len(patch_bytes),
                "sha256": hashlib.sha256(patch_bytes).hexdigest(),
            },
        )
        for entry in manifest["files"]:
            content = self.payloads[entry["path"]]
            self.assertEqual(entry["bytes"], len(content))
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())

    def test_verify_without_source_never_invokes_git(self):
        self.build()
        self.git.reset_mock()
        self.git.side_effect = AssertionError("Verification must not need Git")
        self.assertEqual(self.verify(), self.payloads)
        self.git.assert_not_called()

    def test_verify_needs_no_checkout_and_does_not_execute_python(self):
        content = b'raise AssertionError("Payload must never execute")\n'
        (self.source / EXPECTED_PATHS[0]).write_bytes(content)
        self.build()
        self.source.rename(self.root / "unavailable checkout")
        self.git.side_effect = AssertionError("No Git")
        with patch.object(
            bundle, "read_source", side_effect=AssertionError("No source reads")
        ):
            self.assertEqual(self.verify()[EXPECTED_PATHS[0]], content)

    def test_source_drift_is_rejected(self):
        self.build()
        (self.source / EXPECTED_PATHS[0]).write_bytes(b"changed\n")
        with self.assertRaisesRegex(bundle.BundleError, "Source.*differ"):
            self.verify(source=self.source)

    def test_changed_output_requires_explicit_replace(self):
        self.build()
        first = self.generated()
        (self.source / EXPECTED_PATHS[0]).write_bytes(b"changed\n")
        with self.assertRaisesRegex(bundle.BundleError, "--replace"):
            self.build()
        self.assertEqual(first, self.generated())
        self.assertTrue(self.build(replace=True))
        self.assertEqual(
            self.verify(source=self.source)[EXPECTED_PATHS[0]], b"changed\n"
        )

    def test_identical_rebuild_does_not_write(self):
        self.build()
        with patch.object(
            Path, "write_bytes", side_effect=AssertionError("No rewrite")
        ):
            self.assertFalse(self.build())

    def test_corrupt_existing_output_is_not_silently_repaired(self):
        self.build()
        (self.output / "manifest.json").write_bytes(b"keep this\n")
        with self.assertRaisesRegex(bundle.BundleError, "--replace"):
            self.build()
        self.assertEqual((self.output / "manifest.json").read_bytes(), b"keep this\n")

    def test_second_destination_refusal_does_not_create_the_first(self):
        manifest = self.output / "manifest.json"
        manifest.write_bytes(b"keep this\n")
        with self.assertRaisesRegex(bundle.BundleError, "--replace"):
            self.build()
        self.assertFalse((self.output / "preview.patch").exists())
        self.assertEqual(manifest.read_bytes(), b"keep this\n")

    def test_invalid_second_destination_does_not_replace_the_first(self):
        self.build()
        first = self.generated()
        (self.source / EXPECTED_PATHS[0]).write_bytes(b"changed\n")
        lstat = Path.lstat

        def redirected(path):
            if path == self.output / "manifest.json":
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return lstat(path)

        with (
            patch.object(Path, "lstat", redirected),
            self.assertRaises(bundle.BundleError),
        ):
            self.build(replace=True)
        self.assertEqual(self.generated(), first)

    def test_partial_pair_fails_verification_and_can_be_regenerated(self):
        self.build()
        (self.output / "manifest.json").unlink()
        with self.assertRaises(bundle.BundleError):
            self.verify()
        self.assertTrue(self.build())
        self.assertEqual(self.verify(), self.payloads)

    def test_write_failure_leaves_detectably_invalid_pair(self):
        self.build()
        (self.source / EXPECTED_PATHS[0]).write_bytes(b"changed\n")
        write = Path.write_bytes

        def fail_manifest(path, data):
            if path.name == "manifest.json":
                raise OSError("synthetic write failure")
            return write(path, data)

        with (
            patch.object(Path, "write_bytes", fail_manifest),
            self.assertRaises(bundle.BundleError),
        ):
            self.build(replace=True)
        with self.assertRaises(bundle.BundleError):
            self.verify()
        self.assertTrue(self.build(replace=True))
        self.verify(source=self.source)

    def test_wrong_base_is_rejected_before_writing(self):
        self.head = b"0" * 40 + b"\n"
        with self.assertRaisesRegex(bundle.BundleError, "base|HEAD"):
            self.build()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_nested_or_wrong_checkout_root_is_rejected(self):
        self.git_root = self.root.as_posix().encode() + b"\n"
        with self.assertRaisesRegex(bundle.BundleError, "root"):
            self.build()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_status_requires_exact_untracked_allowlist(self):
        original = self.status
        cases = (
            b"",
            original + b"?? private.txt\0",
            original + b" M uv.lock\0",
            original.replace(b"?? ", b"A  ", 1),
            original.replace(b"?? ", b" M ", 1),
            original + b"R  new.py\0old.py\0",
            original[:-1],
            original + b"?? " + EXPECTED_PATHS[0].encode() + b"\0",
            original.replace(EXPECTED_PATHS[0].encode(), b"../escape.py"),
        )
        for value in cases:
            with self.subTest(status=value):
                self.status = value
                with self.assertRaisesRegex(bundle.BundleError, "status|untracked"):
                    self.build()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_git_status_order_does_not_change_output(self):
        self.build()
        first = self.generated()
        self.status = b"\0".join(reversed(self.status[:-1].split(b"\0"))) + b"\0"
        self.assertFalse(self.build())
        self.assertEqual(first, self.generated())

    def test_git_missing_failed_and_timeout_are_actionable_errors(self):
        for error in (
            FileNotFoundError("git"),
            subprocess.CalledProcessError(128, ["git"], stderr=b"not a repository"),
            subprocess.TimeoutExpired(["git"], 20),
        ):
            with self.subTest(error=type(error).__name__):
                self.git.side_effect = error
                with self.assertRaisesRegex(bundle.BundleError, "Git|git"):
                    self.build()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_invalid_source_text_is_rejected(self):
        path = self.source / EXPECTED_PATHS[0]
        for content in (
            b"",
            b"no final newline",
            b"bare\rreturn\n",
            b"nul\0\n",
            b"\xff\n",
        ):
            with self.subTest(content=content):
                path.write_bytes(content)
                with self.assertRaises(bundle.BundleError):
                    self.build()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_and_nonregular_source_files_are_rejected(self):
        path = self.source / EXPECTED_PATHS[0]
        path.unlink()
        with self.assertRaises(bundle.BundleError):
            self.build()
        path.mkdir()
        with self.assertRaises(bundle.BundleError):
            self.build()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_symlink_and_windows_reparse_paths_are_rejected(self):
        # Mock lstat so this also runs without Windows symlink privileges.
        lstat = Path.lstat
        for target in (
            self.source,
            self.source / "custom_components",
            self.source / EXPECTED_PATHS[0],
            self.output,
        ):
            for mode, attributes in ((stat.S_IFLNK, 0), (stat.S_IFDIR, 0x400)):
                with self.subTest(target=target, mode=mode):

                    def redirected(
                        path, target=target, mode=mode, attributes=attributes
                    ):
                        if path == target:
                            return SimpleNamespace(
                                st_mode=mode, st_file_attributes=attributes
                            )
                        return lstat(path)

                    with (
                        patch.object(Path, "lstat", redirected),
                        self.assertRaisesRegex(
                            bundle.BundleError, "link|redirect|reparse"
                        ),
                    ):
                        self.build()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_nonregular_or_linked_generated_files_are_not_overwritten(self):
        self.build()
        path = self.output / "preview.patch"
        lstat = Path.lstat
        for mode, attributes, links in (
            (stat.S_IFLNK, 0, 1),
            (stat.S_IFREG, 0x400, 1),
            (stat.S_IFREG, 0, 2),
            (stat.S_IFDIR, 0, 1),
        ):
            with self.subTest(mode=mode, attributes=attributes, links=links):

                def redirected(current, mode=mode, attributes=attributes, links=links):
                    if current == path:
                        return SimpleNamespace(
                            st_mode=mode, st_file_attributes=attributes, st_nlink=links
                        )
                    return lstat(current)

                with patch.object(Path, "lstat", redirected):
                    with self.assertRaises(bundle.BundleError):
                        self.build(replace=True)
                    with self.assertRaises(bundle.BundleError):
                        self.verify()

    def test_output_cannot_be_inside_source(self):
        with self.assertRaises(bundle.BundleError):
            bundle.build_bundle(self.source, self.source, replace=True)
        self.assertFalse((self.source / "preview.patch").exists())

    def test_malformed_patch_structure_and_paths_are_rejected(self):
        self.build()
        original = (self.output / "preview.patch").read_bytes()
        first = EXPECTED_PATHS[0].encode()
        mutations = (
            original + b"trailing content\n",
            original + original,
            original[:-1],
            original.replace(b"\n", b"\r\n"),
            original.replace(first, b"../escape.py"),
            original.replace(first, b"/absolute.py"),
            original.replace(first, b"C:/escape.py"),
            original.replace(first, b"custom_components\\escape.py"),
            original.replace(b"100644", b"120000", 1),
            original.replace(b"--- /dev/null", b"--- a/existing.py", 1),
            original.replace(b"@@ -0,0 +1,3 @@", b"@@ -0,0 +1,0 @@", 1),
            original.replace(b"@@ -0,0 +1,3 @@", b"@@ -0,0 +1,4 @@", 1),
            original.replace(b"@@ -0,0 +1,3 @@", b"@@ -1,1 +1,3 @@", 1),
            original.replace(b"+# ", b"-# ", 1),
            original.replace(b"+value", b"+\x00value", 1),
            original.replace(b"+value", b"+\xffvalue", 1),
        )
        for content in mutations:
            with self.subTest(prefix=content[:120]):
                self.assertNotEqual(content, original)
                with self.assertRaises(bundle.BundleError):
                    bundle.parse_patch(content)
        self.assertEqual(bundle.parse_patch(original), self.payloads)

    def test_manifest_drift_or_noncanonical_format_is_rejected(self):
        self.build()
        path = self.output / "manifest.json"
        original = path.read_bytes()
        mutations = (
            original.replace(BASE.encode(), b"0" * 40),
            original.replace(b'"MIT"', b'"Apache-2.0"'),
            original.replace(b'"schema_version": 1', b'"schema_version": true'),
            original + b"\n",
            original.replace(b"\n", b"\r\n"),
            b"{}\n",
            b"\xff",
        )
        for content in mutations:
            with self.subTest(content=content[:80]):
                self.assertNotEqual(content, original)
                path.write_bytes(content)
                with self.assertRaises(bundle.BundleError):
                    self.verify()

    def test_valid_patch_content_change_still_fails_manifest_hash(self):
        self.build()
        path = self.output / "preview.patch"
        path.write_bytes(path.read_bytes().replace(b"+value", b"+other", 1))
        with self.assertRaisesRegex(bundle.BundleError, "manifest"):
            self.verify()

    def test_cli_verify_defaults_to_local_bundle_without_git(self):
        self.build()
        self.git.reset_mock()
        with (
            patch.object(bundle, "DEFAULT_BUNDLE", self.output),
            redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(bundle.main(["verify"]), 0)
        self.assertIn("8", out.getvalue())
        self.git.assert_not_called()

    def test_cli_build_and_source_verification(self):
        with (
            patch.object(bundle, "DEFAULT_BUNDLE", self.output),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(bundle.main(["build", "--source", str(self.source)]), 0)
            self.assertEqual(bundle.main(["verify", "--source", str(self.source)]), 0)
            self.assertEqual(
                bundle.main(["build", "--source", str(self.source), "--replace"]), 0
            )

    def test_cli_failures_are_clear_and_do_not_print_tracebacks(self):
        with (
            patch.object(bundle, "DEFAULT_BUNDLE", self.output),
            redirect_stderr(io.StringIO()) as err,
        ):
            self.assertEqual(bundle.main(["verify"]), 2)
        self.assertNotIn("Traceback", err.getvalue())
        with redirect_stderr(io.StringIO()):
            for arguments in (["build"], ["verify", "--replace"], ["apply"]):
                with (
                    self.subTest(arguments=arguments),
                    self.assertRaises(SystemExit) as result,
                ):
                    bundle.main(arguments)
                self.assertEqual(result.exception.code, 2)


class ShippedBundleTests(unittest.TestCase):
    def test_actual_bundle_verifies_without_checkout_or_git(self):
        with patch.object(
            bundle.subprocess, "run", side_effect=AssertionError("No Git needed")
        ):
            files = bundle.verify_bundle(ROOT / "contributions" / "climate-advisor")
        self.assertEqual(tuple(files), EXPECTED_PATHS)
        for content in files.values():
            self.assertGreater(len(content), 0)


if __name__ == "__main__":
    unittest.main()
