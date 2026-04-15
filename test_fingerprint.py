"""
Tests for the fingerprint authentication module.

These tests cover normal operation as well as the crash fix for None/empty
fingerprint inputs that previously caused unhandled exceptions.
"""

import pytest
from fingerprint import FingerprintData, authenticate, extract_minutiae, match_fingerprints


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_fingerprint():
    """A fingerprint with realistic byte data."""
    raw = bytes([130, 70, 200, 50, 180, 90, 140, 30, 160, 75])
    return FingerprintData(raw, quality=95)


@pytest.fixture
def matching_template():
    """A template that is close enough to sample_fingerprint to match."""
    raw = bytes([131, 70, 201, 50, 179, 90, 141, 30, 161, 75])
    return FingerprintData(raw, quality=90)


@pytest.fixture
def non_matching_template():
    """A template with completely different data."""
    raw = bytes([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
    return FingerprintData(raw, quality=90)


# ---------------------------------------------------------------------------
# FingerprintData construction
# ---------------------------------------------------------------------------

class TestFingerprintData:
    def test_valid_construction(self):
        fp = FingerprintData(b"\x01\x02\x03")
        assert len(fp) == 3

    def test_default_quality(self):
        fp = FingerprintData(b"\x01")
        assert fp.quality == 100

    def test_custom_quality(self):
        fp = FingerprintData(b"\x01", quality=80)
        assert fp.quality == 80

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            FingerprintData("not bytes")


# ---------------------------------------------------------------------------
# extract_minutiae
# ---------------------------------------------------------------------------

class TestExtractMinutiae:
    def test_returns_list(self, sample_fingerprint):
        result = extract_minutiae(sample_fingerprint)
        assert isinstance(result, list)

    def test_minutiae_have_expected_keys(self, sample_fingerprint):
        result = extract_minutiae(sample_fingerprint)
        for m in result:
            assert "type" in m
            assert "position" in m
            assert "angle" in m

    # --- crash-fix tests ---

    def test_none_fingerprint_raises_value_error(self):
        """Previously crashed with AttributeError; must now raise ValueError."""
        with pytest.raises(ValueError, match="None"):
            extract_minutiae(None)

    def test_empty_fingerprint_raises_value_error(self):
        """Empty fingerprint data must raise ValueError, not crash."""
        empty = FingerprintData(b"")
        with pytest.raises(ValueError, match="empty"):
            extract_minutiae(empty)


# ---------------------------------------------------------------------------
# match_fingerprints
# ---------------------------------------------------------------------------

class TestMatchFingerprints:
    def test_matching_fingerprints_returns_true(self, sample_fingerprint, matching_template):
        assert match_fingerprints(sample_fingerprint, matching_template) is True

    def test_non_matching_fingerprints_returns_false(self, sample_fingerprint, non_matching_template):
        assert match_fingerprints(sample_fingerprint, non_matching_template) is False

    # --- crash-fix tests ---

    def test_none_probe_raises_value_error(self, matching_template):
        """Passing None as probe must raise ValueError, not crash."""
        with pytest.raises(ValueError, match="probe"):
            match_fingerprints(None, matching_template)

    def test_none_template_raises_value_error(self, sample_fingerprint):
        """Passing None as template must raise ValueError, not crash."""
        with pytest.raises(ValueError, match="template"):
            match_fingerprints(sample_fingerprint, None)

    def test_empty_probe_raises_value_error(self, matching_template):
        """Empty probe must raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            match_fingerprints(FingerprintData(b""), matching_template)

    def test_empty_template_raises_value_error(self, sample_fingerprint):
        """Empty template must raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            match_fingerprints(sample_fingerprint, FingerprintData(b""))


# ---------------------------------------------------------------------------
# authenticate (public API — swallows exceptions gracefully)
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_valid_match_returns_true(self, sample_fingerprint, matching_template):
        assert authenticate(sample_fingerprint, matching_template) is True

    def test_no_match_returns_false(self, sample_fingerprint, non_matching_template):
        assert authenticate(sample_fingerprint, non_matching_template) is False

    # --- crash-fix tests ---

    def test_none_fingerprint_returns_false(self, matching_template):
        """None fingerprint must return False instead of crashing."""
        assert authenticate(None, matching_template) is False

    def test_none_template_returns_false(self, sample_fingerprint):
        """None template must return False instead of crashing."""
        assert authenticate(sample_fingerprint, None) is False

    def test_both_none_returns_false(self):
        """Both arguments None must return False instead of crashing."""
        assert authenticate(None, None) is False

    def test_empty_fingerprint_returns_false(self, matching_template):
        """Empty fingerprint bytes must return False instead of crashing."""
        assert authenticate(FingerprintData(b""), matching_template) is False

    def test_empty_template_returns_false(self, sample_fingerprint):
        """Empty template bytes must return False instead of crashing."""
        assert authenticate(sample_fingerprint, FingerprintData(b"")) is False
