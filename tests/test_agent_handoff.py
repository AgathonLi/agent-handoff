#!/usr/bin/env python3
"""
Self-test suite for agent-handoff.

Covers the behaviour that distinguishes this implementation: the five-level
directory resolution chain, marker-based project root detection, refusal to
write when no root exists, heading levels 1-3 acceptance, level-4 sub-headings
not truncating their parent section, correct file-reference base path at
arbitrary handoff directory depth, credential blocking, and the non-git
staleness fallback.

Also covers the repository -> installed-copy sync, whose exclusion list is a
correctness constraint: copying AGENTS.md into an installed copy would turn that
directory into an apparent project root and reintroduce the stray-write defect.

Run:
    python tests/test_agent_handoff.py
    python tests/test_agent_handoff.py -v

Exit code 0 means every test passed. No third-party dependencies.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_to_host  # noqa: E402
from handoff_paths import (  # noqa: E402
    ProjectRootNotFound,
    find_project_root,
    read_config,
    resolve_handoff_dir,
)

FILLER = (
    "Real substantive content written here to clear the fifty character minimum "
    "for this section without leaving any placeholder text behind."
)


def run_script(name: str, *args: str, cwd: Path, env: dict | None = None):
    """Invoke one of the skill scripts as a subprocess."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=merged_env,
        timeout=60,
    )


class TempProject:
    """Context manager creating a throwaway project directory."""

    def __init__(self, marker: str = "AGENTS.md", git: bool = False):
        self.marker = marker
        self.git = git

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name).resolve()
        (self.path / self.marker).write_text("# test project\n", encoding="utf-8")
        (self.path / "app.py").write_text("x = 1\n", encoding="utf-8")
        if self.git:
            subprocess.run(
                ["git", "init", "-q"], cwd=str(self.path), capture_output=True
            )
        return self.path

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False


class TestProjectRootDetection(unittest.TestCase):
    def test_finds_root_from_nested_directory(self):
        with TempProject() as root:
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            self.assertEqual(find_project_root(deep), root)

    def test_recognizes_multiple_marker_types(self):
        for marker in ("AGENTS.md", "CLAUDE.md", "package.json", "pyproject.toml"):
            with TempProject(marker=marker) as root:
                self.assertEqual(find_project_root(root), root)

    def test_raises_when_no_marker_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / "nested" / "deeper"
            bare.mkdir(parents=True)
            # A marker may exist above the temp dir on some systems; only assert
            # the exception type when detection genuinely finds nothing.
            try:
                found = find_project_root(bare)
            except ProjectRootNotFound:
                return
            self.assertNotEqual(found, bare)


class TestDirectoryResolution(unittest.TestCase):
    def test_level5_default_is_host_neutral(self):
        with TempProject() as root:
            handoff_dir, project_root, source = resolve_handoff_dir(start=root)
            self.assertEqual(handoff_dir, root / ".handoff")
            self.assertEqual(project_root, root)
            self.assertIn("default", source)

    def test_level4_adopts_existing_layout_without_migrating(self):
        with TempProject() as root:
            legacy = root / ".workbuddy" / "handoffs"
            legacy.mkdir(parents=True)
            handoff_dir, _, source = resolve_handoff_dir(start=root)
            self.assertEqual(handoff_dir, legacy)
            self.assertIn("existing directory", source)
            self.assertFalse((root / ".handoff").exists())

    def test_level3_config_file(self):
        with TempProject() as root:
            (root / ".handoffrc").write_text("handoff_dir = docs/ho\n", encoding="utf-8")
            handoff_dir, _, source = resolve_handoff_dir(start=root)
            self.assertEqual(handoff_dir, root / "docs" / "ho")
            self.assertIn(".handoffrc", source)

    def test_level3_bare_path_form(self):
        with TempProject() as root:
            (root / ".handoffrc").write_text("custom-dir\n", encoding="utf-8")
            self.assertEqual(read_config(root), "custom-dir")

    def test_level3_ignores_comments_and_blanks(self):
        with TempProject() as root:
            (root / ".handoffrc").write_text(
                "# a comment\n\nhandoff_dir = real-dir\n", encoding="utf-8"
            )
            self.assertEqual(read_config(root), "real-dir")

    def test_level2_env_var_beats_config(self):
        with TempProject() as root:
            (root / ".handoffrc").write_text("from-rc\n", encoding="utf-8")
            os.environ["HANDOFF_DIR"] = "from-env"
            try:
                handoff_dir, _, source = resolve_handoff_dir(start=root)
            finally:
                del os.environ["HANDOFF_DIR"]
            self.assertEqual(handoff_dir, root / "from-env")
            self.assertIn("environment", source)

    def test_level1_cli_beats_everything(self):
        with TempProject() as root:
            (root / ".handoffrc").write_text("from-rc\n", encoding="utf-8")
            os.environ["HANDOFF_DIR"] = "from-env"
            try:
                handoff_dir, _, source = resolve_handoff_dir(
                    explicit="from-cli", start=root
                )
            finally:
                del os.environ["HANDOFF_DIR"]
            self.assertEqual(handoff_dir, root / "from-cli")
            self.assertIn("argument", source)


