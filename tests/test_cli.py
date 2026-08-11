"""Tests for the composable CLI commands.

We use click's built-in CliRunner to exercise commands end-to-end without
subprocesses. Commands that would invoke external tools (git, curl, uv) are
tested with fixtures that never trigger those code paths – the SDK's job is
to plumb, not to run real network / vcs ops.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from dt_ai_sdk.cli import (
    convert_cmd,
    init_cmd,
    iter_selected_models,
    list_cmd,
    load_or_fail,
    package_cmd,
    setup_cmd,
    validate_cmd,
)


MINIMAL_YAML = """\
id: {mid}
name: {mid}
description: fixture
task: general
"""


def _make_repo(tmp_path: Path, ids: list[str]) -> Path:
    """Create a fake repo with N models. No checkpoints, no convert steps."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='dummy'\n")
    for mid in ids:
        d = tmp_path / "models" / mid
        d.mkdir(parents=True)
        (d / "model.yaml").write_text(MINIMAL_YAML.format(mid=mid))
    return tmp_path


def _build_group(root: Path, sync_hook=None) -> click.Group:
    """Build a Click group mounted with SDK commands and a root."""
    @click.group()
    @click.pass_context
    def app(ctx):
        ctx.ensure_object(dict)
        ctx.obj["root"] = root
        if sync_hook is not None:
            ctx.obj["sync_deps_hook"] = sync_hook

    for cmd in (setup_cmd, convert_cmd, validate_cmd,
                package_cmd, list_cmd, init_cmd):
        app.add_command(cmd)
    return app


# ---- list ----

