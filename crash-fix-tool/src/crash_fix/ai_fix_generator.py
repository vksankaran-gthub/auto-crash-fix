"""AI-assisted fix generation module.

Constructs prompts from crash context, sends to AI API,
parses responses into patches, and applies them.
"""

import json
import os
import re
import subprocess
import tempfile

import click
import requests


class AIFixGenerator:
    """Generates code fixes using AI from crash context."""

    # Return code indicating no actionable fix produced
    EXIT_NO_FIX = 2

    def __init__(self, api_token=None, api_url=None):
        self.api_token = api_token or os.environ.get("COPILOT_API_TOKEN", "")
        self.api_url = api_url or os.environ.get(
            "COPILOT_API_URL",
            "https://api.githubcopilot.com/chat/completions",
        )

    def build_prompt(self, crash_context):
        """Construct a structured prompt from crash context.

        Args:
            crash_context: dict with keys: component_name, repo_url,
                build_version, crash_type, backtrace, crash_site, source_info.

        Returns:
            str: The constructed prompt text.
        """
        sections = []

        # Section 1: Component & repository context
        component = crash_context.get("crash_metadata", {}).get("component_name", "unknown")
        build_version = crash_context.get("crash_metadata", {}).get("build_version", "unknown")
        repo_url = crash_context.get("source_info", {}).get("repo_url", "unknown")
        recipe = crash_context.get("recipe_info", {}).get("recipe_name", "unknown")

        sections.append(
            f"## Context\n"
            f"Component: {component}\n"
            f"Repository: {repo_url}\n"
            f"Recipe: {recipe}\n"
            f"Build version: {build_version}\n"
        )

        # Section 2: Crash type
        crash_type = crash_context.get("crash_type", "unknown")
        sections.append(f"## Crash Type\n{crash_type}\n")

        # Section 3: Backtrace
        backtrace = crash_context.get("backtrace")
        if backtrace:
            bt_text = self._format_backtrace(backtrace)
            sections.append(f"## Backtrace\n{bt_text}\n")
        else:
            sections.append(
                "## Backtrace\n[NOT AVAILABLE — backtrace could not be retrieved]\n"
            )

        # Section 4: Source code at crash site
        crash_site = crash_context.get("crash_site")
        if crash_site:
            src_text = self._format_crash_site(crash_site)
            sections.append(f"## Source Code at Crash Site\n{src_text}\n")
        else:
            sections.append(
                "## Source Code at Crash Site\n"
                "[NOT AVAILABLE — source file could not be located in repository]\n"
            )

        # Section 5: Fix instruction
        sections.append(
            "## Task\n"
            "Analyze the crash above and provide a minimal code fix.\n"
            "1. Explain the root cause of the crash in 2-3 sentences.\n"
            "2. Provide the fix as a unified diff that can be applied with `git apply`.\n"
            "3. Only modify the minimum code necessary to fix the crash.\n"
            "4. Format the diff inside a ```diff code block.\n"
        )

        return "\n".join(sections)

    def send_to_ai(self, prompt):
        """Send prompt to the AI API and return the response text.

        Args:
            prompt: The constructed prompt string.

        Returns:
            str: AI response text, or None on error.
        """
        if not self.api_token:
            click.echo("Error: AI API token not configured (set COPILOT_API_TOKEN)", err=True)
            return None

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert C/C++ developer specializing in crash analysis "
                        "and bug fixing for embedded Linux systems. Provide minimal, "
                        "focused fixes with clear root cause explanations."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120,
            )
        except (requests.ConnectionError, ConnectionError):
            click.echo("Error: AI API unreachable", err=True)
            return None
        except requests.Timeout:
            click.echo("Error: AI API request timed out", err=True)
            return None

        if resp.status_code != 200:
            click.echo(f"Error: AI API returned HTTP {resp.status_code}", err=True)
            return None

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            click.echo("Error: AI API returned empty response", err=True)
            return None

        return choices[0].get("message", {}).get("content", "")

    def parse_response(self, ai_response):
        """Parse AI response to extract patch and explanation.

        Args:
            ai_response: Raw text from AI API.

        Returns:
            dict with 'patch' (str or None), 'explanation' (str),
            'files_modified' (list), 'actionable' (bool).
        """
        if not ai_response:
            return {
                "patch": None,
                "explanation": "",
                "files_modified": [],
                "actionable": False,
            }

        # Extract diff blocks
        diff_pattern = r"```diff\s*\n(.*?)```"
        diff_matches = re.findall(diff_pattern, ai_response, re.DOTALL)

        if not diff_matches:
            # Try generic code blocks that look like diffs
            code_pattern = r"```\s*\n((?:[-+@].*\n?)+)```"
            diff_matches = re.findall(code_pattern, ai_response, re.DOTALL)

        patch = "\n".join(diff_matches) if diff_matches else None

        # Extract explanation (text before the first code block)
        explanation = ai_response
        code_start = ai_response.find("```")
        if code_start > 0:
            explanation = ai_response[:code_start].strip()

        # Count modified files from diff headers
        files_modified = []
        if patch:
            for line in patch.split("\n"):
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    fname = line[6:].strip()
                    if fname and fname != "/dev/null" and fname not in files_modified:
                        files_modified.append(fname)

        return {
            "patch": patch,
            "explanation": explanation,
            "files_modified": files_modified,
            "actionable": patch is not None,
        }

    def apply_patch(self, patch_text, repo_path, fingerprint_id, crash_summary=""):
        """Apply a patch to the repo and commit.

        Args:
            patch_text: Unified diff text.
            repo_path: Path to the git repo.
            fingerprint_id: Crash fingerprint ID for commit message.
            crash_summary: Brief crash description for commit message.

        Returns:
            dict with 'success' (bool), 'error' (str or None),
            'branch_name' (str).
        """
        if not patch_text or not repo_path:
            return {"success": False, "error": "No patch or repo path provided"}

        # Create feature branch
        branch_name = f"crash-fix/{fingerprint_id}"
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "git checkout timed out"}

        # Write patch to temp file and apply
        patch_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False
            ) as f:
                f.write(patch_text)
                patch_file = f.name

            result = subprocess.run(
                ["git", "apply", "--check", patch_file],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Patch failed to apply: {result.stderr.strip()}",
                }

            # Apply for real
            subprocess.run(
                ["git", "apply", patch_file],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
        finally:
            if patch_file and os.path.exists(patch_file):
                os.unlink(patch_file)

        # Stage and commit
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            timeout=15,
        )

        commit_msg = (
            f"fix: crash fix for fingerprint {fingerprint_id}\n\n"
            f"Auto-generated fix for crash: {crash_summary}\n"
            f"Fingerprint: {fingerprint_id}\n"
        )

        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": f"git commit failed: {result.stderr.strip()}",
            }

        return {
            "success": True,
            "error": None,
            "branch_name": branch_name,
        }

    def assess_confidence(self, crash_context, parsed_response):
        """Assess confidence level of the generated fix.

        Args:
            crash_context: Original crash context dict.
            parsed_response: Output from parse_response().

        Returns:
            str: "high" or "low".
        """
        # Start optimistic
        is_high = True

        # Check context completeness
        if not crash_context.get("backtrace"):
            is_high = False
        if not crash_context.get("crash_site"):
            is_high = False
        if crash_context.get("crash_type") == "unknown":
            is_high = False

        # Check fix scope
        if len(parsed_response.get("files_modified", [])) > 2:
            is_high = False

        return "high" if is_high else "low"

    @staticmethod
    def _format_backtrace(backtrace):
        """Format backtrace frames as readable text."""
        lines = []
        for frame in backtrace:
            fn = frame.get("function_name", "??")
            src = frame.get("source_file", "")
            line_no = frame.get("line_number", "")
            module = frame.get("module", "")
            frame_num = frame.get("frame_number", "?")

            location = ""
            if src:
                location = f" at {src}"
                if line_no:
                    location += f":{line_no}"
            if module:
                location += f" [{module}]"

            lines.append(f"#{frame_num} {fn}{location}")

        return "\n".join(lines)

    @staticmethod
    def _format_crash_site(crash_sites):
        """Format crash site source code for prompt."""
        parts = []
        for site in crash_sites:
            header = f"File: {site.get('source_file', '?')}"
            if site.get("line_number"):
                header += f" (crash at line {site['line_number']})"
            header += f"\nFunction: {site.get('function_name', '?')}"

            code = site.get("source_context", {}).get("code", "")
            start = site.get("source_context", {}).get("start_line", 1)

            parts.append(f"{header}\n```\n{code}```")

        return "\n\n".join(parts)
