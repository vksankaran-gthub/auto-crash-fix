"""Unit tests for the portal client."""

import pytest
import responses

from crash_fix.portal_client import PortalClient


PORTAL_URL = "https://stacktrace.example.com"
TOKEN = "test-token"


@pytest.fixture
def client():
    return PortalClient(PORTAL_URL, TOKEN)


class TestGetCrashMetadata:
    """Tests for get_crash_metadata."""

    @responses.activate
    def test_successful_metadata_retrieval(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-12345",
            json={
                "build_version": "rdkb-2025q4-sprint1",
                "timestamp": "2026-03-15T10:30:00Z",
                "minidump": {
                    "reference": "dump-abc123.dmp",
                    "crashing_module": "libwpe-1.0.so",
                    "type": "native",
                    "crash_address": "0x7fff1234abcd",
                },
            },
            status=200,
        )

        result = client.get_crash_metadata("FP-12345")
        assert result is not None
        assert result["build_version"] == "rdkb-2025q4-sprint1"
        assert result["component_name"] == "libwpe-1.0.so"
        assert result["component_type"] == "library"
        assert result["crash_timestamp"] == "2026-03-15T10:30:00Z"
        assert result["minidump_reference"] == "dump-abc123.dmp"

    @responses.activate
    def test_executable_component_type(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-99",
            json={
                "build_version": "v1.0",
                "minidump": {
                    "crashing_module": "WPEProcess",
                    "type": "native",
                },
            },
            status=200,
        )

        result = client.get_crash_metadata("FP-99")
        assert result["component_type"] == "executable"
        assert result["component_name"] == "WPEProcess"

    @responses.activate
    def test_script_crash(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-SCRIPT",
            json={
                "build_version": "v2.0",
                "minidump": {
                    "type": "script",
                    "script_path": "/usr/bin/my_script.sh",
                    "error_type": "syntax_error",
                },
            },
            status=200,
        )

        result = client.get_crash_metadata("FP-SCRIPT")
        assert result["component_type"] == "script"
        assert result["component_name"] == "/usr/bin/my_script.sh"

    @responses.activate
    def test_fingerprint_not_found(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-MISSING",
            json={"error": "not found"},
            status=404,
        )

        result = client.get_crash_metadata("FP-MISSING")
        assert result is None

    @responses.activate
    def test_server_error(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-ERR",
            json={"error": "internal"},
            status=500,
        )

        result = client.get_crash_metadata("FP-ERR")
        assert result is None

    @responses.activate
    def test_connection_error(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-1",
            body=ConnectionError("Connection refused"),
        )

        result = client.get_crash_metadata("FP-1")
        assert result is None


class TestGetBacktrace:
    """Tests for get_backtrace."""

    @responses.activate
    def test_successful_backtrace(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-12345/backtrace",
            json={
                "frames": [
                    {
                        "frame_number": 0,
                        "function_name": "crash_func",
                        "source_file": "src/main.cpp",
                        "line_number": 42,
                        "module": "libwpe-1.0.so",
                    },
                    {
                        "frame_number": 1,
                        "function_name": "caller_func",
                        "source_file": "src/caller.cpp",
                        "line_number": 100,
                        "module": "libwpe-1.0.so",
                    },
                ]
            },
            status=200,
        )

        result = client.get_backtrace("FP-12345")
        assert result is not None
        assert len(result) == 2
        assert result[0]["function_name"] == "crash_func"
        assert result[0]["source_file"] == "src/main.cpp"
        assert result[0]["line_number"] == 42

    @responses.activate
    def test_backtrace_not_available(self, client):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/fingerprints/FP-NOBT/backtrace",
            status=404,
        )

        result = client.get_backtrace("FP-NOBT")
        assert result is None


class TestParseMinidump:
    """Tests for _parse_minidump."""

    def test_native_library_crash(self):
        result = PortalClient._parse_minidump(
            {"crashing_module": "libfoo.so.2", "type": "native", "crash_address": "0xdead"}
        )
        assert result["component_name"] == "libfoo.so.2"
        assert result["component_type"] == "library"
        assert result["crash_address"] == "0xdead"

    def test_native_executable_crash(self):
        result = PortalClient._parse_minidump(
            {"crashing_module": "WPEWebProcess", "type": "native"}
        )
        assert result["component_type"] == "executable"

    def test_script_crash(self):
        result = PortalClient._parse_minidump(
            {"type": "script", "script_path": "/opt/run.sh", "error_type": "exit_code_1"}
        )
        assert result["component_type"] == "script"
        assert result["component_name"] == "/opt/run.sh"
