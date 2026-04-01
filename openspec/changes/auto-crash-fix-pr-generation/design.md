## Context

RDK crash analysis currently involves a manual workflow: engineers receive crash reports, look up fingerprints in the stack trace portal, manually trace crashing components through Yocto layer metadata to source repositories, analyze backtraces, author fixes, build, test, and raise PRs. This multi-step process spans multiple tools (stack trace portal, bitbake, git, build systems, device labs) and requires deep domain knowledge at each step.

The stack trace portal stores crash fingerprints with associated metadata — build version, minidump details, crashing binary/library/script name, and full backtraces. Yocto/bitbake provides the mapping from packaged binaries to recipes and their upstream source repositories. The CI/CD system handles builds and device test deployments.

Stakeholders: RDK engineering teams, release management, QA/test teams, DevOps/CI teams.

## Goals / Non-Goals

**Goals:**
- Automate the end-to-end pipeline from crash fingerprint to validated Pull Request
- Deliver in phases, with each phase independently useful
- Phase 1: Crash data retrieval and component tracing (foundation)
- Phase 2: AI-assisted fix generation with human review
- Phase 3: Automated build, test, and PR creation (full automation)
- Support both native crashes (C/C++ libraries, executables) and script-level crashes
- Produce audit trail linking every PR back to the originating crash fingerprint

**Non-Goals:**
- Replacing human code review — the PR is the review gate, not the final approval
- Handling all crash types automatically — some crashes require architectural changes beyond what AI can propose
- Building a new stack trace portal — we consume the existing portal's API
- Modifying the Yocto build system itself — we use bitbake as a read-only query tool

## Decisions

### 1. Phased implementation approach

**Decision**: Implement in three distinct phases, each delivering standalone value:

```
Phase 1: Data Pipeline          Phase 2: AI Fix Gen          Phase 3: Full Automation
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│ Fingerprint Input   │     │ Source code fetch     │     │ Build trigger         │
│ ↓                   │     │ ↓                     │     │ ↓                     │
│ Portal API query    │     │ Copilot AI prompt     │     │ Build validation      │
│ ↓                   │     │ construction          │     │ ↓                     │
│ Crash metadata      │     │ ↓                     │     │ Device deployment     │
│ extraction          │     │ Fix generation        │     │ ↓                     │
│ ↓                   │     │ ↓                     │     │ Test execution        │
│ Yocto recipe trace  │     │ Patch creation        │     │ ↓                     │
│ ↓                   │     │ ↓                     │     │ Crash regression      │
│ Repo identification │     │ Human review gate     │     │ check                 │
│ ↓                   │     │                       │     │ ↓                     │
│ Backtrace retrieval │     │                       │     │ PR creation           │
│ ↓                   │     │                       │     │                       │
│ Structured report   │     │                       │     │                       │
└─────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

**Rationale**: Each phase is independently useful. Phase 1 alone saves hours of manual tracing. Phase 2 adds AI assistance but keeps humans in the loop. Phase 3 completes full automation. If AI fix quality is insufficient, Phase 1+2 still provide value as a triage accelerator.

### 2. CLI-based tool architecture

**Decision**: Build as a CLI tool (Python) that can be run locally or in CI/CD pipelines.

**Rationale**: Aligns with existing RDK tooling patterns. CLI is composable — each phase is a subcommand that can be called independently or chained. Python provides excellent library support for API clients, bitbake interaction, and git operations.

**Alternatives considered**:
- Web service: Rejected for Phase 1 — adds deployment complexity. Can be added later as a wrapper.
- Shell scripts: Rejected — insufficient error handling and structure for a multi-phase tool.

### 3. Stack trace portal integration via REST API

**Decision**: Consume the stack trace portal's existing REST API to fetch fingerprint data, minidump info, and backtraces.

**Rationale**: Non-invasive integration. No changes needed to the portal. API provides structured data that's easier to parse than scraping.

**Alternatives considered**:
- Direct database access: Rejected — tighter coupling, security concerns, requires DB credentials.
- Scraping portal UI: Rejected — fragile, breaks with UI changes.

### 4. Yocto recipe tracing via bitbake queries

**Decision**: Use `bitbake -e <recipe>` and OE layer metadata to map a binary/library name to its source recipe and git repository. The tool will parse the bitbake environment output for `SRC_URI`, `S` (source directory), and `SRCREV` variables.

```
Binary name (e.g., "libwpe-1.0.so")
        ↓
