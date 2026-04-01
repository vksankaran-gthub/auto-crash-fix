"""Unit tests for the AI fix generator."""

import os
import subprocess

import pytest
import responses

from crash_fix.ai_fix_generator import AIFixGenerator


API_URL = "https://api.example.com/chat/completions"
API_TOKEN = "test-token"


@pytest.fixture
def generator():
    return AIFixGenerator(api_token=API_TOKEN, api_url=API_URL)


def _make_crash_context(**overrides):
    """Build a minimal crash context dict, with overrides."""
    ctx = {
        "fingerprint_id": "FP-001",
        "crash_metadata": {
            "component_name": "WPEWebProcess",
            "build_version": "rdkb-2025q4",
        },
        "crash_type": "null_pointer_dereference",
        "recipe_info": {"recipe_name": "wpe-webkit"},
        "source_info": {"repo_url": "https://github.com/example/wpe.git"},
        "repo_path": "/tmp/repos/wpe",
        "backtrace": [
            {
                "frame_number": 0,
                "function_name": "WebCore::RenderBox::paint",
                "source_file": "Source/WebCore/rendering/RenderBox.cpp",
                "line_number": 142,
                "module": "libWPEWebKit.so",
            },
            {
                "frame_number": 1,
                "function_name": "WebCore::RenderLayer::paintLayer",
                "source_file": "Source/WebCore/rendering/RenderLayer.cpp",
                "line_number": 310,
                "module": "libWPEWebKit.so",
            },
        ],
        "crash_site": [
            {
                "source_file": "Source/WebCore/rendering/RenderBox.cpp",
                "line_number": 142,
                "function_name": "WebCore::RenderBox::paint",
                "source_context": {
                    "code": "void RenderBox::paint(PaintInfo& info) {\n"
                            "    auto* style = this->style();\n"
                            "    style->display();  // crashes here\n"
                            "}\n",
                    "start_line": 140,
                },
            }
        ],
    }
    ctx.update(overrides)
    return ctx


# ── Prompt construction ──────────────────────────────────────────


class TestBuildPrompt:
    """Tests for build_prompt — prompt construction."""

    def test_prompt_contains_all_five_sections(self, generator):
        ctx = _make_crash_context()
        prompt = generator.build_prompt(ctx)

        assert "## Context" in prompt
        assert "## Crash Type" in prompt
        assert "## Backtrace" in prompt
        assert "## Source Code at Crash Site" in prompt
        assert "## Task" in prompt

    def test_prompt_populates_context_fields(self, generator):
        ctx = _make_crash_context()
        prompt = generator.build_prompt(ctx)

        assert "WPEWebProcess" in prompt
        assert "rdkb-2025q4" in prompt
        assert "https://github.com/example/wpe.git" in prompt
        assert "wpe-webkit" in prompt

    def test_prompt_contains_crash_type(self, generator):
        ctx = _make_crash_context(crash_type="use_after_free")
        prompt = generator.build_prompt(ctx)
        assert "use_after_free" in prompt

    def test_prompt_includes_backtrace_frames(self, generator):
        ctx = _make_crash_context()
        prompt = generator.build_prompt(ctx)

        assert "WebCore::RenderBox::paint" in prompt
        assert "RenderBox.cpp" in prompt
        assert "#0" in prompt
        assert "#1" in prompt

    def test_prompt_includes_source_code(self, generator):
        ctx = _make_crash_context()
        prompt = generator.build_prompt(ctx)
        assert "style->display();" in prompt

    def test_prompt_flags_missing_backtrace(self, generator):
        ctx = _make_crash_context(backtrace=None)
        prompt = generator.build_prompt(ctx)
        assert "NOT AVAILABLE" in prompt
        assert "backtrace" in prompt.lower()

    def test_prompt_flags_missing_crash_site(self, generator):
        ctx = _make_crash_context(crash_site=None)
        prompt = generator.build_prompt(ctx)
        assert "NOT AVAILABLE" in prompt
        assert "source" in prompt.lower()

    def test_prompt_handles_empty_backtrace(self, generator):
        ctx = _make_crash_context(backtrace=[])
        prompt = generator.build_prompt(ctx)
        # Empty list is falsy → should flag as not available
        assert "NOT AVAILABLE" in prompt

    def test_prompt_fix_instruction_requires_diff(self, generator):
        ctx = _make_crash_context()
        prompt = generator.build_prompt(ctx)
        assert "git apply" in prompt
        assert "diff" in prompt.lower()


