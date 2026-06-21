"""Tests for documentation completeness (DOC-01..04).

These tests don't validate prose quality; they validate that the
required sections exist and the public API surface is documented.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_readme_exists():
    assert (ROOT / "README.md").exists()


def test_readme_has_installation_section():
    readme = (ROOT / "README.md").read_text()
    assert "## Installation" in readme
    assert "uv add aionlslivetiming" in readme or "pip install aionlslivetiming" in readme


def test_readme_has_quickstart_section():
    readme = (ROOT / "README.md").read_text()
    assert "##" in readme  # at least one section header
    assert "NLSClient" in readme  # at least mentions the public API
    assert "## Quickstart" in readme or "## 60-Second Quickstart" in readme


def test_readme_references_docs():
    readme = (ROOT / "README.md").read_text()
    assert "docs/" in readme or "docs." in readme


def test_license_exists_and_has_mit_text():
    license_text = (ROOT / "LICENSE").read_text()
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 akentner" in license_text or "Copyright 2026" in license_text


def test_changelog_exists_with_v010():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert "## [0.1.0]" in changelog or "## 0.1.0" in changelog
    assert "2026-06-21" in changelog
    assert "### Added" in changelog
    assert "### Removed" in changelog


def test_contributing_exists_with_dev_setup():
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    assert "## Development setup" in contributing or "## Development Setup" in contributing
    assert "uv sync" in contributing
    assert "pytest" in contributing
    assert "ruff" in contributing or "mypy" in contributing


def test_contributing_documents_dataclass_rule():
    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    # The dataclass-for-events / pydantic-for-state rule per D-18
    assert "dataclass" in contributing.lower()
    assert "pydantic" in contributing.lower()


def test_pyproject_includes_mkdocs_deps():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert "mkdocs" in pyproject
    assert "mkdocs-material" in pyproject or "mkdocstrings" in pyproject


def test_mkdocs_yml_exists():
    assert (ROOT / "mkdocs.yml").exists()


def test_mkdocs_yml_uses_material_theme():
    config = (ROOT / "mkdocs.yml").read_text()
    assert "name: material" in config


def test_mkdocs_yml_configures_mkdocstrings():
    config = (ROOT / "mkdocs.yml").read_text()
    assert "mkdocstrings" in config
    assert "paths: [src]" in config


def test_docs_index_exists():
    assert (ROOT / "docs" / "index.md").exists()


def test_docs_quickstart_covers_all_use_cases():
    quickstart = (ROOT / "docs" / "quickstart.md").read_text()
    assert "## Live" in quickstart
    assert "## Replay" in quickstart
    assert "## Recording" in quickstart
    assert "## Filtering" in quickstart or "## Filter" in quickstart


def test_docs_examples_match_examples_dir():
    """docs/examples/*.py must be byte-identical to examples/*.py."""
    for name in ("live_quickstart.py", "replay_offline.py", "filter_walkthrough.py"):
        src = (ROOT / "examples" / name).read_bytes()
        dst = (ROOT / "docs" / "examples" / name).read_bytes()
        assert src == dst, f"{name} is out of sync with examples/{name}"


def test_mkdocs_build_succeeds_strict():
    """`mkdocs build --strict` must succeed with no warnings.

    Skipped if mkdocs is not installed (the docs extra is not always present).
    """
    import shutil
    import subprocess

    if shutil.which("mkdocs") is None:
        pytest.skip("mkdocs not installed")
    result = subprocess.run(
        ["mkdocs", "build", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"mkdocs build --strict failed:\n{result.stdout}\n{result.stderr}"
    )
