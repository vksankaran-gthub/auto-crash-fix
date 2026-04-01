"""Integration test for Phase 1 pipeline with mock portal and local git repo."""

import json
import os
import subprocess

import pytest
import responses

from crash_fix.config import Config
from crash_fix.portal_client import PortalClient
from crash_fix.yocto_tracer import YoctoTracer
from crash_fix.crash_site import CrashSiteLocator


PORTAL_URL = "https://stacktrace.example.com"
TOKEN = "test-token"


@pytest.fixture
def local_repo(tmp_path):
    """Create a temporary git repo with a source file."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_dir,
        capture_output=True,
    )

    # Create source file
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    source_file = src_dir / "main.cpp"
    lines = []
    for i in range(1, 101):
        lines.append(f"// Line {i}\n")
    lines[41] = "void crash_func() { int *p = nullptr; *p = 42; } // CRASH HERE\n"
    source_file.write_text("".join(lines))

    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_dir,
        capture_output=True,
    )

    return str(repo_dir)


class TestCrashSiteLocator:
    """Tests for crash site identification."""

    def test_locate_source_by_exact_path(self, local_repo):
        locator = CrashSiteLocator()
        backtrace = [
            {
                "frame_number": 0,
                "function_name": "crash_func",
                "source_file": "src/main.cpp",
                "line_number": 42,
                "module": "libtest.so",
            }
        ]

        result = locator.locate_crash_source(backtrace, local_repo)
        assert result is not None
        assert len(result) == 1
        assert result[0]["source_file"] == "src/main.cpp"
        assert result[0]["line_number"] == 42
        assert "CRASH HERE" in result[0]["source_context"]["code"]

    def test_locate_source_by_filename_fallback(self, local_repo):
        locator = CrashSiteLocator()
        backtrace = [
            {
                "frame_number": 0,
                "function_name": "crash_func",
                "source_file": "/build/workspace/some/path/main.cpp",
                "line_number": 42,
                "module": "libtest.so",
            }
        ]

        result = locator.locate_crash_source(backtrace, local_repo)
        assert result is not None
        assert len(result) == 1
        assert "main.cpp" in result[0]["source_file"]

    def test_source_not_found(self, local_repo):
        locator = CrashSiteLocator()
        backtrace = [
            {
                "frame_number": 0,
                "function_name": "unknown_func",
                "source_file": "nonexistent.cpp",
                "line_number": 1,
                "module": "libtest.so",
            }
        ]

        result = locator.locate_crash_source(backtrace, local_repo)
        assert result is None

    def test_classify_segfault(self):
        locator = CrashSiteLocator()
        backtrace = [
            {"function_name": "handle_SIGSEGV", "frame_number": 0},
            {"function_name": "crash_func", "frame_number": 1},
        ]
        result = locator.classify_crash_type(backtrace, {})
        assert result == "segfault"

    def test_classify_abort(self):
        locator = CrashSiteLocator()
        backtrace = [
            {"function_name": "__assert_fail", "frame_number": 0},
            {"function_name": "validate", "frame_number": 1},
        ]
        result = locator.classify_crash_type(backtrace, {})
        assert result == "abort"

    def test_classify_unknown(self):
        locator = CrashSiteLocator()
        backtrace = [
            {"function_name": "some_func", "frame_number": 0},
        ]
        result = locator.classify_crash_type(backtrace, {})
        assert result == "unknown"


class TestConfigValidation:
    """Tests for configuration credential validation."""

    def test_portal_creds_valid(self, monkeypatch):
        monkeypatch.setenv("STACKTRACE_PORTAL_URL", "https://portal.test")
        monkeypatch.setenv("STACKTRACE_PORTAL_TOKEN", "tok123")
        config = Config()
        valid, err = config.validate_portal_credentials()
        assert valid is True
        assert err is None

    def test_portal_creds_missing_url(self, monkeypatch):
        monkeypatch.delenv("STACKTRACE_PORTAL_URL", raising=False)
        monkeypatch.setenv("STACKTRACE_PORTAL_TOKEN", "tok123")
        config = Config()
        valid, err = config.validate_portal_credentials()
        assert valid is False
        assert "STACKTRACE_PORTAL_URL" in err

    def test_github_creds_missing(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        config = Config()
        valid, err = config.validate_github_credentials()
        assert valid is False
        assert "GitHub token" in err
