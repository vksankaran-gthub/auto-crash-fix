## ADDED Requirements

### Requirement: Trigger build with patched source
The system SHALL trigger a build in the CI/CD system using the patched source code for the affected recipe.

#### Scenario: Build triggered successfully
- **WHEN** the patched source repository is pushed to a feature branch AND the CI/CD API is available
- **THEN** the system SHALL trigger a build for the affected recipe/component and return a build job ID for tracking

#### Scenario: CI/CD system unreachable
- **WHEN** the CI/CD system API is unreachable
- **THEN** the system SHALL report "Build system unreachable" and exit with a non-zero return code

### Requirement: Monitor build status
The system SHALL poll the build job status until completion or timeout.

#### Scenario: Build succeeds
- **WHEN** the build job completes with a success status
- **THEN** the system SHALL record the build artifact location (image URL or path) and proceed to the next phase

#### Scenario: Build fails
- **WHEN** the build job completes with a failure status
- **THEN** the system SHALL report "Build failed" with the build log URL, discard the fix, and exit with a non-zero return code

#### Scenario: Build times out
- **WHEN** the build does not complete within the configured timeout period (default: 4 hours)
- **THEN** the system SHALL report "Build timed out after {timeout}" and exit with a non-zero return code

### Requirement: Support incremental builds
The system SHALL attempt an incremental (component-only) build before falling back to a full image build.

#### Scenario: Incremental build available
- **WHEN** the CI/CD system supports building a single recipe/component
- **THEN** the system SHALL trigger a component-only build first for faster validation

#### Scenario: Incremental build not available
- **WHEN** the CI/CD system only supports full image builds
- **THEN** the system SHALL trigger a full image build and log a warning about expected longer build time
