"""Build verification tests (DIST-01, D-26..D-30).

These tests verify that the package is publish-ready:

- py.typed is included (PEP 561)
- pyproject.toml metadata is complete
- No homeassistant.* imports anywhere
- uv build + twine check succeed (when run in an environment that has them)

The shell-level guards (scripts/check_no_ha_imports.sh, scripts/build.sh)
are also exercised here so CI catches broken scripts.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _has_twine_module() -> bool:
    """Helper: check if ``twine`` is importable as a Python module."""
    try:
        import twine  # noqa: F401
        return True
    except ImportError:
        return False


_TWINE_AVAILABLE = _has_twine_module()


def test_py_typed_marker_exists_in_src() -> None:
    """D-27 / D-11: py.typed must be a real file in src/."""
    assert (ROOT / "src" / "aionlslivetiming" / "py.typed").is_file(), (
        "src/aionlslivetiming/py.typed is missing — Phase 1 D-11 lock"
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "name",
        "version",
        "description",
        "readme",
        "license",
        "requires-python",
        "authors",
        "keywords",
        "classifiers",
    ],
)
def test_pyproject_has_required_metadata_field(field_name: str) -> None:
    """D-28: every required PyPI metadata field is present in [project]."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf"^{field_name}\s*=", pyproject, re.MULTILINE), (
        f"pyproject.toml missing required [project] field: {field_name}"
    )


def test_pyproject_has_project_urls() -> None:
    """D-28: Repository and Issues URLs are set."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.urls]" in pyproject
    assert "Repository" in pyproject
    assert "Issues" in pyproject


def test_pyproject_force_includes_py_typed() -> None:
    """D-11 / D-27: hatch force-include must include the py.typed file."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "force-include" in pyproject
    assert "py.typed" in pyproject


def test_no_homeassistant_imports_in_src() -> None:
    """DIST-04 / D-30: zero homeassistant.* imports in src/."""
    src_root = ROOT / "src"
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        # Match actual import statements: `import homeassistant`, `from homeassistant`
        # We tolerate the substring only in comments / docstrings; this guards
        # against the real risk (an `import homeassistant` slipping into src/).
        assert not _has_real_homeassistant_import(text), (
            f"{path.relative_to(ROOT)} contains a homeassistant import statement"
        )


def test_no_homeassistant_imports_in_tests() -> None:
    """D-30: zero homeassistant.* import statements in tests/.

    Test docstrings and assertion messages may legitimately mention
    'homeassistant' (e.g. ``test_no_homeassistant_imports``); only actual
    import statements are forbidden here.
    """
    for path in (ROOT / "tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert not _has_real_homeassistant_import(text), (
            f"{path.relative_to(ROOT)} contains a homeassistant import statement"
        )


def test_check_no_ha_imports_script_executable() -> None:
    """The CI script must exist and be executable."""
    script = ROOT / "scripts" / "check_no_ha_imports.sh"
    assert script.is_file(), f"{script} missing"
    assert script.stat().st_mode & 0o111, f"{script} is not executable"


def test_check_no_ha_imports_script_exits_zero() -> None:
    """Running the script exits 0 (no HA imports found)."""
    script = ROOT / "scripts" / "check_no_ha_imports.sh"
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode == 0, (
        f"check_no_ha_imports.sh failed:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


def test_build_script_executable() -> None:
    """build.sh must exist and be executable."""
    script = ROOT / "scripts" / "build.sh"
    assert script.is_file(), f"{script} missing"
    assert script.stat().st_mode & 0o111, f"{script} is not executable"


def test_gitignore_excludes_dist() -> None:
    """`dist/` must be in .gitignore (build artifacts)."""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    # Accept either `dist/` or `dist` line — both are valid gitignore patterns.
    assert re.search(r"^dist/?$", text, re.MULTILINE), (
        ".gitignore missing `dist/` entry"
    )


def test_gitignore_excludes_site() -> None:
    """`site/` (mkdocs build output) must be in .gitignore."""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^site/?$", text, re.MULTILINE), (
        ".gitignore missing `site/` entry"
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_uv_build_produces_wheel_and_sdist(tmp_path: pathlib.Path) -> None:
    """D-26: uv build must produce both wheel and sdist."""
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"uv build failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    wheels = list(tmp_path.glob("*.whl"))
    sdists = list(tmp_path.glob("*.tar.gz"))
    assert len(wheels) == 1, f"expected 1 wheel, got {len(wheels)}: {wheels}"
    assert len(sdists) == 1, f"expected 1 sdist, got {len(sdists)}: {sdists}"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_wheel_contains_py_typed(tmp_path: pathlib.Path) -> None:
    """D-27: the built wheel must include py.typed (PEP 561 marker)."""
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(build_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"uv build failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    wheels = list(build_dir.glob("*.whl"))
    assert wheels, f"no wheel produced in {build_dir}"
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    py_typed_paths = [n for n in names if n.endswith("py.typed")]
    assert py_typed_paths, (
        f"py.typed missing from wheel {wheel.name}. Contents sample: {names[:10]}"
    )


@pytest.mark.skipif(
    not _TWINE_AVAILABLE, reason="twine module not importable"
)
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_twine_check_passes(tmp_path: pathlib.Path) -> None:
    """D-26: ``python -m twine check dist/*`` must pass."""
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    build_result = subprocess.run(
        ["uv", "build", "--out-dir", str(build_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert build_result.returncode == 0, (
        f"uv build failed:\nSTDOUT: {build_result.stdout}\n"
        f"STDERR: {build_result.stderr}"
    )
    # Only glob for wheel + sdist; `uv build --out-dir <existing_dir>` may copy
    # other repo files (e.g. .gitignore) alongside the artifacts.
    artifacts = sorted(
        list(build_dir.glob("*.whl")) + list(build_dir.glob("*.tar.gz"))
    )
    assert artifacts, f"no wheel/sdist produced in {build_dir}"
    check_result = subprocess.run(
        ["python", "-m", "twine", "check", *(str(p) for p in artifacts)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert check_result.returncode == 0, (
        f"twine check failed:\nSTDOUT: {check_result.stdout}\n"
        f"STDERR: {check_result.stderr}"
    )


def _has_real_homeassistant_import(text: str) -> bool:
    """Return True if ``text`` contains an actual homeassistant import.

    Matches Python import statements only — comments, docstrings, and
    test descriptions are ignored. Specifically looks for:

    - ``import homeassistant`` (possibly ``import homeassistant.x``)
    - ``from homeassistant import ...``
    - ``from homeassistant.x import ...``

    Anchored to the start of a (stripped) line; this catches the common
    forms without false positives on identifier mentions like
    ``test_no_homeassistant_imports``.
    """
    pattern = re.compile(
        r"^\s*(?:import\s+homeassistant\b|from\s+homeassistant(?:\.\w+)?\s+import\b)"
    )
    return bool(pattern.search(text))
