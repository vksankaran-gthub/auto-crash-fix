"""Unit tests for regression checker."""

import pytest
import responses

from crash_fix.regression_checker import RegressionChecker


PORTAL_URL = "https://stacktrace.example.com"
TOKEN = "test-token"


@pytest.fixture
def checker():
    return RegressionChecker(portal_url=PORTAL_URL, portal_token=TOKEN)


class TestMonitorCrashes:
    """Tests for monitor_crashes."""

    @responses.activate
    def test_no_crashes_detected_passes(self, checker):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/crashes",
            json={"crashes": []},
            status=200,
        )

        result = checker.monitor_crashes(
            "device-123", "FP-001", duration=1, poll_interval=0.5
        )
        assert result["status"] == "pass"
        assert result["original_reoccurred"] is False
        assert result["new_fingerprints"] == []

    @responses.activate
    def test_original_reoccurred_fails(self, checker):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/crashes",
            json={"crashes": [{"fingerprint_id": "FP-001"}]},
            status=200,
        )

        result = checker.monitor_crashes(
            "device-123", "FP-001", duration=1, poll_interval=0.5
        )
        assert result["status"] == "fail"
        assert result["original_reoccurred"] is True

    @responses.activate
    def test_new_fingerprint_fails(self, checker):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/crashes",
            json={"crashes": [{"fingerprint_id": "FP-NEW"}]},
            status=200,
        )

        result = checker.monitor_crashes(
            "device-123", "FP-001", duration=1, poll_interval=0.5
        )
        assert result["status"] == "fail"
        assert "FP-NEW" in result["new_fingerprints"]

    @responses.activate
    def test_portal_unreachable_inconclusive(self, checker):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/crashes",
            body=ConnectionError("unreachable"),
        )

        result = checker.monitor_crashes(
            "device-123", "FP-001", duration=1, poll_interval=0.5
        )
        assert result["status"] == "inconclusive"
        assert "portal unreachable" in result["error"].lower()

    def test_no_portal_url_inconclusive(self):
        c = RegressionChecker(portal_url="", portal_token="tok")
        result = c.monitor_crashes("dev", "FP-001", duration=1)
        assert result["status"] == "inconclusive"


class TestCorrelate:
    """Tests for _correlate logic."""

    def test_empty_crashes_pass(self, checker):
        result = checker._correlate([], "FP-001")
        assert result["status"] == "pass"

    def test_original_match(self, checker):
        crashes = [{"fingerprint_id": "FP-001"}]
        result = checker._correlate(crashes, "FP-001")
        assert result["status"] == "fail"
        assert result["original_reoccurred"] is True

    def test_new_crash(self, checker):
        crashes = [{"fingerprint_id": "FP-999"}]
        result = checker._correlate(crashes, "FP-001")
        assert result["status"] == "fail"
        assert "FP-999" in result["new_fingerprints"]

    def test_both_original_and_new(self, checker):
        crashes = [
            {"fingerprint_id": "FP-001"},
            {"fingerprint_id": "FP-888"},
        ]
        result = checker._correlate(crashes, "FP-001")
        assert result["status"] == "fail"
        assert result["original_reoccurred"] is True
        assert "FP-888" in result["new_fingerprints"]
