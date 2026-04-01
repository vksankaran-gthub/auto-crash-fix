## ADDED Requirements

### Requirement: Map crashing component to Yocto recipe
The system SHALL use `oe-pkgdata-util` to determine which Yocto recipe packages the crashing component (library, executable, or script file).

#### Scenario: Binary maps to a known recipe
- **WHEN** the crashing component name (e.g., `libwpe-1.0.so`) is provided
- **THEN** the system SHALL run `oe-pkgdata-util find-path` to identify the package, then `oe-pkgdata-util lookup-recipe` to identify the recipe name

#### Scenario: Binary not found in package data
- **WHEN** `oe-pkgdata-util` cannot find a package containing the crashing component
- **THEN** the system SHALL report "Could not map component '{name}' to a Yocto recipe" and exit with a non-zero return code

### Requirement: Extract source repository from recipe
The system SHALL use `bitbake -e <recipe>` to extract the `SRC_URI`, `SRCREV`, and `S` (source directory) variables from the recipe environment, identifying the upstream git repository and commit hash.

#### Scenario: Recipe has a git SRC_URI
- **WHEN** the recipe's `SRC_URI` contains a `git://` or `https://` git URL
- **THEN** the system SHALL extract the repository URL, branch (if specified), and `SRCREV` (commit hash)

#### Scenario: Recipe uses a tarball source
- **WHEN** the recipe's `SRC_URI` points to a tarball (non-git source)
- **THEN** the system SHALL report "Recipe '{name}' uses non-git source — manual investigation required" and exit with a non-zero return code

#### Scenario: Bitbake environment not available
- **WHEN** the `bitbake` command is not available in the current environment
- **THEN** the system SHALL report "Bitbake not found — run this tool from a configured Yocto build environment" and exit with a non-zero return code

### Requirement: Clone or access source repository
The system SHALL clone (or use an existing checkout of) the source repository at the specific `SRCREV` commit so that source files can be examined.

#### Scenario: Repository cloned successfully
- **WHEN** the git repository URL and SRCREV are known
- **THEN** the system SHALL clone the repository to a temporary working directory and checkout the exact SRCREV commit

#### Scenario: Repository already cached locally
- **WHEN** a local clone of the repository already exists in the tool's cache directory
- **THEN** the system SHALL fetch updates and checkout the correct SRCREV without a full re-clone
