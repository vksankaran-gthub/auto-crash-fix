"""Unit tests for PR creator."""

import pytest
import responses

from crash_fix.pr_creator import PRCreator


GITHUB_TOKEN = "ghp-test-token-123"


@pytest.fixture
def creator():
    return PRCreator(github_token=GITHUB_TOKEN)


def _crash_context():
    return {
        "fingerprint_id": "FP-001",
        "crash_type": "null_pointer_dereference",
        "crash_metadata": {
            "component_name": "WPEWebProcess",
            "build_version": "rdkb-2025q4",
        },
        "backtrace": [
            {"frame_number": 0, "function_name": "crash_fn", "source_file": "main.c", "line_number": 10},
        ],
    }


def _build_success():
    return {"status": "success", "artifact_url": "https://ci/artifact", "log_url": "https://ci/log"}


def _build_failure():
    return {"status": "failure", "artifact_url": None, "log_url": "https://ci/log", "error": "Build failed"}


def _test_pass():
    return {"tests_defined": True, "total": 5, "passed": 5, "failed": 0, "skipped": 0, "results": []}


def _test_fail():
    return {"tests_defined": True, "total": 5, "passed": 3, "failed": 2, "skipped": 0, "results": []}


def _regression_pass():
    return {"status": "pass", "crashes_found": [], "original_reoccurred": False, "new_fingerprints": []}


def _regression_fail():
    return {"status": "fail", "crashes_found": [], "original_reoccurred": True,
            "new_fingerprints": [], "error": "original crash re-occurred"}


class TestCanCreatePR:
    """Tests for gate logic."""

    def test_all_pass(self, creator):
        ok, reason = creator.can_create_pr(_build_success(), _test_pass(), _regression_pass())
        assert ok is True

    def test_build_failure_blocks(self, creator):
        ok, reason = creator.can_create_pr(_build_failure(), _test_pass(), _regression_pass())
        assert ok is False
        assert "Build failed" in reason

    def test_test_failure_blocks(self, creator):
        ok, reason = creator.can_create_pr(_build_success(), _test_fail(), _regression_pass())
        assert ok is False
        assert "tests failed" in reason

    def test_regression_failure_blocks(self, creator):
        ok, reason = creator.can_create_pr(_build_success(), _test_pass(), _regression_fail())
        assert ok is False
        assert "PR not created" in reason

    def test_no_tests_defined_allowed(self, creator):
        no_tests = {"tests_defined": False, "total": 0, "passed": 0, "failed": 0, "skipped": 0}
        ok, _ = creator.can_create_pr(_build_success(), no_tests, _regression_pass())
        assert ok is True


class TestCreatePR:
    """Tests for PR creation API calls."""

    @responses.activate
    def test_successful_pr_creation(self, creator):
        responses.add(
            responses.POST,
            "https://api.github.com/repos/example/wpe/pulls",
            json={"number": 42, "html_url": "https://github.com/example/wpe/pull/42"},
            status=201,
        )
        responses.add(
            responses.POST,
            "https://api.github.com/repos/example/wpe/issues/42/labels",
            json={},
            status=200,
        )

        result = creator.create_pr(
            "https://github.com/example/wpe.git",
            "crash-fix/FP-001",
            _crash_context(),
            _build_success(),
            _test_pass(),
            _regression_pass(),
            "high",
        )
        assert result["pr_url"] == "https://github.com/example/wpe/pull/42"
        assert result["pr_number"] == 42
        assert result["error"] is None

    @responses.activate
    def test_github_api_failure(self, creator):
        responses.add(
            responses.POST,
            "https://api.github.com/repos/example/wpe/pulls",
            status=422,
        )
        result = creator.create_pr(
            "https://github.com/example/wpe.git", "branch", _crash_context(),
            _build_success(), _test_pass(), _regression_pass(), "low",
        )
        assert result["error"] is not None
        assert result["pr_url"] is None

    def test_missing_github_token(self):
        c = PRCreator(github_token="")
        result = c.create_pr(
            "https://github.com/example/wpe.git", "branch", _crash_context(),
            _build_success(), _test_pass(), _regression_pass(), "high",
        )
        assert "token" in result["error"].lower()

    def test_bad_repo_url(self, creator):
        result = creator.create_pr(
            "not-a-github-url", "branch", _crash_context(),
            _build_success(), _test_pass(), _regression_pass(), "high",
        )
        assert result["error"] is not None


class TestParseRepoURL:
    """Tests for _parse_repo_url."""

    def test_https_with_git_suffix(self):
        owner, repo = PRCreator._parse_repo_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_https_without_suffix(self):
        owner, repo = PRCreator._parse_repo_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_ssh_url(self):
        owner, repo = PRCreator._parse_repo_url("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_invalid_url(self):
        owner, repo = PRCreator._parse_repo_url("not-a-url")
        assert owner is None
        assert repo is None


class TestBuildDescription:
    """Tests for PR description generation."""

    def test_description_contains_fingerprint(self, creator):
        desc = creator._build_description(
            _crash_context(), _build_success(), _test_pass(), _regression_pass(), "high"
        )
        assert "FP-001" in desc

    def test_description_contains_backtrace(self, creator):
        desc = creator._build_description(
            _crash_context(), _build_success(), _test_pass(), _regression_pass(), "high"
        )
        assert "crash_fn" in desc

    def test_description_contains_test_results(self, creator):
        desc = creator._build_description(
            _crash_context(), _build_success(), _test_pass(), _regression_pass(), "high"
        )
        assert "Passed" in desc

    def test_description_no_tests_defined(self, creator):
        no_tests = {"tests_defined": False}
        desc = creator._build_description(
            _crash_context(), _build_success(), no_tests, _regression_pass(), "low"
        )
        assert "No tests defined" in desc
