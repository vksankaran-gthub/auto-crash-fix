"""CI/CD build integration module.

Triggers builds, monitors status, supports incremental builds.
"""

import time

import click
import requests


class BuildValidator:
    """Manages CI/CD build triggering and monitoring."""

    # Default timeout: 4 hours
    DEFAULT_TIMEOUT = 4 * 60 * 60
    # Poll interval: 30 seconds
    POLL_INTERVAL = 30

    def __init__(self, ci_url=None, ci_token=None):
        self.ci_url = ci_url or ""
        self.ci_token = ci_token or ""

    def trigger_build(self, recipe, branch, repo_url, incremental=True):
        """Push feature branch and trigger build via CI/CD API.

        Args:
            recipe: Yocto recipe name.
            branch: Feature branch name.
            repo_url: Source repository URL.
            incremental: Try component-only build first.

        Returns:
            dict with 'job_id' (str or None), 'error' (str or None),
            'build_type' ('incremental' or 'full').
        """
        if not self.ci_url:
            return {"job_id": None, "error": "CI/CD URL not configured"}

        headers = self._auth_headers()

        # Try incremental build first
        if incremental:
            result = self._trigger(
                headers, recipe, branch, repo_url, build_type="incremental"
            )
            if result["job_id"]:
                return result
            click.echo(
                "Warning: Incremental build not available, falling back to full image build.",
                err=True,
            )

        return self._trigger(headers, recipe, branch, repo_url, build_type="full")

    def monitor_build(self, job_id, timeout=None):
        """Poll build status until success, failure, or timeout.

        Args:
            job_id: Build job ID from trigger_build.
            timeout: Max wait in seconds (default: 4 hours).

        Returns:
            dict with 'status' ('success'|'failure'|'timeout'),
            'artifact_url' (str or None), 'log_url' (str or None),
            'error' (str or None).
        """
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT

        headers = self._auth_headers()
        url = f"{self.ci_url}/api/v1/builds/{job_id}"
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                resp = requests.get(url, headers=headers, timeout=30)
            except (requests.ConnectionError, ConnectionError):
                click.echo("Warning: CI/CD API unreachable, retrying...", err=True)
                time.sleep(self.POLL_INTERVAL)
                continue
            except requests.Timeout:
                time.sleep(self.POLL_INTERVAL)
                continue

            if resp.status_code != 200:
                time.sleep(self.POLL_INTERVAL)
                continue

            data = resp.json()
            status = data.get("status", "")

            if status == "success":
                return {
                    "status": "success",
                    "artifact_url": data.get("artifact_url"),
                    "log_url": data.get("log_url"),
                    "error": None,
                }
            elif status in ("failure", "error"):
                log_url = data.get("log_url", "")
                return {
                    "status": "failure",
                    "artifact_url": None,
                    "log_url": log_url,
                    "error": f"Build failed. Log: {log_url}",
                }

            time.sleep(self.POLL_INTERVAL)

        return {
            "status": "timeout",
            "artifact_url": None,
            "log_url": None,
            "error": f"Build timed out after {timeout}s",
        }

    def _trigger(self, headers, recipe, branch, repo_url, build_type):
        """Send build trigger request."""
        payload = {
            "recipe": recipe,
            "branch": branch,
            "repo_url": repo_url,
            "build_type": build_type,
        }

        try:
            resp = requests.post(
                f"{self.ci_url}/api/v1/builds",
                headers=headers,
                json=payload,
                timeout=30,
            )
        except (requests.ConnectionError, ConnectionError):
            return {
                "job_id": None,
                "error": "Build system unreachable",
                "build_type": build_type,
            }
        except requests.Timeout:
            return {
                "job_id": None,
                "error": "Build system request timed out",
                "build_type": build_type,
            }

        if resp.status_code == 404 and build_type == "incremental":
            return {"job_id": None, "error": "Incremental build not supported", "build_type": build_type}

        if resp.status_code not in (200, 201):
            return {
                "job_id": None,
                "error": f"Build trigger failed: HTTP {resp.status_code}",
                "build_type": build_type,
            }

        data = resp.json()
        return {
            "job_id": data.get("job_id"),
            "error": None,
            "build_type": build_type,
        }

    def _auth_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.ci_token:
            headers["Authorization"] = f"Bearer {self.ci_token}"
        return headers
