"""M4 packaging/release metadata: version, scripts, license, CI, docs."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 (CI matrix)
    import tomli as tomllib
from pathlib import Path

import memorix


ROOT = Path(__file__).resolve().parents[1]


def test_version_is_release_version():
    assert memorix.__version__ == "0.3.7"


def test_pyproject_scripts_and_license():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "mem-patrol"
    assert data["project"]["version"] == "0.3.7"
    scripts = data["project"]["scripts"]
    assert scripts["memorix"] == "memorix.cli:main"
    assert scripts["memorix-mcp"] == "memorix.mcp.server:main"
    assert scripts["mem-patrol"] == "memorix.cli:main"
    assert scripts["mem-patrol-mcp"] == "memorix.mcp.server:main"
    assert data["project"]["license"] == "MIT"
    assert "LICENSE" in data["project"]["license-files"]
    assert "jieba" in data["project"]["optional-dependencies"]["anchor"][0]
    assert "pytest" in data["project"]["optional-dependencies"]["test"][0]


def test_license_and_changelog_exist():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text and "Permission is hereby granted" in license_text
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "0.2.0" in changelog and "MCP" in changelog


def test_ci_and_release_workflows():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for version in ("3.10", "3.11", "3.12"):
        assert version in ci
    assert "memorix.eval" in ci and "memorix-mcp" in ci
    assert "tags:" in release and "action-gh-release" in release


def test_mcp_module_is_importable():
    from memorix.mcp.server import Server

    assert Server().handle({"jsonrpc": "2.0", "id": 1, "method": "ping"})["result"] == {}
