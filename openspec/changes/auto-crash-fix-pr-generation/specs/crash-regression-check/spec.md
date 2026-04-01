## ADDED Requirements

### Requirement: Monitor for new crashes on test device
The system SHALL monitor the test device for new crashes during and after the test execution period to verify the fix does not introduce regressions.

#### Scenario: No new crashes detected
- **WHEN** the test device runs the patched build for the monitoring period (test execution + a configurable soak period, default 10 minutes) AND no new crash fingerprints appear
- **THEN** the system SHALL record "No crash regressions detected" and mark the regression check as PASS

#### Scenario: New crash detected matching original fingerprint
- **WHEN** a new crash is detected on the test device AND its fingerprint matches the original crash being fixed
- **THEN** the system SHALL report "Fix did not resolve the original crash — same fingerprint {id} re-occurred" and mark the regression check as FAIL

#### Scenario: New crash detected with different fingerprint
- **WHEN** a new crash is detected on the test device AND its fingerprint is different from the original
- **THEN** the system SHALL report "New crash introduced — fingerprint {new_id}" and mark the regression check as FAIL

### Requirement: Query stack trace portal for post-deployment crashes
The system SHALL poll the stack trace portal for any new crash reports from the test device's MAC address or serial number during the monitoring window.

#### Scenario: Portal polled successfully
- **WHEN** the monitoring period is active
- **THEN** the system SHALL query the portal at regular intervals (default: every 60 seconds) for crashes from the test device

#### Scenario: Portal unreachable during monitoring
- **WHEN** the stack trace portal is unreachable during the monitoring window
- **THEN** the system SHALL retry with exponential backoff and report "Crash regression check inconclusive — portal unreachable" if the entire monitoring window passes without successful queries
