"""Tests for the shipped example repo and the `init` templates.

These guard the documented contract: the template `model.yaml` must parse
under the real schema, and `examples/minimal-repo` must actually build a
`.dtmodel`. The end-to-end test needs onnx and is skipped without it –
that dependency belongs to a model repo, not to the SDK.
"""

from __future__ import annotations

import json
import py_compile
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from dt_ai_sdk.__main__ import main
from dt_ai_sdk.config import load_model_config
from dt_ai_sdk.convert import run_conversion
from dt_ai_sdk.discovery import discover_models
from dt_ai_sdk.package import package_model

REPO_ROOT = Path(__file__).resolve().parent.parent
MINIMAL_REPO = REPO_ROOT / "examples" / "minimal-repo"
TEMPLATE_MODELS = REPO_ROOT / "dt_ai_sdk" / "templates" / "models"


# ---- templates ----

def test_template_model_yaml_parses() -> None:
    """The scaffolded example must load under the real schema.

    Guards against the template documenting fields the loader doesn't
    support, or omitting ones it requires.
    """
    model_dir = TEMPLATE_MODELS / "example"
    cfg = load_model_config(model_dir, model_dir.parent.parent)
    assert cfg.id == "example"
    assert cfg.task


def test_template_gitignore_covers_build_artifacts() -> None:
    """A fresh repo must not invite committing weights or packages."""
    text = (REPO_ROOT / "dt_ai_sdk" / "templates" / "gitignore").read_text()
    for pattern in ("output/", "temp/", "*.dtmodel", ".venv/"):
        assert pattern in text, f"template gitignore missing {pattern}"


def test_template_cli_compiles(tmp_path: Path) -> None:
    """The scaffolded extension module must at least be valid Python."""
    src = REPO_ROOT / "dt_ai_sdk" / "templates" / "_pkg" / "cli.py"
    py_compile.compile(str(src), cfile=str(tmp_path / "cli.pyc"), doraise=True)


def test_template_ships_ci_workflows() -> None:
    """A scaffolded repo must arrive with working CI, not an empty .github."""
    wf = REPO_ROOT / "dt_ai_sdk" / "templates" / "github" / "workflows"
    assert (wf / "check-pr.yml").is_file()
    assert (wf / "release.yml").is_file()
    assert (wf / "nightly.yml").is_file()


def test_template_workflows_are_valid_yaml() -> None:
    import yaml

    wf = REPO_ROOT / "dt_ai_sdk" / "templates" / "github" / "workflows"
    check = yaml.safe_load((wf / "check-pr.yml").read_text())
    release = yaml.safe_load((wf / "release.yml").read_text())
    nightly = yaml.safe_load((wf / "nightly.yml").read_text())

    assert set(check["jobs"]) == {"discover", "check"}
    assert set(release["jobs"]) == {"discover", "build", "publish"}
    assert set(nightly["jobs"]) == {"discover", "build", "publish"}

    # A partial nightly would hand testers a release missing models.
    assert "needs.build.result == 'success'" in (wf / "nightly.yml").read_text()

    # The matrix is fed by the SDK's own JSON output; if that contract
    # changes, these workflows silently build nothing.
    text = (wf / "check-pr.yml").read_text()
    assert "dtai list --json-output" in text
    assert "matrix.dep_group" in text and "matrix.id" in text

    # The release must produce the digests darktable verifies against.
    assert "dtai versions --artifacts-dir" in (wf / "release.yml").read_text()


def test_template_releases_index_is_valid() -> None:
    """Shipped empty: offering nothing is correct until a release exists."""
    data = json.loads(
        (REPO_ROOT / "dt_ai_sdk" / "templates" / "releases-index.json").read_text())
    assert data["schema"] == 1
    assert data["compatible_releases"] == {}


def test_template_cli_declares_no_console_script() -> None:
    """Repos extend the SDK's `dtai`; a second one of the same name collides."""
    text = (REPO_ROOT / "dt_ai_sdk" / "templates" / "_pkg" / "cli.py").read_text()
    assert "from dt_ai_sdk.__main__ import main" in text
    assert "@main.command(" in text


# ---- example repo ----

def test_minimal_repo_is_discoverable() -> None:
    configs = discover_models(MINIMAL_REPO)
    assert [c.id for c in configs] == ["identity"]

    cfg = configs[0]
    assert cfg.convert, "identity should declare a convert step"
    assert (cfg.model_dir / cfg.convert[0].script).is_file()


