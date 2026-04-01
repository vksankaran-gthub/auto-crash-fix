"""Configuration module for crash-fix-tool.

Reads credentials and settings from environment variables.
"""

import os
import sys


class Config:
    """Configuration loaded from environment variables."""

    def __init__(self):
        self.portal_url = os.environ.get("STACKTRACE_PORTAL_URL", "")
        self.portal_token = os.environ.get("STACKTRACE_PORTAL_TOKEN", "")
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.cache_dir = os.environ.get(
            "CRASH_FIX_CACHE_DIR",
            os.path.join(os.path.expanduser("~"), ".cache", "crash-fix-tool"),
        )

    def validate_portal_credentials(self):
        """Validate that stack trace portal credentials are configured.

        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        if not self.portal_url:
            return False, "Stack trace portal credentials not configured: STACKTRACE_PORTAL_URL is not set"
        if not self.portal_token:
            return False, "Stack trace portal credentials not configured: STACKTRACE_PORTAL_TOKEN is not set"
        return True, None

    def validate_github_credentials(self):
        """Validate that GitHub credentials are configured.

        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        if not self.github_token:
            return False, "GitHub token not configured — cannot create PR"
        return True, None
