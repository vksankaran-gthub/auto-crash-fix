## ADDED Requirements

### Requirement: Construct structured prompt for AI fix generation
The system SHALL construct a structured prompt containing the crash context and send it to the GitHub Copilot API to request a code fix.

#### Scenario: Prompt constructed with full context
- **WHEN** the backtrace, source code around the crash site, component name, crash type, and repository context are all available
- **THEN** the system SHALL construct a prompt containing: (a) component and repository context, (b) crash type classification, (c) full backtrace, (d) relevant source code, and (e) instruction to provide a minimal fix with root cause explanation

#### Scenario: Partial context available
- **WHEN** some context is missing (e.g., source code not found but backtrace is available)
- **THEN** the system SHALL construct the prompt with available data and flag the missing context in the prompt so the AI is aware of limitations

### Requirement: Parse AI response into applicable patch
The system SHALL parse the AI-generated response and extract a code patch that can be applied to the source repository.

#### Scenario: AI provides a valid diff
- **WHEN** the AI response contains code changes in diff or code-block format
- **THEN** the system SHALL extract the changes and create a git-compatible patch file

#### Scenario: AI response is not actionable
- **WHEN** the AI response does not contain clear code changes (e.g., only provides analysis without a fix)
- **THEN** the system SHALL report "AI could not generate an actionable fix" with the AI's analysis text, and exit with a specific return code indicating no fix was produced

### Requirement: Apply generated patch to source repository
The system SHALL apply the AI-generated patch to the cloned source repository and verify it applies cleanly.

#### Scenario: Patch applies cleanly
- **WHEN** the generated patch is applied via `git apply`
- **THEN** the system SHALL commit the change with a structured commit message containing the fingerprint ID and crash summary

#### Scenario: Patch fails to apply
- **WHEN** `git apply` fails (e.g., conflicts, incorrect line numbers)
- **THEN** the system SHALL report "Patch failed to apply" with the git error output and exit with a non-zero return code

### Requirement: Report AI confidence level
The system SHALL assess and report a confidence level for the generated fix based on the completeness of the crash context and the AI's response.

#### Scenario: High confidence fix
- **WHEN** full backtrace, source code, and clear crash type are available AND the AI provides a focused single-function fix
- **THEN** the system SHALL report confidence as "high"

#### Scenario: Low confidence fix
- **WHEN** context is partial OR the AI response modifies multiple files OR the crash type is "unknown"
- **THEN** the system SHALL report confidence as "low" and include a recommendation for manual review