# ── Response parsing ──────────────────────────────────────────────


class TestParseResponse:
    """Tests for parse_response — extracting patches from AI output."""

    SAMPLE_RESPONSE_WITH_DIFF = (
        "The crash is caused by a null pointer dereference.\n\n"
        "```diff\n"
        "--- a/Source/WebCore/rendering/RenderBox.cpp\n"
        "+++ b/Source/WebCore/rendering/RenderBox.cpp\n"
        "@@ -140,4 +140,5 @@\n"
        " void RenderBox::paint(PaintInfo& info) {\n"
        "     auto* style = this->style();\n"
        "+    if (!style) return;\n"
        "     style->display();\n"
        " }\n"
        "```\n"
    )

    def test_extracts_patch_from_diff_block(self, generator):
        result = generator.parse_response(self.SAMPLE_RESPONSE_WITH_DIFF)
        assert result["actionable"] is True
        assert result["patch"] is not None
        assert "+    if (!style) return;" in result["patch"]

    def test_extracts_explanation(self, generator):
        result = generator.parse_response(self.SAMPLE_RESPONSE_WITH_DIFF)
        assert "null pointer" in result["explanation"].lower()

    def test_lists_modified_files(self, generator):
        result = generator.parse_response(self.SAMPLE_RESPONSE_WITH_DIFF)
        assert "Source/WebCore/rendering/RenderBox.cpp" in result["files_modified"]

    def test_no_diff_returns_non_actionable(self, generator):
        response = "The crash appears to be a race condition. More data is needed."
        result = generator.parse_response(response)
        assert result["actionable"] is False
        assert result["patch"] is None
        assert result["files_modified"] == []

    def test_empty_response(self, generator):
        result = generator.parse_response("")
        assert result["actionable"] is False
        assert result["patch"] is None

    def test_none_response(self, generator):
        result = generator.parse_response(None)
        assert result["actionable"] is False

    def test_multiple_diff_blocks_combined(self, generator):
        response = (
            "Fix two files:\n\n"
            "```diff\n--- a/file1.c\n+++ b/file1.c\n@@ -1 +1 @@\n-old\n+new\n```\n\n"
            "```diff\n--- a/file2.c\n+++ b/file2.c\n@@ -1 +1 @@\n-old2\n+new2\n```\n"
        )
        result = generator.parse_response(response)
        assert result["actionable"] is True
        assert "file1.c" in result["files_modified"]
        assert "file2.c" in result["files_modified"]

    def test_dev_null_not_included_in_files(self, generator):
        response = (
            "```diff\n--- /dev/null\n+++ b/new_file.c\n@@ -0,0 +1 @@\n+hello\n```\n"
        )
        result = generator.parse_response(response)
        assert "/dev/null" not in result["files_modified"]
        assert "new_file.c" in result["files_modified"]


# ── AI API interaction ────────────────────────────────────────────


class TestSendToAI:
    """Tests for send_to_ai — API interaction."""

    @responses.activate
    def test_successful_api_call(self, generator):
        responses.add(
            responses.POST,
            API_URL,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Here is the fix:\n```diff\n-old\n+new\n```"
                        }
                    }
                ]
            },
            status=200,
        )
        result = generator.send_to_ai("Fix this crash")
        assert result is not None
        assert "fix" in result.lower()

    @responses.activate
    def test_api_returns_non_200(self, generator):
        responses.add(responses.POST, API_URL, status=500)
        result = generator.send_to_ai("Fix this crash")
        assert result is None

    @responses.activate
    def test_api_returns_empty_choices(self, generator):
        responses.add(
            responses.POST, API_URL, json={"choices": []}, status=200
        )
        result = generator.send_to_ai("Fix this crash")
        assert result is None

    @responses.activate
    def test_api_connection_error(self, generator):
        responses.add(
            responses.POST,
            API_URL,
            body=ConnectionError("unreachable"),
        )
        result = generator.send_to_ai("Fix this crash")
        assert result is None

    def test_missing_token_returns_none(self):
        gen = AIFixGenerator(api_token="", api_url=API_URL)
        result = gen.send_to_ai("Fix this crash")
        assert result is None


