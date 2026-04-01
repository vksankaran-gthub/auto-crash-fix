"""GitHub PR creation module.

Creates pull requests with structured descriptions containing
the full audit trail from crash to fix.
"""

import os
import re

import click
import requests


class PRCreator:
    """Creates GitHub PRs for validated crash fixes."""

    LABELS = ["auto-generated", "crash-fix"]

    def __init__(self, github_token=None):
        self.token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.api_base = "https://api.github.com"

    def can_create_pr(self, build_result, test_result, regression_result):
        """Check whether all gates pass for PR creation.

        Returns:
            (bool, str): (allowed, reason_if_not)
        """
        if build_result.get("status") != "success":
            return False, "Build failed — PR not created"

        if test_result.get("tests_defined", True) and test_result.get("failed", 0) > 0:
            return False, "Validation failed — PR not created: tests failed"

        reg_status = regression_result.get("status", "")
        if reg_status == "fail":
            reason = regression_result.get("error", "regression check failed")
            return False, f"Validation failed — PR not created: {reason}"

        return True, ""

    def create_pr(
        self,
        repo_url,
        branch,
        crash_context,
        build_result,
        test_result,
        regression_result,
        confidence,
    ):
        """Create a PR via GitHub API.

        Args:
            repo_url: Source repository URL (e.g. https://github.com/owner/repo).
            branch: Feature branch name.
            crash_context: Original crash context dict.
            build_result: Output from BuildValidator.monitor_build.
            test_result: Output from DeviceTester.run_component_tests.
            regression_result: Output from RegressionChecker.monitor_crashes.
            confidence: "high" or "low".

        Returns:
            dict with 'pr_url' (str or None), 'pr_number' (int or None),
            'error' (str or None).
        """
        if not self.token:
            return {
                "pr_url": None,
                "pr_number": None,
                "error": "GitHub token not configured — cannot create PR",
            }

        owner, repo = self._parse_repo_url(repo_url)
        if not owner or not repo:
            return {
                "pr_url": None,
                "pr_number": None,
                "error": f"Cannot parse repository from URL: {repo_url}",
            }

        fingerprint_id = crash_context.get("fingerprint_id", "unknown")
        crash_type = crash_context.get("crash_type", "unknown")
        component = crash_context.get("crash_metadata", {}).get("component_name", "unknown")

        title = f"fix: crash fix for {component} ({fingerprint_id})"

        body = self._build_description(
            crash_context, build_result, test_result, regression_result, confidence
        )

        labels = self.LABELS + [
            f"fingerprint:{fingerprint_id}",
            f"{confidence}-confidence",
        ]

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

        payload = {
            "title": title,
            "body": body,
            "head": branch,
            "base": "main",
        }

        try:
            resp = requests.post(
                f"{self.api_base}/repos/{owner}/{repo}/pulls",
                headers=headers,
                json=payload,
                timeout=30,
            )
        except (requests.ConnectionError, ConnectionError, requests.Timeout):
            return {
                "pr_url": None,
                "pr_number": None,
                "error": "GitHub API unreachable",
            }

        if resp.status_code not in (200, 201):
            return {
                "pr_url": None,
                "pr_number": None,
                "error": f"PR creation failed: HTTP {resp.status_code}",
            }

        data = resp.json()
        pr_number = data.get("number")
        pr_url = data.get("html_url", "")

        # Apply labels (best-effort)
        self._apply_labels(headers, owner, repo, pr_number, labels)

        return {
            "pr_url": pr_url,
            "pr_number": pr_number,
            "error": None,
        }

    def _build_description(
        self, crash_context, build_result, test_result, regression_result, confidence
    ):
        """Build structured PR description with audit trail."""
        fp = crash_context.get("fingerprint_id", "unknown")
        metadata = crash_context.get("crash_metadata", {})
        component = metadata.get("component_name", "unknown")
        crash_type = crash_context.get("crash_type", "unknown")
        build_version = metadata.get("build_version", "unknown")

        sections = []

        # Header
        sections.append(
            f"## Automated Crash Fix\n\n"
            f"**Fingerprint:** `{fp}`\n"
            f"**Component:** {component}\n"
            f"**Crash Type:** {crash_type}\n"
            f"**Build Version:** {build_version}\n"
            f"**Confidence:** {confidence}\n"
        )

        # Backtrace excerpt (top 10 frames)
        backtrace = crash_context.get("backtrace", [])
        if backtrace:
            bt_lines = []
            for frame in backtrace[:10]:
                fn = frame.get("function_name", "??")
                src = frame.get("source_file", "")
                line = frame.get("line_number", "")
                loc = f" at {src}:{line}" if src else ""
                bt_lines.append(f"#{frame.get('frame_number', '?')} {fn}{loc}")
            sections.append(
                "### Backtrace (top 10 frames)\n```\n"
                + "\n".join(bt_lines)
                + "\n```\n"
            )

        # Build result
        build_url = build_result.get("log_url", "N/A")
        sections.append(
            f"### Build Result\n"
            f"**Status:** {build_result.get('status', 'unknown')}\n"
            f"**Log:** {build_url}\n"
        )

        # Test results
        if test_result.get("tests_defined", False):
            sections.append(
                f"### Test Results\n"
                f"**Total:** {test_result.get('total', 0)} | "
                f"**Passed:** {test_result.get('passed', 0)} | "
                f"**Failed:** {test_result.get('failed', 0)} | "
                f"**Skipped:** {test_result.get('skipped', 0)}\n"
            )
        else:
            sections.append("### Test Results\nNo tests defined for this component.\n")

        # Regression check
        reg_status = regression_result.get("status", "unknown")
        sections.append(
            f"### Crash Regression Check\n**Result:** {reg_status}\n"
        )

        sections.append(
            "---\n*This PR was auto-generated by crash-fix-tool.*\n"
        )

        return "\n".join(sections)

    def _apply_labels(self, headers, owner, repo, pr_number, labels):
        """Apply labels to PR (best effort)."""
        try:
            requests.post(
                f"{self.api_base}/repos/{owner}/{repo}/issues/{pr_number}/labels",
                headers=headers,
                json={"labels": labels},
                timeout=15,
            )
        except (requests.ConnectionError, ConnectionError, requests.Timeout):
            pass

    @staticmethod
    def _parse_repo_url(url):
        """Extract owner/repo from a GitHub URL."""
        # Handle https://github.com/owner/repo.git or similar
        match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
        if match:
            return match.group(1), match.group(2)
        return None, None