oe-pkgdata-util: find which recipe packages it
        ↓
Recipe name (e.g., "wpeframework")
        ↓
bitbake -e <recipe>: extract SRC_URI, SRCREV
        ↓
Git repository URL + commit hash
```

**Rationale**: `oe-pkgdata-util` is the standard OE/Yocto tool for mapping files to recipes. `bitbake -e` provides the full recipe environment including source location. Both are read-only operations.

**Alternatives considered**:
- Manual recipe database: Rejected — stale quickly, maintenance burden.
- Layer index API: Partial coverage only, doesn't include custom RDK layers.

### 5. AI fix generation via Copilot API with structured prompts

**Decision**: Construct a structured prompt containing: (a) the backtrace, (b) the relevant source file(s) around the crash site, (c) the component context, and (d) the crash type. Send to GitHub Copilot API. Apply the generated fix as a git patch.

**Prompt structure**:
```
Context: {component name, repository, build version}
Crash type: {segfault / abort / exception / ...}
Backtrace:
  {full backtrace from portal}
Source code around crash site:
  {extracted source files}
Task: Provide a minimal fix for this crash. Explain the root cause.
```

**Rationale**: Structured prompts with real crash context produce better fixes than generic prompts. Including the backtrace and source code gives the AI sufficient context.

**Alternatives considered**:
- Local LLM: Rejected for now — Copilot API is already available and integrated with GitHub.
- Multiple AI passes (generate + review): Possible future improvement, not needed for Phase 2 MVP.

### 6. Build and test validation via existing CI/CD

**Decision**: Trigger builds through the existing CI/CD system (Concourse/Jenkins) via API. Deploy successful builds to a test device from the device pool. Run component-specific tests using existing test frameworks.

**Rationale**: Reuses existing infrastructure. No new build system needed. Test device pool is already managed.

### 7. PR creation with full audit trail

**Decision**: Use GitHub API to create a PR with a structured description containing: originating fingerprint ID, crash summary, backtrace excerpt, AI-generated fix explanation, build result, test results.

**Rationale**: Full traceability from crash to fix. Reviewers have all context in the PR itself. The PR serves as the human review gate before merge.

## Risks / Trade-offs

- **[AI fix quality]** → The AI may generate incorrect or incomplete fixes. Mitigation: Phase 2 includes a mandatory human review gate. Track fix acceptance rate to improve prompts over time. Never auto-merge — PR is always the review point.
- **[Stack trace portal API availability]** → API may not exist or may be undocumented. Mitigation: Phase 1 starts with API discovery; if no API, fall back to structured export files.
- **[Bitbake environment requirement]** → Tracing recipes requires a configured Yocto build environment. Mitigation: Run the tool on build servers where bitbake is already configured. Cache recipe-to-repo mappings for offline use.
- **[Build time]** → Full builds can take hours. Mitigation: Use incremental builds where possible. In Phase 3, only build the affected component.
- **[Test device availability]** → Device pool may be busy. Mitigation: Queue mechanism with timeout. Allow skipping device test with manual override flag.
- **[Security — AI-generated code]** → AI-generated patches could introduce vulnerabilities. Mitigation: PR review is mandatory. Future: add automated security scanning (SAST) to the validation pipeline.
- **[Crash types beyond AI capability]** → Some crashes (race conditions, memory corruption at scale) require deep analysis beyond AI capability. Mitigation: The tool reports confidence level; low-confidence fixes are flagged for manual analysis.

## Open Questions

1. What is the exact REST API interface for the stack trace portal? Is there API documentation available, or do we need to reverse-engineer from the portal UI?
2. Which CI/CD system (Concourse, Jenkins, other) should the Phase 3 build trigger target first?
3. What is the test device pool management API? How do we reserve a device and deploy a build?
4. Should the tool support multi-component crashes (backtrace spans multiple libraries)?
5. What is the acceptable turnaround time target for the full pipeline (fingerprint → PR)?
