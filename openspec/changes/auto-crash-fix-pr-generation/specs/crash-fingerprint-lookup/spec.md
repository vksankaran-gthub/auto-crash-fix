## ADDED Requirements

### Requirement: Accept fingerprint ID as input
The system SHALL accept a crash fingerprint ID (string) as the primary input parameter via CLI argument.

#### Scenario: Valid fingerprint ID provided
- **WHEN** the user provides a valid fingerprint ID as a CLI argument
- **THEN** the system SHALL use this ID to query the stack trace portal API

#### Scenario: No fingerprint ID provided
- **WHEN** the user invokes the tool without a fingerprint ID
- **THEN** the system SHALL display a usage message and exit with a non-zero return code

### Requirement: Fetch crash metadata from stack trace portal
The system SHALL query the stack trace portal REST API with the given fingerprint ID and retrieve the crash metadata including build version, minidump file reference, and the name of the crashing component (library, executable, or script).

#### Scenario: Successful metadata retrieval
- **WHEN** the fingerprint ID exists in the stack trace portal
- **THEN** the system SHALL return a structured object containing: build version (string), minidump reference (string), crashing component name (string), component type (one of: library, executable, script), and crash timestamp

#### Scenario: Fingerprint ID not found
- **WHEN** the fingerprint ID does not exist in the stack trace portal
- **THEN** the system SHALL report an error message "Fingerprint not found: {id}" and exit with a non-zero return code

#### Scenario: Portal API unreachable
- **WHEN** the stack trace portal API is unreachable or returns an HTTP error
- **THEN** the system SHALL report a connection error with the HTTP status code and URL attempted, and exit with a non-zero return code

### Requirement: Extract minidump details
The system SHALL parse the minidump information associated with the crash to identify the specific binary, library, or script file that crashed.

#### Scenario: Minidump contains native crash info
- **WHEN** the minidump indicates a native crash (C/C++ binary or shared library)
- **THEN** the system SHALL extract the crashing module name (e.g., `libwpe-1.0.so`) and the crash address/offset

#### Scenario: Minidump indicates script crash
- **WHEN** the crash originates from a script-level component (e.g., shell script, Python)
- **THEN** the system SHALL extract the script file path and the error type

### Requirement: Authenticate with stack trace portal
The system SHALL authenticate with the stack trace portal using credentials provided via environment variables or a configuration file. Credentials MUST NOT be passed as CLI arguments.

#### Scenario: Credentials via environment variables
- **WHEN** the environment variables `STACKTRACE_PORTAL_URL` and `STACKTRACE_PORTAL_TOKEN` are set
- **THEN** the system SHALL use these to authenticate API requests

#### Scenario: Missing credentials
- **WHEN** the required environment variables are not set and no configuration file is found
- **THEN** the system SHALL report "Stack trace portal credentials not configured" and exit with a non-zero return code
