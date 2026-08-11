"""darktable-ai-sdk: build model repositories that darktable can consume."""

from __future__ import annotations

from dt_ai_sdk.config import (
    Checkpoint,
    ConvertStep,
    DemoConfig,
    ModelConfig,
    ModelConfigError,
    RepoConfig,
    load_model_config,
)
from dt_ai_sdk.convert import run_conversion, generate_config_json
from dt_ai_sdk.discovery import discover_models, find_project_root
from dt_ai_sdk.download import download_checkpoints
from dt_ai_sdk.gitversion import describe_version, version_prefix
from dt_ai_sdk.package import package_model
from dt_ai_sdk.validate import run_validation, validate_config_json, validate_onnx

__version__ = "0.1.0a1"

# CLI subpackage is imported lazily by consumers that want to compose commands;
# not re-exported here to keep the top-level import path lightweight

__all__ = [
    "__version__",
    # config
    "Checkpoint",
    "ConvertStep",
    "DemoConfig",
    "ModelConfig",
    "ModelConfigError",
    "RepoConfig",
    "load_model_config",
    # discovery
    "discover_models",
    "find_project_root",
    # repo version from git tags
    "describe_version",
    "version_prefix",
    # pipeline steps
    "download_checkpoints",
    "run_conversion",
    "generate_config_json",
    "package_model",
    # validation
    "run_validation",
    "validate_config_json",
    "validate_onnx",
]
