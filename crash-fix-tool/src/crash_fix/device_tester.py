"""Device deployment and test execution module.

Deploys images to test devices, runs component tests,
and manages device pool lifecycle.
"""

import click
import requests


class DeviceTester:
    """Manages device deployment and test execution."""

    # Default wait timeout for device availability: 30 minutes
    DEFAULT_DEVICE_TIMEOUT = 30 * 60

    def __init__(self, device_pool_url=None, device_pool_token=None):
        self.pool_url = device_pool_url or ""
        self.pool_token = device_pool_token or ""

    def acquire_device(self, device_type, timeout=None):
        """Acquire a test device from the pool.

        Args:
            device_type: Required device type/model.
            timeout: Max seconds to wait (default: 30 min).

        Returns:
            dict with 'device_id' (str or None), 'error' (str or None).
        """
        if timeout is None:
            timeout = self.DEFAULT_DEVICE_TIMEOUT

        if not self.pool_url:
            return {"device_id": None, "error": "Device pool URL not configured"}

        headers = self._auth_headers()
        payload = {"device_type": device_type, "timeout": timeout}

        try:
            resp = requests.post(
                f"{self.pool_url}/api/v1/devices/acquire",
                headers=headers,
                json=payload,
                timeout=min(timeout + 30, 1860),
            )
        except (requests.ConnectionError, ConnectionError):
            return {"device_id": None, "error": "Device pool unreachable"}
        except requests.Timeout:
            return {"device_id": None, "error": "No test device available"}

        if resp.status_code != 200:
            return {
                "device_id": None,
                "error": f"Device acquisition failed: HTTP {resp.status_code}",
            }

        data = resp.json()
        return {"device_id": data.get("device_id"), "error": None}

    def deploy_image(self, device_id, image_url, retries=1):
        """Deploy build artifact to test device with retry logic.

        Args:
            device_id: Target device identifier.
            image_url: URL of the build image to deploy.
            retries: Number of retry attempts on failure.

        Returns:
            dict with 'success' (bool), 'error' (str or None).
        """
        if not self.pool_url:
            return {"success": False, "error": "Device pool URL not configured"}

        headers = self._auth_headers()
        payload = {"device_id": device_id, "image_url": image_url}

        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    f"{self.pool_url}/api/v1/devices/{device_id}/deploy",
                    headers=headers,
                    json=payload,
                    timeout=600,
                )
            except (requests.ConnectionError, ConnectionError, requests.Timeout):
                if attempt < retries:
                    click.echo(f"Deployment attempt {attempt + 1} failed, retrying...", err=True)
                    continue
                return {"success": False, "error": "Device deployment failed"}

            if resp.status_code == 200:
                return {"success": True, "error": None}

            if attempt < retries:
                click.echo(f"Deployment attempt {attempt + 1} failed (HTTP {resp.status_code}), retrying...", err=True)

        return {"success": False, "error": "Device deployment failed"}

    def run_component_tests(self, device_id, component_name):
        """Execute component-specific test suite on device.

        Args:
            device_id: Target device identifier.
            component_name: Name of the component to test.

        Returns:
            dict with 'total', 'passed', 'failed', 'skipped' (ints),
            'results' (list), 'error' (str or None),
            'tests_defined' (bool).
        """
        if not self.pool_url:
            return self._no_tests_result("Device pool URL not configured")

        headers = self._auth_headers()

        try:
            resp = requests.post(
                f"{self.pool_url}/api/v1/devices/{device_id}/test",
                headers=headers,
                json={"component": component_name},
                timeout=1800,
            )
        except (requests.ConnectionError, ConnectionError, requests.Timeout):
            return self._no_tests_result("Test execution failed: device unreachable")

        if resp.status_code == 404:
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
                "error": None,
                "tests_defined": False,
            }

        if resp.status_code != 200:
            return self._no_tests_result(f"Test execution failed: HTTP {resp.status_code}")

        data = resp.json()
        return {
            "total": data.get("total", 0),
            "passed": data.get("passed", 0),
            "failed": data.get("failed", 0),
            "skipped": data.get("skipped", 0),
            "results": data.get("results", []),
            "error": None,
            "tests_defined": True,
        }

    def release_device(self, device_id):
        """Release device back to pool.

        Args:
            device_id: Device to release.

        Returns:
            dict with 'success' (bool), 'error' (str or None).
        """
        if not self.pool_url:
            return {"success": False, "error": "Device pool URL not configured"}

        headers = self._auth_headers()

        try:
            resp = requests.post(
                f"{self.pool_url}/api/v1/devices/{device_id}/release",
                headers=headers,
                timeout=30,
            )
        except (requests.ConnectionError, ConnectionError, requests.Timeout):
            return {"success": False, "error": "Failed to release device"}

        return {
            "success": resp.status_code == 200,
            "error": None if resp.status_code == 200 else f"Release failed: HTTP {resp.status_code}",
        }

    def _auth_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.pool_token:
            headers["Authorization"] = f"Bearer {self.pool_token}"
        return headers

    @staticmethod
    def _no_tests_result(error):
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "error": error,
            "tests_defined": False,
        }