def test_minimal_repo_model_yaml_matches_dir_name() -> None:
    """id must equal the directory name – darktable rejects a mismatch."""
    for model_dir in (MINIMAL_REPO / "models").iterdir():
        if not (model_dir / "model.yaml").is_file():
            continue
        cfg = load_model_config(model_dir, MINIMAL_REPO)
        assert cfg.id == model_dir.name


def test_minimal_repo_builds_a_dtmodel(tmp_path: Path) -> None:
    """Full convert → package on a copy, so the checked-in tree stays clean."""
    pytest.importorskip("onnx", reason="onnx is a model-repo dependency")

    root = tmp_path / "minimal-repo"
    shutil.copytree(MINIMAL_REPO, root,
                    ignore=shutil.ignore_patterns(".venv", "output", "temp",
                                                  "__pycache__"))

    cfg = load_model_config(root / "models" / "identity", root)
    run_conversion(cfg)
    package = package_model(cfg)

    assert package == root / "output" / "identity.dtmodel"

    with zipfile.ZipFile(package) as zf:
        names = sorted(zf.namelist())
        assert names == ["identity/config.json", "identity/model.onnx"]

        # single top-level dir, named for the model id
        assert {n.split("/")[0] for n in names} == {"identity"}

        config = json.loads(zf.read("identity/config.json"))

    # the keys `dtai validate` requires
    for key in ("id", "name", "description", "task", "backend", "version"):
        assert key in config, f"config.json missing {key}"
    assert config["backend"] == "onnx"
    assert config["attributes"]["input_sizes"] == [64]
    assert config["model_card"]["license"]


def test_minimal_repo_info_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """`dtai info` reaches the CLI via the example's [tool.dtai] extend key.

    Exercises the real path: the group reads pyproject, imports the named
    module, and the command it registered becomes available.
    """
    # The example isn't installed into the SDK's test env, so make it
    # importable the way an installed repo would be.
    monkeypatch.syspath_prepend(str(MINIMAL_REPO))
    monkeypatch.chdir(MINIMAL_REPO)
    monkeypatch.setattr(main, "_extension_loaded", False)

    try:
        result = CliRunner().invoke(main, ["info"])
        assert result.exit_code == 0, result.output
        assert "minimal-repo" in result.output   # name from pyproject
        assert "identity" in result.output       # the model
        assert "denoise" in result.output        # its task
    finally:
        main.commands.pop("info", None)
        for mod in ("minimal_repo.cli", "minimal_repo"):
            sys.modules.pop(mod, None)


def test_minimal_repo_onnx_uses_expected_dim_names(tmp_path: Path) -> None:
    """darktable assumes symbolic dims named height/width by default."""
    onnx = pytest.importorskip("onnx", reason="onnx is a model-repo dependency")

    root = tmp_path / "minimal-repo"
    shutil.copytree(MINIMAL_REPO, root,
                    ignore=shutil.ignore_patterns(".venv", "output", "temp",
                                                  "__pycache__"))

    cfg = load_model_config(root / "models" / "identity", root)
    run_conversion(cfg)

    model = onnx.load(str(cfg.output_dir / "model.onnx"))
    dims = model.graph.input[0].type.tensor_type.shape.dim
    assert [d.dim_param for d in dims][2:] == ["height", "width"]


def test_template_defines_the_default_dep_group() -> None:
    """CI runs `uv sync --group <dep_group>`; the default must resolve.

    `dep_group` defaults to "core", so a scaffolded repo whose
    [dependency-groups] lacks it fails its very first CI run with
    "Group `core` is not defined".
    """
    import tomllib

    src = REPO_ROOT / "dt_ai_sdk" / "templates" / "pyproject.toml"
    # the template carries {{tokens}}, which are not valid TOML values
    # anywhere they appear here, but the group table itself is literal
    data = tomllib.loads(src.read_text().replace("{{sdk_version}}", "0")
                         .replace("{{project_name}}", "x")
                         .replace("{{module}}", "x"))
    assert "core" in data["dependency-groups"]


def test_sdk_version_is_single_sourced() -> None:
    """One definition only – a second copy drifts silently.

    __version__ is what `dtai --version` reports AND what {{sdk_version}}
    pins into every scaffolded repo's dependency on the SDK, so a stale
    duplicate in pyproject.toml would ship wrong pins.
    """
    import tomllib

    from dt_ai_sdk import __version__

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert "version" not in data["project"], \
        "pyproject.toml redefines the version; it must stay dynamic"
    assert "version" in data["project"].get("dynamic", [])
    assert data["tool"]["hatch"]["version"]["path"] == "dt_ai_sdk/__init__.py"
    assert __version__