class TestCreateHandoff(unittest.TestCase):
    def test_writes_into_resolved_directory(self):
        with TempProject() as root:
            result = run_script("create_handoff.py", "my-task", cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            created = list((root / ".handoff").glob("*-my-task.md"))
            self.assertEqual(len(created), 1)

    def test_refuses_to_write_without_project_root(self):
        """The defining safety property: no silent write to cwd."""
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / "no-marker"
            bare.mkdir()
            result = run_script("create_handoff.py", "orphan", cwd=bare)
            if result.returncode == 0:
                # A marker existed above the temp dir; assert the file did not
                # land in the marker-less directory itself.
                self.assertFalse((bare / ".handoff").exists())
            else:
                self.assertEqual(result.returncode, 2)
                self.assertIn("No project root marker", result.stderr)

    def test_scaffold_uses_level_two_headings(self):
        with TempProject() as root:
            run_script("create_handoff.py", "heading-check", cwd=root)
            created = next((root / ".handoff").glob("*.md"))
            content = created.read_text(encoding="utf-8")
            for section in (
                "Current State Summary",
                "Important Context",
                "Immediate Next Steps",
            ):
                self.assertIn(f"## {section}", content)

    def test_chaining_links_previous_handoff(self):
        with TempProject() as root:
            run_script("create_handoff.py", "first", cwd=root)
            first = next((root / ".handoff").glob("*-first.md"))
            run_script(
                "create_handoff.py", "second", "--continues-from", first.name, cwd=root
            )
            second = next((root / ".handoff").glob("*-second.md"))
            self.assertIn(first.name, second.read_text(encoding="utf-8"))


class TestValidation(unittest.TestCase):
    def _write(self, root: Path, body: str, name: str = "h.md") -> Path:
        path = root / ".handoff"
        path.mkdir(parents=True, exist_ok=True)
        target = path / name
        target.write_text(body, encoding="utf-8")
        return target

    def _complete_doc(self, level: str = "##") -> str:
        # Every required section needs >= 50 chars of content, including the
        # last one. A short final section is a realistic authoring mistake and
        # the validator is expected to catch it; see
        # test_flags_short_final_section.
        return (
            f"# Handoff: test\n\n"
            f"{level} Current State Summary\n\n{FILLER}\n\n"
            f"{level} Important Context\n\n{FILLER}\n\n"
            f"{level} Immediate Next Steps\n\n"
            f"1. Do the first thing that matters most to the next agent here.\n"
            f"2. Then verify the change behaves as the handoff describes.\n"
        )

    def test_accepts_level_three_headings(self):
        """Upstream matched only #/## and scored ### as missing."""
        with TempProject() as root:
            doc = self._write(root, self._complete_doc("###"))
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("All required sections complete", result.stdout)

    def test_accepts_level_two_headings(self):
        with TempProject() as root:
            doc = self._write(root, self._complete_doc("##"))
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("All required sections complete", result.stdout)

    def test_level_four_subheading_stays_inside_parent(self):
        """A #### sub-heading must not truncate its parent section."""
        body = (
            "# Handoff: test\n\n"
            "## Current State Summary\n\n"
            "#### A sub heading\n\n"
            f"{FILLER}\n\n"
            f"## Important Context\n\n{FILLER}\n\n"
            "## Immediate Next Steps\n\n"
            "1. Confirm the parent section survived the sub heading intact.\n"
            "2. Confirm the content below the sub heading was still counted.\n"
        )
        with TempProject() as root:
            doc = self._write(root, body)
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("All required sections complete", result.stdout)

    def test_flags_short_final_section(self):
        """The last section has no following heading; length must still apply.

        Section content runs to end-of-file when no further heading exists. That
        path is easy to get wrong, so it is pinned here: a too-short final
        section must be reported as incomplete rather than passing by default.
        """
        body = (
            "# Handoff: test\n\n"
            f"## Current State Summary\n\n{FILLER}\n\n"
            f"## Important Context\n\n{FILLER}\n\n"
            "## Immediate Next Steps\n\n1. Too short.\n"
        )
        with TempProject() as root:
            doc = self._write(root, body)
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("Immediate Next Steps (incomplete", result.stdout)

    def test_flags_remaining_todos(self):
        with TempProject() as root:
            run_script("create_handoff.py", "unfilled", cwd=root)
            doc = next((root / ".handoff").glob("*.md"))
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TODO placeholder", result.stdout)

    def test_blocks_on_credentials(self):
        body = self._complete_doc() + '\napi_key = "AKIAIOSFODNN7EXAMPLE"\n'
        with TempProject() as root:
            doc = self._write(root, body)
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("BLOCKED", result.stdout)
            self.assertNotEqual(result.returncode, 0)

    def test_resolves_file_references_at_single_level_depth(self):
        """Depth-counting broke here; marker detection must not."""
        body = (
            self._complete_doc()
            + "\n## Critical Files\n\n| File | Purpose | Relevance |\n"
            "|------|---------|-----------|\n| app.py | entry point | core |\n"
            "\nSee `app.py` for the entry point.\n"
        )
        with TempProject() as root:
            doc = self._write(root, body)
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertNotIn("referenced file(s) not found", result.stdout)

    def test_complete_document_scores_full_marks(self):
        with TempProject() as root:
            run_script("create_handoff.py", "scored", cwd=root)
            doc = next((root / ".handoff").glob("*.md"))
            content = doc.read_text(encoding="utf-8")
            import re

            doc.write_text(
                re.sub(r"\[TODO:[^\]]*\]", FILLER, content), encoding="utf-8"
            )
            result = run_script("validate_handoff.py", str(doc), cwd=root)
            self.assertIn("100/100", result.stdout)
            self.assertEqual(result.returncode, 0)


class TestListing(unittest.TestCase):
    def test_reports_resolution_source(self):
        with TempProject() as root:
            run_script("create_handoff.py", "listed", cwd=root)
            result = run_script("list_handoffs.py", cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Resolved via", result.stdout)
            self.assertIn("Found 1 handoff", result.stdout)

    def test_empty_directory_is_not_an_error(self):
        with TempProject() as root:
            result = run_script("list_handoffs.py", cwd=root)
            self.assertEqual(result.returncode, 0)
            self.assertIn("No handoffs found", result.stdout)

    def test_json_mode_is_parseable(self):
        import json

        with TempProject() as root:
            run_script("create_handoff.py", "as-json", cwd=root)
            result = run_script("list_handoffs.py", "--json", cwd=root)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            self.assertIn("resolved_via", payload)


class TestStaleness(unittest.TestCase):
    def test_non_git_project_gets_a_real_verdict(self):
        """Upstream returned UNKNOWN for every non-git project."""
        with TempProject(git=False) as root:
            run_script("create_handoff.py", "nogit", cwd=root)
            doc = next((root / ".handoff").glob("*.md"))
            result = run_script("check_staleness.py", str(doc), cwd=root)
            self.assertNotIn("UNKNOWN", result.stdout)
            self.assertIn("file modification times", result.stdout)
            self.assertIn("FRESH", result.stdout)

    def test_git_project_uses_git_history(self):
        with TempProject(git=True) as root:
            run_script("create_handoff.py", "withgit", cwd=root)
            doc = next((root / ".handoff").glob("*.md"))
            result = run_script("check_staleness.py", str(doc), cwd=root)
            self.assertIn("git history", result.stdout)

    def test_fresh_handoff_exits_zero(self):
        with TempProject() as root:
            run_script("create_handoff.py", "fresh", cwd=root)
            doc = next((root / ".handoff").glob("*.md"))
            result = run_script("check_staleness.py", str(doc), cwd=root)
            self.assertEqual(result.returncode, 0)


class TestHostSync(unittest.TestCase):
    """The repo -> installed-copy sync must not leak development files."""

    def test_excludes_root_markers(self):
        """AGENTS.md in an installed copy would make it look like a project root.

        Running a script from there would then write handoffs into the skill's
        own directory instead of failing loudly -- the defect this skill exists
        to prevent. This is a correctness constraint, not tidiness.
        """
        payload = sync_to_host.collect_payload(REPO_ROOT)
        for marker in ("AGENTS.md", "CLAUDE.md", ".handoffrc", "pyproject.toml"):
            self.assertNotIn(
                marker,
                payload,
                f"{marker} is a project-root marker and must never be synced",
            )

    def test_excludes_development_only_paths(self):
        payload = sync_to_host.collect_payload(REPO_ROOT)
        for relative in payload:
            self.assertFalse(
                relative.startswith("tests/"),
                f"test file leaked into the sync payload: {relative}",
            )
            self.assertFalse(
                relative.startswith(".github/"),
                f"CI config leaked into the sync payload: {relative}",
            )
        self.assertNotIn("scripts/sync_to_host.py", payload)
        self.assertNotIn(".gitattributes", payload)

    def test_payload_is_an_allowlist_not_a_blocklist(self):
        """Any new top-level entry must be opted in, never opted out.

        EXCLUDED_NAMES enumerates what to withhold, so a newly added local
        directory -- host session memory, a scratch dir, an editor workspace --
        silently ships to every installed copy until someone remembers to add
        it. That already happened once with .workbuddy/. Pinning the permitted
        set turns the next occurrence into a test failure instead of a leak.
        """
        permitted_top_level = {
            ".gitignore",
            "LICENSE",
            "README.md",
            "README.zh-CN.md",
            "SKILL.md",
            "references",
            "scripts",
        }
        payload = sync_to_host.collect_payload(REPO_ROOT)
        actual_top_level = {relative.split("/", 1)[0] for relative in payload}
        unexpected = actual_top_level - permitted_top_level
        self.assertEqual(
            set(),
            unexpected,
            f"unapproved entries reached the sync payload: {sorted(unexpected)}. "
            "Add them to EXCLUDED_NAMES, or to this allowlist if the installed "
            "skill genuinely needs them at runtime.",
        )

    def test_both_readme_languages_ship_together(self):
        """Each README links to the other, so shipping one alone breaks the link.

        An installed copy carrying only README.md would render a "简体中文"
        link that resolves to nothing.
        """
        payload = sync_to_host.collect_payload(REPO_ROOT)
        self.assertIn("README.md", payload)
        self.assertIn("README.zh-CN.md", payload)

        english = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        # Assert that each file links to the other, without pinning the markup.
        # The switcher is an HTML block so it can be right-aligned, which
        # Markdown link syntax cannot express; checking for a literal
        # "[text](target)" would make a purely visual change fail the suite.
        def links_to(document: str, target: str) -> bool:
            return f"]({target})" in document or f'href="{target}"' in document

        for source, target in (
            (english, "./README.zh-CN.md"),
            (chinese, "./README.md"),
        ):
            self.assertTrue(
                links_to(source, target) or links_to(source, target[2:]),
                f"a README no longer links to {target}",
            )

    def test_includes_everything_the_skill_needs_at_runtime(self):
        payload = sync_to_host.collect_payload(REPO_ROOT)
        required = [
            "SKILL.md",
            "README.md",
            "README.zh-CN.md",
            "LICENSE",
            "scripts/handoff_paths.py",
            "scripts/create_handoff.py",
            "scripts/validate_handoff.py",
            "scripts/list_handoffs.py",
            "scripts/check_staleness.py",
            "references/handoff-template.md",
            "references/resume-checklist.md",
        ]
        for relative in required:
            self.assertIn(relative, payload, f"{relative} missing from sync payload")

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            target.mkdir()
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            self.assertEqual(len(actions["new"]), len(payload))
            self.assertEqual(list(target.iterdir()), [])

    def test_apply_then_verify_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            target.mkdir(parents=True)
            sync_to_host.apply_plan(payload, target, actions)

            self.assertEqual(sync_to_host.verify(payload, target), [])
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertFalse((target / "tests").exists())
            self.assertTrue((target / "scripts" / "handoff_paths.py").exists())

            # A second run must be a no-op.
            again = sync_to_host.plan(payload, target, prune=False)
            self.assertEqual(again["new"], [])
            self.assertEqual(again["changed"], [])

    def test_prune_spares_host_written_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            target.mkdir(parents=True)
            sync_to_host.apply_plan(payload, target, actions)

            (target / "_meta.json").write_text("{}", encoding="utf-8")
            (target / "leftover.md").write_text("stale\n", encoding="utf-8")

            pruning = sync_to_host.plan(payload, target, prune=True)
            self.assertIn("leftover.md", pruning["stale"])
            self.assertNotIn("_meta.json", pruning["stale"])

            sync_to_host.apply_plan(payload, target, pruning)
            self.assertFalse((target / "leftover.md").exists())
            self.assertTrue((target / "_meta.json").exists())

    def test_prune_removes_directories_it_empties(self):
        """Deleting files alone leaves hollow tests/ and .github/ behind."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            target.mkdir(parents=True)
            sync_to_host.apply_plan(payload, target, actions)

            leftover_dir = target / "tests"
            leftover_dir.mkdir()
            (leftover_dir / "test_old.py").write_text("# stale\n", encoding="utf-8")

            pruning = sync_to_host.plan(payload, target, prune=True)
            self.assertIn("tests/test_old.py", pruning["stale"])

            sync_to_host.apply_plan(payload, target, pruning)
            self.assertFalse(leftover_dir.exists(), "empty tests/ was left behind")
            # Directories the payload still needs must survive.
            self.assertTrue((target / "scripts").is_dir())
            self.assertTrue((target / "references").is_dir())

    def test_prune_collapses_nested_empty_directories(self):
        """One bottom-up sweep strips only a single level per nesting depth.

        os.walk fixes a directory's child list when it first visits the parent,
        so removing a/b/ during a pass leaves a/ still looking non-empty in that
        same pass. Observed with .workbuddy/memory/: the file and memory/ went,
        while .workbuddy/ survived and the copy still looked contaminated.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            target.mkdir(parents=True)
            sync_to_host.apply_plan(payload, target, actions)

            deep = target / "leaked" / "level2" / "level3"
            deep.mkdir(parents=True)
            (deep / "note.md").write_text("stale\n", encoding="utf-8")

            pruning = sync_to_host.plan(payload, target, prune=True)
            self.assertIn("leaked/level2/level3/note.md", pruning["stale"])

            sync_to_host.apply_plan(payload, target, pruning)
            self.assertFalse(
                (target / "leaked").exists(),
                "nested empty directories were not collapsed to the top",
            )
            self.assertTrue((target / "scripts").is_dir())

    def test_prune_cleans_a_copy_whose_only_flaw_is_an_empty_dir(self):
        """An already-hollow directory yields no stale entries to key off.

        Cleanup used to run only when stale was non-empty, so a copy already in
        file-level sync reported "already in sync" and the directory survived
        every subsequent run. _find_empty_dirs makes the hollow directory itself
        a unit of pending work.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed"
            payload = sync_to_host.collect_payload(REPO_ROOT)
            actions = sync_to_host.plan(payload, target, prune=False)
            target.mkdir(parents=True)
            sync_to_host.apply_plan(payload, target, actions)

            (target / "hollow" / "deeper").mkdir(parents=True)

            pruning = sync_to_host.plan(payload, target, prune=True)
            self.assertEqual(pruning["stale"], [], "an empty dir holds no files")
            self.assertEqual(
                [d.name for d in sync_to_host._find_empty_dirs(target)],
                ["hollow"],
                "the hollow directory must be reported as pending work",
            )

            sync_to_host.apply_plan(payload, target, pruning, prune=True)
            self.assertFalse((target / "hollow").exists())
            self.assertEqual(sync_to_host.verify(payload, target), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
