"""HTTP client for the stack trace portal REST API."""

import sys

import click
import requests


class PortalClient:
    """Client for the stack trace portal REST API."""

    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )

    def get_crash_metadata(self, fingerprint_id):
        """Fetch crash metadata for a given fingerprint ID.

        Returns a dict with: build_version, minidump_reference,
        component_name, component_type, crash_timestamp.
        Returns None on error (after printing error message).
        """
        url = f"{self.base_url}/api/v1/fingerprints/{fingerprint_id}"
        try:
            resp = self.session.get(url, timeout=30)
        except (requests.ConnectionError, ConnectionError):
            click.echo(
                f"Error: Stack trace portal unreachable at {url}", err=True
            )
            return None
        except requests.Timeout:
            click.echo(
                f"Error: Request timed out connecting to {url}", err=True
            )
            return None

        if resp.status_code == 404:
            click.echo(
                f"Error: Fingerprint not found: {fingerprint_id}", err=True
            )
            return None

        if resp.status_code != 200:
            click.echo(
                f"Error: Portal API returned HTTP {resp.status_code} for {url}",
                err=True,
            )
            return None

        data = resp.json()

        # Extract and normalize metadata
        metadata = {
            "build_version": data.get("build_version", ""),
            "minidump_reference": data.get("minidump", {}).get("reference", ""),
            "component_name": "",
            "component_type": "unknown",
            "crash_timestamp": data.get("timestamp", ""),
        }

        # Parse minidump to extract crashing component
        minidump = data.get("minidump", {})
        metadata.update(self._parse_minidump(minidump))

        return metadata

    def get_backtrace(self, fingerprint_id):
        """Fetch the full backtrace for a given fingerprint ID.

        Returns a list of stack frame dicts, each containing:
        frame_number, function_name, source_file, line_number, module.
        Returns None if backtrace is not available (with warning).
        """
        url = f"{self.base_url}/api/v1/fingerprints/{fingerprint_id}/backtrace"
        try:
            resp = self.session.get(url, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            click.echo(
                f"Warning: Could not fetch backtrace from {url}", err=True
            )
            return None

        if resp.status_code != 200:
            click.echo(
                f"Warning: Backtrace not available for fingerprint {fingerprint_id}",
                err=True,
            )
            return None

        data = resp.json()
        frames = data.get("frames", data.get("backtrace", []))

        backtrace = []
        for i, frame in enumerate(frames):
            backtrace.append(
                {
                    "frame_number": frame.get("frame_number", i),
                    "function_name": frame.get("function_name", frame.get("function", "")),
                    "source_file": frame.get("source_file", frame.get("file", "")),
                    "line_number": frame.get("line_number", frame.get("line", None)),
                    "module": frame.get("module", frame.get("library", "")),
                }
            )

        return backtrace if backtrace else None

    @staticmethod
    def _parse_minidump(minidump):
        """Parse minidump info to extract crashing component details.

        Returns a dict with component_name, component_type, and optionally
        crash_address or script_error_type.
        """
        result = {}
        crash_module = minidump.get("crashing_module", minidump.get("module", ""))
        crash_type = minidump.get("type", "native")

        if crash_type in ("script", "python", "shell"):
            # Script-level crash
            result["component_name"] = minidump.get("script_path", crash_module)
            result["component_type"] = "script"
            result["script_error_type"] = minidump.get("error_type", "")
        else:
            # Native crash (C/C++ binary or shared library)
            result["component_name"] = crash_module
            if crash_module.endswith(".so") or ".so." in crash_module:
                result["component_type"] = "library"
            else:
                result["component_type"] = "executable"
            result["crash_address"] = minidump.get("crash_address", "")

        return result
