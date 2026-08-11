"""Derive a repository version string from its `release-*` git tags.

A model repo needs a version for two things: labelling a nightly build,
and naming the release channel that `releases-index.json` maps a darktable
version onto. Both want the same answer – "what release are we on, and how
far past it" – which `git describe` already computes.

Examples of what `describe_version` returns:

    release-5.6.0 tagged commit      "5.6.0"
    47 commits past release-5.6.0    "5.6.0+47~gXXXXXXX"
    dirty working tree               "5.6.0+47~gXXXXXXX~dirty"
    no release-* tag at all          bare commit hash
    not a git repo                   "unknown-version"

It never raises: CI runs on shallow clones and fresh repos with no tags,
and a version label is not worth failing a build over.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

UNKNOWN = "unknown-version"

# release-1.2.3 / release-1.2.3.4 → the leading numeric X.Y.Z
_PREFIX_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _git(args: list[str], root: Path | None) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(root) if root else None,
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = out.stdout.strip()
    return value or None


def describe_version(root: Path | None = None) -> str:
    """Full version string derived from the newest `release-*` tag."""
    described = _git(["describe", "--tags", "--dirty", "--match", "release-*"],
                     root)
    if described:
        # release-5.6.0-47-gabc1234 → 5.6.0+47~gabc1234
        value = described.removeprefix("release-")
        value = value.replace("-", "+", 1)
        return value.replace("-", "~", 1)

    # shallow clones may carry no tags; fall back to the bare commit
    return _git(["describe", "--always", "--dirty"], root) or UNKNOWN


def version_prefix(root: Path | None = None) -> str | None:
    """Just the X.Y.Z part, or None when no release tag was found.

    This is what a per-version release channel is keyed on – a nightly tag
    like `nightly-5.6.0`, matching an entry in `releases-index.json`.
    """
    match = _PREFIX_RE.match(describe_version(root))
    return match.group(0) if match else None
