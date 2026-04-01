"""Crash regression monitoring module.

Monitors test devices for new crashes after deploying a fix,
correlates with the original fingerprint to detect regressions.
"""

import time

import click
import requests


class RegressionChecker:
    """Monitors for crash regressions on test devices."""

    # Default soak period: 10 minutes
    DEFAULT_SOAK_DURATION = 10 * 60
    # Default poll interval: 60 seconds
    DEFAULT_POLL_INTERVAL = 60
    # Max backoff for retries: 5 minutes
    MAX_BACKOFF = 300

    def __init__(self, portal_url=None, portal_token=None):
        self.portal_url = portal_url or ""
        self.portal_token = portal_token or ""

    def monitor_crashes(
        self, device_id, original_fingerprint, duration=None, poll_interval=None
    ):
        """Poll stack trace portal for new crashes from device.

        Args:
            device_id: MAC address or serial number of the device.
            original_fingerprint: The fingerprint ID being fixed.
            duration: Soak period in seconds (default: 10 min).
            poll_interval: Seconds between polls (default: 60s).

        Returns:
            dict with 'status' ('pass'|'fail'|'inconclusive'),
            'crashes_found' (list), 'error' (str or None),
            'original_reoccurred' (bool), 'new_fingerprints' (list).
        """
        if duration is None:
            duration = self.DEFAULT_SOAK_DURATION
        if poll_interval is None:
            poll_interval = self.DEFAULT_POLL_INTERVAL

        if not self.portal_url:
            return {
                "status": "inconclusive",
                "crashes_found": [],
                "error": "Portal URL not configured",
                "original_reoccurred": False,
                "new_fingerprints": [],
            }

        deadline = time.time() + duration
        crashes_found = []
        successful_queries = 0
        backoff = poll_interval
        headers = self._auth_headers()

        while time.time() < deadline:
            result = self._query_portal(headers, device_id)

            if result is None:
                # Portal unreachable — exponential backoff
                backoff = min(backoff * 2, self.MAX_BACKOFF)
                click.echo("Warning: Portal unreachable, retrying with backoff...", err=True)
                time.sleep(min(backoff, deadline - time.time()))
                continue

            successful_queries += 1
            backoff = poll_interval

            for crash in result:
                fp = crash.get("fingerprint_id", "")
                if fp and fp not in [c.get("fingerprint_id") for c in crashes_found]:
                    crashes_found.append(crash)

            time.sleep(min(poll_interval, max(0, deadline - time.time())))

        if successful_queries == 0:
            return {
                "status": "inconclusive",
                "crashes_found": crashes_found,
                "error": "Crash regression check inconclusive — portal unreachable",
                "original_reoccurred": False,
                "new_fingerprints": [],
            }

        return self._correlate(crashes_found, original_fingerprint)

    def _correlate(self, crashes, original_fingerprint):
        """Classify detected crashes relative to the original."""
        original_reoccurred = False
        new_fingerprints = []

        for crash in crashes:
            fp = crash.get("fingerprint_id", "")
            if fp == original_fingerprint:
                original_reoccurred = True
            else:
                new_fingerprints.append(fp)

        if not crashes:
            return {
                "status": "pass",
                "crashes_found": [],
                "error": None,
                "original_reoccurred": False,
                "new_fingerprints": [],
            }

        status = "fail"
        error = None
        if original_reoccurred:
            error = (
                f"Fix did not resolve the original crash — "
                f"same fingerprint {original_fingerprint} re-occurred"
            )
        elif new_fingerprints:
            error = f"New crash introduced — fingerprint {new_fingerprints[0]}"

        return {
            "status": status,
            "crashes_found": crashes,
            "error": error,
            "original_reoccurred": original_reoccurred,
            "new_fingerprints": new_fingerprints,
        }

    def _query_portal(self, headers, device_id):
        """Query portal for crashes from a specific device."""
        try:
            resp = requests.get(
                f"{self.portal_url}/api/v1/crashes",
                headers=headers,
                params={"device_id": device_id},
                timeout=30,
            )
        except (requests.ConnectionError, ConnectionError, requests.Timeout):
            return None

        if resp.status_code != 200:
            return None

        return resp.json().get("crashes", [])

    def _auth_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.portal_token:
            headers["Authorization"] = f"Bearer {self.portal_token}"
        return headers
