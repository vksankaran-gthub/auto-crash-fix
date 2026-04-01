## Phase 1: Data Pipeline — Crash Fingerprint Lookup & Component Tracing

### 1. Project Setup

- [x] 1.1 Create project directory structure: `crash-fix-tool/` with `src/`, `config/`, `tests/` subdirectories
- [x] 1.2 Create `pyproject.toml` with project metadata and dependencies (requests, click, pyyaml)
- [x] 1.3 Create CLI entry point using Click with `crash-fix` main command and `lookup` subcommand
- [x] 1.4 Create configuration module that reads credentials from environment variables (`STACKTRACE_PORTAL_URL`, `STACKTRACE_PORTAL_TOKEN`, `GITHUB_TOKEN`)
- [x] 1.5 Add error handling for missing credentials — clear error messages per spec

### 2. Stack Trace Portal Client

- [x] 2.1 Create `portal_client.py` — HTTP client class for the stack trace portal REST API with authentication
- [x] 2.2 Implement `get_crash_metadata(fingerprint_id)` — fetch build version, minidump reference, crashing component name, component type, and crash timestamp
- [x] 2.3 Implement `get_backtrace(fingerprint_id)` — fetch full backtrace as a structured list of stack frames (frame number, function name, source file, line number, module)
- [x] 2.4 Implement error handling: fingerprint not found, API unreachable, HTTP errors — per spec scenarios
- [x] 2.5 Implement minidump parser — extract crashing module name and crash address (native) or script file path (script crash)
- [x] 2.6 Implement crash type classification from backtrace — segfault (SIGSEGV), abort (SIGABRT), unknown

### 3. Yocto Recipe Tracing

- [x] 3.1 Create `yocto_tracer.py` — module for mapping component names to source repositories
- [x] 3.2 Implement `find_recipe(component_name)` — run `oe-pkgdata-util find-path` and `lookup-recipe` to get recipe name
- [x] 3.3 Implement `extract_source_info(recipe_name)` — parse `bitbake -e <recipe>` output for `SRC_URI`, `SRCREV`, `S` variables
- [x] 3.4 Handle non-git sources — detect tarball SRC_URI and report "manual investigation required" per spec
- [x] 3.5 Handle missing bitbake — detect when bitbake is not available and report per spec
- [x] 3.6 Implement source repository cloning — clone repo at SRCREV to temp working directory, with local cache support

### 4. Crash Site Identification

- [x] 4.1 Implement `locate_crash_source(backtrace, repo_path)` — find source file(s) in cloned repo matching backtrace frames
- [x] 4.2 Implement fallback source matching — match by filename only across repo when full path doesn't match
- [x] 4.3 Implement source context extraction — extract crashing function plus 50 lines of surrounding context

### 5. Phase 1 Output & Report

- [x] 5.1 Create structured JSON report for Phase 1: fingerprint ID, crash metadata, recipe trace, repo info, backtrace, crash site source context
- [x] 5.2 Implement `crash-fix lookup <fingerprint-id>` CLI command that runs the full Phase 1 pipeline and outputs the report
- [x] 5.3 Write unit tests for portal client (mock API responses for success, not-found, unreachable scenarios)
- [x] 5.4 Write unit tests for Yocto tracer (mock bitbake outputs)
- [x] 5.5 Write integration test — end-to-end Phase 1 with mock portal and local git repo

## Phase 2: AI-Assisted Fix Generation

### 6. AI Prompt Construction

- [x] 6.1 Create `ai_fix_generator.py` — module for AI-assisted fix generation
- [x] 6.2 Implement `build_prompt(crash_context)` — construct structured prompt with: component context, crash type, backtrace, source code, fix instruction
- [x] 6.3 Handle partial context — flag missing elements in prompt per spec

### 7. Copilot API Integration

- [x] 7.1 Implement Copilot/AI API client — send prompt and receive response
- [x] 7.2 Implement response parser — extract code diff/patch from AI response
- [x] 7.3 Handle non-actionable responses — detect when AI provides analysis only without code changes