def test_list_shows_models(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha", "beta"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_list_json(tmp_path: Path) -> None:
    import json
    root = _make_repo(tmp_path, ["alpha", "beta"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["list", "--json-output"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert {d["id"] for d in data} == {"alpha", "beta"}


def test_list_marks_skipped(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha", "beta"])
    (root / "models" / "beta" / ".skip").touch()
    app = _build_group(root)
    result = CliRunner().invoke(app, ["list"])
    assert "beta" in result.output
    assert "(skipped)" in result.output


# ---- convert / validate / package: for models with no convert steps ----

def test_convert_no_op_runs_cleanly(tmp_path: Path) -> None:
    """A model with no convert steps should still emit config.json."""
    root = _make_repo(tmp_path, ["alpha"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["convert", "alpha"])
    assert result.exit_code == 0, result.output
    assert (root / "output" / "alpha" / "config.json").is_file()


def test_convert_all_models_iterates(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha", "beta"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["convert"])
    assert result.exit_code == 0, result.output
    assert (root / "output" / "alpha" / "config.json").is_file()
    assert (root / "output" / "beta" / "config.json").is_file()


def test_convert_skips_marked(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha", "beta"])
    (root / "models" / "beta" / ".skip").touch()
    app = _build_group(root)
    result = CliRunner().invoke(app, ["convert"])
    assert result.exit_code == 0, result.output
    assert (root / "output" / "alpha" / "config.json").is_file()
    assert not (root / "output" / "beta").exists()


def test_convert_unknown_model_id_errors(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["convert", "does-not-exist"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_package_after_convert(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha"])
    app = _build_group(root)
    assert CliRunner().invoke(app, ["convert", "alpha"]).exit_code == 0
    result = CliRunner().invoke(app, ["package", "alpha"])
    assert result.exit_code == 0, result.output
    assert (root / "output" / "alpha.dtmodel").is_file()


# ---- setup ----

def test_setup_no_op_for_model_without_repo_or_checkpoints(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha"])
    app = _build_group(root)
    result = CliRunner().invoke(app, ["setup", "alpha"])
    assert result.exit_code == 0, result.output


# ---- sync hook ----

def test_sync_hook_fires_on_convert(tmp_path: Path) -> None:
    calls: list[str] = []

    def hook(cfg):
        calls.append(cfg.id)

    root = _make_repo(tmp_path, ["alpha", "beta"])
    app = _build_group(root, sync_hook=hook)
    CliRunner().invoke(app, ["convert"])
    assert calls == ["alpha", "beta"]


def test_sync_hook_absent_is_fine(tmp_path: Path) -> None:
    """No hook registered → convert works, no error."""
    root = _make_repo(tmp_path, ["alpha"])
    app = _build_group(root)  # no sync_hook
    result = CliRunner().invoke(app, ["convert", "alpha"])
    assert result.exit_code == 0, result.output


# ---- helpers ----

def test_load_or_fail_returns_config(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha"])
    cfg = load_or_fail(root, "alpha")
    assert cfg.id == "alpha"


def test_load_or_fail_exits_on_missing(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, ["alpha"])
    with pytest.raises(SystemExit):
        load_or_fail(root, "missing")


# ---- init ----

def _run_init(target: Path, *extra) -> None:
    app = _build_group(target.parent)
    result = CliRunner().invoke(app, ["init", str(target), *extra])
    assert result.exit_code == 0, result.output


def test_init_scaffolds_repo(tmp_path: Path) -> None:
    target = tmp_path / "my-models"
    _run_init(target, "--name", "my-models")

    assert (target / "pyproject.toml").is_file()
    assert (target / "README.md").is_file()
    assert (target / ".gitignore").is_file()
    assert (target / "my_models" / "__init__.py").is_file()
    assert (target / "my_models" / "cli.py").is_file()
    assert (target / "models" / "example" / "model.yaml").is_file()
    assert (target / "samples" / "README.md").is_file()
    assert (target / "vendor" / "README.md").is_file()


def test_init_substitutes_tokens(tmp_path: Path) -> None:
    target = tmp_path / "cool-repo"
    _run_init(target, "--name", "cool-repo")

    pyproject = (target / "pyproject.toml").read_text()
    assert 'name = "cool-repo"' in pyproject
    assert 'packages = ["cool_repo"]' in pyproject
    assert "{{" not in pyproject  # no unresolved tokens

    # The module token reaches the commented-out extension hook too.
    assert 'extend = "cool_repo.cli"' in pyproject

    readme = (target / "README.md").read_text()
    assert "# cool-repo" in readme


def test_init_scaffolds_github_workflows(tmp_path: Path) -> None:
    """`github/` in the template tree must land as `.github/` on disk.

    Dot-prefixed directories are unreliable to ship inside a wheel, hence
    the rename – if it regresses, repos scaffold with no CI at all.
    """
    target = tmp_path / "with-ci"
    _run_init(target, "--name", "with-ci")

    assert (target / ".github" / "workflows" / "check-pr.yml").is_file()
    assert (target / ".github" / "workflows" / "release.yml").is_file()
    assert (target / ".github" / "workflows" / "nightly.yml").is_file()
    assert not (target / "github").exists()
    assert (target / "releases-index.json").is_file()


def test_init_declares_no_dtai_script(tmp_path: Path) -> None:
    """`dtai` is owned by the SDK alone – a repo script would collide."""
    target = tmp_path / "repo"
    _run_init(target, "--name", "repo")

    pyproject = (target / "pyproject.toml").read_text()
    assert "[project.scripts]" not in pyproject
    for line in pyproject.splitlines():
        assert not line.strip().startswith("dtai ="), line


def test_init_defaults_name_from_dir(tmp_path: Path) -> None:
    target = tmp_path / "auto-named"
    _run_init(target)
    assert 'name = "auto-named"' in (target / "pyproject.toml").read_text()


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    (target / "pyproject.toml").write_text("existing")

    app = _build_group(tmp_path)
    result = CliRunner().invoke(app, ["init", str(target)])
    assert result.exit_code != 0
    assert "refusing to overwrite" in result.output
    assert (target / "pyproject.toml").read_text() == "existing"


def test_init_force_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    (target / "pyproject.toml").write_text("existing")

    app = _build_group(tmp_path)
    result = CliRunner().invoke(app, ["init", str(target), "--force"])
    assert result.exit_code == 0, result.output
    assert "existing" not in (target / "pyproject.toml").read_text()


def test_init_scaffolded_repo_is_discoverable(tmp_path: Path) -> None:
    """After init, `dtai list` on the new repo finds the example model."""
    target = tmp_path / "fresh"
    _run_init(target, "--name", "fresh")

    app = _build_group(target)
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "example" in result.output
