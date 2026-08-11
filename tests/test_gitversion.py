"""Tests for deriving a repo version from `release-*` git tags.

Ported from darktable-ai's tools/get_git_version_string.sh; these pin the
exact output shape, since a nightly channel tag and `releases-index.json`
keys are built from it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dt_ai_sdk.gitversion import UNKNOWN, describe_version, version_prefix


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=root, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "f.txt").write_text("one\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_on_a_release_tag(repo: Path) -> None:
    _git(repo, "tag", "release-1.2.3")
    assert describe_version(repo) == "1.2.3"
    assert version_prefix(repo) == "1.2.3"


def test_commits_past_a_release_tag(repo: Path) -> None:
    _git(repo, "tag", "release-1.2.3")
    (repo / "f.txt").write_text("two\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second")

    version = describe_version(repo)
    # release-1.2.3-1-gHASH becomes 1.2.3+1~gHASH
    assert version.startswith("1.2.3+1~g"), version
    # the prefix stays the release it descends from – that's the channel
    assert version_prefix(repo) == "1.2.3"


def test_dirty_tree_is_marked(repo: Path) -> None:
    _git(repo, "tag", "release-1.2.3")
    (repo / "f.txt").write_text("uncommitted\n")
    assert describe_version(repo).endswith("dirty")


def test_no_release_tag_falls_back_to_commit(repo: Path) -> None:
    """Shallow CI clones and fresh repos have no tags; don't fail on it."""
    version = describe_version(repo)
    assert version != UNKNOWN
    assert len(version) >= 7          # a bare abbreviated hash
    # nothing to key a per-version channel on
    assert version_prefix(repo) is None


def test_four_part_release_tag(repo: Path) -> None:
    """darktable ships hotfix tags like release-5.6.0.1."""
    _git(repo, "tag", "release-5.6.0.1")
    assert describe_version(repo) == "5.6.0.1"
    assert version_prefix(repo) == "5.6.0"


def test_outside_a_git_repo(tmp_path: Path) -> None:
    assert describe_version(tmp_path) == UNKNOWN
    assert version_prefix(tmp_path) is None
