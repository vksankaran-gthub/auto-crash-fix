## ADDED Requirements

### Requirement: Deploy build to test device
The system SHALL deploy the successful build artifact to an available test device from the device pool.

#### Scenario: Device available and deployment succeeds
- **WHEN** a test device of the correct type is available in the device pool AND the build image is deployed successfully
- **THEN** the system SHALL record the device ID and confirm deployment via device reboot and health check

#### Scenario: No device available
- **WHEN** no test device of the correct type is available in the device pool
- **THEN** the system SHALL wait up to a configured timeout (default: 30 minutes), then report "No test device available" and exit with a non-zero return code

#### Scenario: Deployment fails
- **WHEN** the image deployment to the device fails (flash error, network issue)
- **THEN** the system SHALL retry once, and if still failing, report "Device deployment failed" and exit with a non-zero return code

### Requirement: Execute component-specific tests
The system SHALL run the test suite specific to the affected component on the deployed device.

#### Scenario: Tests identified and executed
- **WHEN** the component has a known test suite (mapped via component-to-test configuration)
- **THEN** the system SHALL execute all tests in the suite and collect results (pass/fail/skip counts and individual test details)

#### Scenario: No tests defined for component
- **WHEN** no test suite is mapped for the affected component
- **THEN** the system SHALL report "No tests defined for component '{name}'" and proceed with a warning (test validation is skipped but flagged in the PR)

#### Scenario: Test execution completes
- **WHEN** all component tests have completed
- **THEN** the system SHALL produce a test report containing: total tests, passed, failed, skipped, and individual test results with output

### Requirement: Release test device after completion
The system SHALL release the test device back to the device pool after test execution completes, regardless of test results.

#### Scenario: Device released successfully
- **WHEN** test execution is complete (pass or fail)
- **THEN** the system SHALL release the device back to the pool and confirm release