### 8. Patch Application

- [x] 8.1 Implement `apply_patch(patch, repo_path)` — apply AI-generated patch to cloned repo via `git apply`
- [x] 8.2 Implement structured commit — commit with message containing fingerprint ID and crash summary
- [x] 8.3 Handle patch failure — report git error output per spec
- [x] 8.4 Implement confidence level assessment — high (full context + single-function fix) vs low (partial context or multi-file)

### 9. Phase 2 CLI & Tests

- [x] 9.1 Implement `crash-fix generate-fix <fingerprint-id>` CLI command — runs Phase 1 + Phase 2 pipeline
- [x] 9.2 Add `--dry-run` flag — show generated prompt and AI response without applying patch
- [x] 9.3 Write unit tests for prompt construction
- [x] 9.4 Write unit tests for response parsing and patch extraction
- [x] 9.5 Write integration test — end-to-end Phase 2 with mock AI responses

## Phase 3: Automated Build, Test & PR Creation

### 10. Build Trigger & Monitoring

- [x] 10.1 Create `build_validator.py` — module for CI/CD build integration
- [x] 10.2 Implement `trigger_build(recipe, branch)` — push feature branch and trigger build via CI/CD API
- [x] 10.3 Implement `monitor_build(job_id)` — poll build status until success, failure, or timeout (default 4 hours)
- [x] 10.4 Implement incremental build support — attempt component-only build before full image
- [x] 10.5 Handle build failures and timeouts per spec scenarios

### 11. Device Test Execution

- [x] 11.1 Create `device_tester.py` — module for device deployment and testing
- [x] 11.2 Implement `deploy_image(device_id, image_url)` — deploy build artifact to test device with retry logic
- [x] 11.3 Implement `run_component_tests(device_id, component)` — execute component-specific test suite and collect results
- [x] 11.4 Handle no-device-available and no-tests-defined scenarios per spec
- [x] 11.5 Implement device release — always release device back to pool after test completion

### 12. Crash Regression Check

- [x] 12.1 Create `regression_checker.py` — module for crash regression monitoring
- [x] 12.2 Implement `monitor_crashes(device_id, duration)` — poll stack trace portal for new crashes from the test device during soak period (default 10 min, polling every 60s)
- [x] 12.3 Implement crash correlation — detect if new crash matches original fingerprint (fix didn't work) or is a new fingerprint (regression introduced)
- [x] 12.4 Handle portal unreachable during monitoring per spec

### 13. PR Creation

- [x] 13.1 Create `pr_creator.py` — module for GitHub PR creation
- [x] 13.2 Implement `create_pr(repo, branch, crash_context, results)` — create PR via GitHub API with structured description containing full audit trail
- [x] 13.3 Implement PR description template — fingerprint ID, crash summary, backtrace excerpt (top 10 frames), AI root cause explanation, fix description, build URL, test results, regression check result, confidence level
- [x] 13.4 Implement PR labeling — apply `auto-generated`, `crash-fix`, `fingerprint:{id}`, confidence level labels
- [x] 13.5 Implement gate logic — only create PR if build passes AND tests pass AND regression check passes
- [x] 13.6 Handle GitHub token missing per spec

### 14. Phase 3 CLI & Full Pipeline

- [x] 14.1 Implement `crash-fix auto-pr <fingerprint-id>` CLI command — runs full Phase 1 + 2 + 3 pipeline
- [x] 14.2 Add `--skip-tests` flag — create PR without device testing (build validation only)
- [x] 14.3 Add `--skip-build` flag — generate fix only without build/test/PR (for local review)
- [x] 14.4 Write unit tests for PR creator (mock GitHub API)
- [x] 14.5 Write unit tests for regression checker (mock portal responses)
- [x] 14.6 Write end-to-end integration test — full pipeline with all external services mocked
