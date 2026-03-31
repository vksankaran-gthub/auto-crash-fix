"""
Fingerprint authentication module.

This module provides fingerprint data processing and authentication utilities.
"""


class FingerprintData:
    """Represents raw fingerprint scan data."""

    def __init__(self, raw_bytes: bytes, quality: int = 100):
        if not isinstance(raw_bytes, bytes):
            raise TypeError("raw_bytes must be a bytes object")
        self.raw_bytes = raw_bytes
        self.quality = quality

    def __len__(self):
        return len(self.raw_bytes)


def extract_minutiae(fingerprint: FingerprintData) -> list:
    """
    Extract minutiae (ridge endings and bifurcations) from fingerprint data.

    Args:
        fingerprint: A FingerprintData object containing the raw scan.

    Returns:
        A list of minutiae feature points extracted from the fingerprint.

    Raises:
        ValueError: If fingerprint is None or contains no data.
    """
    if fingerprint is None:
        raise ValueError("fingerprint must not be None")

    if len(fingerprint) == 0:
        raise ValueError("fingerprint data must not be empty")

    # Simulate minutiae extraction from raw bytes
    minutiae = []
    for i, byte in enumerate(fingerprint.raw_bytes):
        if byte > 128:
            minutiae.append({"type": "ridge_ending", "position": i, "angle": byte % 180})
        elif byte > 64:
            minutiae.append({"type": "bifurcation", "position": i, "angle": byte % 180})
    return minutiae


def match_fingerprints(probe: FingerprintData, template: FingerprintData, threshold: float = 0.7) -> bool:
    """
    Compare a probe fingerprint against a stored template.

    Args:
        probe:     The fingerprint scan to authenticate.
        template:  The stored reference fingerprint template.
        threshold: Minimum similarity score (0.0–1.0) required for a match.

    Returns:
        True if the fingerprints match above the threshold, False otherwise.

    Raises:
        ValueError: If either probe or template is None or empty.
    """
    if probe is None:
        raise ValueError("probe fingerprint must not be None")

    if template is None:
        raise ValueError("template fingerprint must not be None")

    if len(probe) == 0:
        raise ValueError("probe fingerprint data must not be empty")

    if len(template) == 0:
        raise ValueError("template fingerprint data must not be empty")

    probe_minutiae = extract_minutiae(probe)
    template_minutiae = extract_minutiae(template)

    if not template_minutiae:
        return False

    # Count how many probe minutiae are close to a template minutia
    matched = sum(
        1
        for pm in probe_minutiae
        if any(
            abs(pm["position"] - tm["position"]) <= 2 and abs(pm["angle"] - tm["angle"]) <= 10
            for tm in template_minutiae
        )
    )

    score = matched / max(len(template_minutiae), 1)
    return score >= threshold


def authenticate(fingerprint: FingerprintData, stored_template: FingerprintData) -> bool:
    """
    Authenticate a user by comparing their fingerprint to a stored template.

    Args:
        fingerprint:     The live fingerprint scan captured from the sensor.
        stored_template: The enrolled fingerprint template to compare against.

    Returns:
        True if authentication succeeds, False otherwise.
    """
    if fingerprint is None or stored_template is None:
        return False

    try:
        return match_fingerprints(fingerprint, stored_template)
    except ValueError:
        return False