# ── Confidence assessment ─────────────────────────────────────────


class TestAssessConfidence:
    """Tests for assess_confidence."""

    def test_high_confidence_full_context(self, generator):
        ctx = _make_crash_context()
        parsed = {
            "files_modified": ["RenderBox.cpp"],
        }
        assert generator.assess_confidence(ctx, parsed) == "high"

    def test_low_confidence_missing_backtrace(self, generator):
        ctx = _make_crash_context(backtrace=None)
        parsed = {"files_modified": ["RenderBox.cpp"]}
        assert generator.assess_confidence(ctx, parsed) == "low"

    def test_low_confidence_missing_crash_site(self, generator):
        ctx = _make_crash_context(crash_site=None)
        parsed = {"files_modified": ["RenderBox.cpp"]}
        assert generator.assess_confidence(ctx, parsed) == "low"

    def test_low_confidence_unknown_crash_type(self, generator):
        ctx = _make_crash_context(crash_type="unknown")
        parsed = {"files_modified": ["RenderBox.cpp"]}
        assert generator.assess_confidence(ctx, parsed) == "low"

    def test_low_confidence_many_files_modified(self, generator):
        ctx = _make_crash_context()
        parsed = {"files_modified": ["a.c", "b.c", "c.c"]}
        assert generator.assess_confidence(ctx, parsed) == "low"


# ── Patch application ────────────────────────────────────────────


class TestApplyPatch:
    """Tests for apply_patch — git operations."""

    def test_no_patch_returns_failure(self, generator):
        result = generator.apply_patch("", "/tmp/repo", "FP-001")
        assert result["success"] is False

    def test_no_repo_path_returns_failure(self, generator):
        result = generator.apply_patch("some patch", "", "FP-001")
        assert result["success"] is False

    def test_apply_patch_in_temp_repo(self, generator, tmp_path):
        """End-to-end: create a git repo, apply a real patch, verify commit."""
        repo = tmp_path / "repo"
        repo.mkdir()

        # Initialize git repo with a file
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo, capture_output=True,
        )

        src_file = repo / "main.c"
        src_file.write_text("int main() {\n    return 0;\n}\n")

        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo, capture_output=True,
        )

        # Create a valid patch
        patch = (
            "--- a/main.c\n"
            "+++ b/main.c\n"
            "@@ -1,3 +1,4 @@\n"
            " int main() {\n"
            "+    /* crash fix */\n"
            "     return 0;\n"
            " }\n"
        )

        result = generator.apply_patch(patch, str(repo), "FP-TEST")

        assert result["success"] is True
        assert result["branch_name"] == "crash-fix/FP-TEST"
        assert result["error"] is None

        # Verify the commit exists
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "FP-TEST" in log.stdout

        # Verify file content
        assert "/* crash fix */" in src_file.read_text()

    def test_bad_patch_fails_cleanly(self, generator, tmp_path):
        """A malformed patch should not leave the repo dirty."""
        repo = tmp_path / "repo"
        repo.mkdir()

        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo, capture_output=True,
        )

        (repo / "foo.c").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo, capture_output=True,
        )

        bad_patch = (
            "--- a/nonexistent.c\n"
            "+++ b/nonexistent.c\n"
            "@@ -1 +1 @@\n"
            "-line that does not exist\n"
            "+replacement\n"
        )

        result = generator.apply_patch(bad_patch, str(repo), "FP-BAD")
        assert result["success"] is False
        assert result["error"] is not None
