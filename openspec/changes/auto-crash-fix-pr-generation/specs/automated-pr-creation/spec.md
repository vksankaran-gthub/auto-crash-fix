## ADDED Requirements

### Requirement: Create Pull Request with validated fix
The system SHALL create a Pull Request on the source repository via the GitHub API when all validation checks pass (build success, tests pass, no crash regressions).

#### Scenario: All checks pass — PR created
- **WHEN** the build succeeds AND component tests pass AND crash regression check passes
- **THEN** the system SHALL create a PR on the source repository's default branch with a feature branch containing the fix commit

#### Scenario: Tests fail — no PR created
- **WHEN** the component tests fail OR the crash regression check fails
- **THEN** the system SHALL NOT create a PR and SHALL report "Validation failed — PR not created" with details of which checks failed

#### Scenario: Build failed — no PR created
- **WHEN** the build fails
- **THEN** the system SHALL NOT create a PR and SHALL report "Build failed — PR not created"

### Requirement: PR description contains full audit trail
The PR description SHALL contain a structured audit trail linking the fix back to the originating crash.

#### Scenario: Full PR description generated
- **WHEN** a PR is being created
- **THEN** the PR description SHALL contain: (a) originating crash fingerprint ID, (b) crash summary (component, crash type, build version), (c) backtrace excerpt (top 10 frames), (d) AI-generated root cause explanation, (e) fix description, (f) build result URL, (g) test results summary, (h) crash regression check result, (i) AI confidence level

### Requirement: PR metadata and labels
The system SHALL apply appropriate labels and metadata to the created PR.

#### Scenario: PR labels applied
- **WHEN** a PR is created
- **THEN** the system SHALL apply labels: `auto-generated`, `crash-fix`, `fingerprint:{id}`, and the AI confidence level label (`high-confidence` or `low-confidence`)

### Requirement: Notify on PR creation
The system SHALL output the PR URL and summary upon successful creation.

#### Scenario: Successful notification
- **WHEN** the PR is created successfully
- **THEN** the system SHALL print the PR URL, title, and a one-line summary to stdout

### Requirement: Authenticate with GitHub for PR creation
The system SHALL use a GitHub token provided via environment variable `GITHUB_TOKEN` to authenticate for PR creation. The token MUST NOT be logged or included in output.

#### Scenario: GitHub token available
- **WHEN** the `GITHUB_TOKEN` environment variable is set
- **THEN** the system SHALL use it for GitHub API authentication

#### Scenario: GitHub token missing
- **WHEN** the `GITHUB_TOKEN` environment variable is not set
- **THEN** the system SHALL report "GitHub token not configured — cannot create PR" and exit with a non-zero return code
