## ADDED Requirements

### Requirement: Retrieve full backtrace from stack trace portal
The system SHALL fetch the full function backtrace for the given crash fingerprint from the stack trace portal API.

#### Scenario: Backtrace retrieved successfully
- **WHEN** a valid fingerprint ID is provided and the portal has backtrace data
- **THEN** the system SHALL return the full backtrace as a structured list of stack frames, each containing: frame number, function name (if symbolicated), source file (if available), line number (if available), and module/library name

#### Scenario: Backtrace not available
- **WHEN** the portal has the fingerprint but no backtrace data is available (e.g., minidump could not be processed)
- **THEN** the system SHALL report "Backtrace not available for fingerprint {id}" and continue with a warning (non-fatal)

### Requirement: Identify crash site in source code
The system SHALL use the backtrace to identify the specific source file(s) and function(s) at the crash site in the cloned source repository.

#### Scenario: Source file found in repository
- **WHEN** the backtrace contains a source file path and line number AND the file exists in the cloned repository
- **THEN** the system SHALL extract the source code context (the crashing function plus surrounding context of at least 50 lines before and after)

#### Scenario: Source file not found in repository
- **WHEN** the backtrace references a source file that does not exist in the cloned repository at the given SRCREV
- **THEN** the system SHALL report "Source file '{path}' not found at SRCREV {hash}" and attempt to match by filename only across the repository

### Requirement: Extract crash type classification
The system SHALL classify the crash type from the backtrace and minidump information.

#### Scenario: Segmentation fault detected
- **WHEN** the backtrace indicates a SIGSEGV signal
- **THEN** the system SHALL classify the crash as "segfault" and extract the faulting address

#### Scenario: Abort signal detected
- **WHEN** the backtrace indicates a SIGABRT signal
- **THEN** the system SHALL classify the crash as "abort" and extract any assertion message if present

#### Scenario: Unclassified crash
- **WHEN** the crash type cannot be determined from available data
- **THEN** the system SHALL classify as "unknown" and include all available signal/exception information
