"""Tests for the SDK's own `dtai` entry point.

The design these pin down: `dtai` is owned by exactly one package. It
carries every command, finds the repo root from the cwd, and picks up
repo-specific commands via `[tool.dtai] extend` – so a model repository
never has to ship a competing console script.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

import dt_ai_sdk.cli.common as common
from dt_ai_sdk.__main__ import _read_extension_target, main

MINIMAL_YAML = """\
id: {mid}
name: {mid}
description: fixture
task: general
"""

PYPROJECT = "[project]\nname='dummy'\nversion='0.1.0'\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo on disk, with the cwd inside it so the root is discoverable."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    d = tmp_path / "models" / "alpha"
    d.mkdir(parents=True)
    (d / "model.yaml").write_text(MINIMAL_YAML.format(mid="alpha"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_group_state():
    """The group caches its extension load; tests must not leak into each other."""
    yield
    main._extension_loaded = False
    common.set_sync_deps_hook(None)


# ---- the full command set ships on the SDK's dtai ----

def test_all_commands_are_mounted() -> None:
    names = set(main.commands)
    assert names == {"init", "setup", "convert", "validate",
                     "package", "list", "run", "versions", "git-version"}


# ---- lazy root resolution ----

def test_commands_find_the_root_from_cwd(repo: Path) -> None:
    """No wiring: `dtai list` works inside a repo with nothing configured."""
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output


def test_convert_works_unwired(repo: Path) -> None:
    result = CliRunner().invoke(main, ["convert", "alpha"])
    assert result.exit_code == 0, result.output
    assert (repo / "output" / "alpha" / "config.json").is_file()


def test_root_requiring_command_outside_a_repo_errors_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code != 0
    assert "Could not find project root" in result.output


def test_init_works_outside_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason the root is resolved lazily rather than in the callback."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", str(tmp_path / "fresh"),
                                       "--name", "fresh"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "fresh" / "pyproject.toml").is_file()


# ---- [tool.dtai] extend ----

def test_read_extension_target(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        PYPROJECT + '\n[tool.dtai]\nextend = "my_pkg.cli"\n')
    assert _read_extension_target(tmp_path) == "my_pkg.cli"


def test_read_extension_target_absent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    assert _read_extension_target(tmp_path) is None
    assert _read_extension_target(tmp_path / "nonexistent") is None


def test_read_extension_target_survives_malformed_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml")
    assert _read_extension_target(tmp_path) is None


def _write_extension(repo: Path, module: str, body: str) -> None:
    """Add an importable extension module and point pyproject at it."""
    pkg = repo / module
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(textwrap.dedent(body))
    (repo / "pyproject.toml").write_text(
        PYPROJECT + f'\n[tool.dtai]\nextend = "{module}.cli"\n')
    sys.path.insert(0, str(repo))


def test_extension_command_is_picked_up(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(repo))
    _write_extension(repo, "ext_pkg", """
        import click
        from dt_ai_sdk.__main__ import main

        @main.command("demo")
        def demo_cmd():
            click.echo("demo ran")
    """)
    try:
        result = CliRunner().invoke(main, ["demo"])
        assert result.exit_code == 0, result.output
        assert "demo ran" in result.output
    finally:
        main.commands.pop("demo", None)
        sys.modules.pop("ext_pkg.cli", None)
        sys.modules.pop("ext_pkg", None)


def test_extension_registers_a_sync_hook(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook a repo can't express in YAML, armed by import alone."""
    monkeypatch.syspath_prepend(str(repo))
    _write_extension(repo, "hook_pkg", """
        from pathlib import Path
        from dt_ai_sdk.cli import set_sync_deps_hook

        def _hook(cfg):
            Path(cfg.root_dir, "hook-fired.txt").write_text(cfg.id)

        set_sync_deps_hook(_hook)
    """)
    try:
        result = CliRunner().invoke(main, ["convert", "alpha"])
        assert result.exit_code == 0, result.output
        assert (repo / "hook-fired.txt").read_text() == "alpha"
    finally:
        sys.modules.pop("hook_pkg.cli", None)
        sys.modules.pop("hook_pkg", None)


def test_broken_extension_fails_loudly(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declared-but-unimportable extension must not silently vanish."""
    (repo / "pyproject.toml").write_text(
        PYPROJECT + '\n[tool.dtai]\nextend = "no_such_module_xyz"\n')
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code != 0
    assert "could not import CLI extension" in result.output


def test_no_extension_declared_is_fine(repo: Path) -> None:
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0, result.output


# ---- versions ----

def test_versions_writes_model_versions(repo: Path) -> None:
    result = CliRunner().invoke(main, ["versions"])
    assert result.exit_code == 0, result.output

    import json
    data = json.loads((repo / "output" / "versions.json").read_text())
    assert data == {"models": {"alpha": {"version": "1.0"}}}


def test_versions_adds_sha256_from_artifacts(repo: Path) -> None:
    """The digest darktable verifies a download against."""
    import hashlib
    import json

    artifacts = repo / "artifacts"
    artifacts.mkdir()
    blob = b"not really a zip, but hashing does not care"
    (artifacts / "alpha.dtmodel").write_bytes(blob)

    result = CliRunner().invoke(main, ["versions", "--artifacts-dir",
                                       str(artifacts)])
    assert result.exit_code == 0, result.output

    entry = json.loads((repo / "output" / "versions.json").read_text())["models"]["alpha"]
    # the "sha256:" prefix is mandatory – darktable ignores a bare digest
    assert entry["sha256"] == f"sha256:{hashlib.sha256(blob).hexdigest()}"


def test_versions_accepts_nested_ci_layout(repo: Path) -> None:
    """actions/download-artifact nests each asset in its own directory."""
    import json

    nested = repo / "artifacts" / "alpha"
    nested.mkdir(parents=True)
    (nested / "alpha.dtmodel").write_bytes(b"x")

    result = CliRunner().invoke(main, ["versions", "--artifacts-dir",
                                       str(repo / "artifacts")])
    assert result.exit_code == 0, result.output
    entry = json.loads((repo / "output" / "versions.json").read_text())["models"]["alpha"]
    assert entry["sha256"].startswith("sha256:")


def test_versions_warns_on_missing_artifact(repo: Path) -> None:
    """A model with no built asset must not silently get no digest."""
    import json

    artifacts = repo / "artifacts"
    artifacts.mkdir()
    result = CliRunner().invoke(main, ["versions", "--artifacts-dir",
                                       str(artifacts)])
    assert result.exit_code == 0, result.output
    assert "artifact missing for alpha" in result.output

    entry = json.loads((repo / "output" / "versions.json").read_text())["models"]["alpha"]
    assert "sha256" not in entry
