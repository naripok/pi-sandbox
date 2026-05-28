# Delta: Per-Project Sandbox Images

## Domain: sandbox-environment (new domain — no living spec exists)

### ADDED Requirements

#### Requirement: Per-project image naming
When a `.pi-packages` file exists in the current working directory, the system SHALL derive a unique image name using the directory basename and a deterministic hash of the `.pi-packages` contents.

##### Scenario: Image name includes project name and package hash
- GIVEN a project named `myproject` with `.pi-packages` containing `cmake`
- WHEN the sandbox is launched
- THEN the image name SHALL be `pi-agent-isolated-myproject-<hash>` where `<hash>` is a deterministic suffix derived from the raw byte contents of `.pi-packages`

##### Scenario: Shared base image when no .pi-packages
- GIVEN a project without `.pi-packages`
- WHEN the sandbox is launched
- THEN the image name SHALL be `pi-agent-isolated` (the shared base)

#### Requirement: Package declaration file format
The system SHALL accept a `.pi-packages` file containing one system package name per line. Leading and trailing whitespace SHALL be stripped. Lines beginning with `#` (after stripping) are comments. Blank lines SHALL be ignored. Trailing `\r` SHALL be stripped.

##### Scenario: Simple package list
- GIVEN `.pi-packages` containing `cmake\npkgconf\n`
- WHEN the sandbox builds the image
- THEN both `cmake` and `pkgconf` SHALL be installed in the resulting image

##### Scenario: Comments are ignored
- GIVEN `.pi-packages` containing `# build tools\ncmake\n`
- WHEN the sandbox builds the image
- THEN only `cmake` SHALL be installed in the image

##### Scenario: Blank lines are ignored
- GIVEN `.pi-packages` containing `cmake\n\npkgconf\n`
- WHEN the sandbox builds the image
- THEN both `cmake` and `pkgconf` SHALL be installed in the image

##### Scenario: Comment-only file uses shared base image
- GIVEN `.pi-packages` contains only comments and blank lines
- WHEN the sandbox is launched
- THEN the system SHALL use the shared base image `pi-agent-isolated`

##### Scenario: Empty file uses shared base image
- GIVEN `.pi-packages` is an empty (0-byte) file
- WHEN the sandbox is launched
- THEN the system SHALL use the shared base image `pi-agent-isolated`

#### Requirement: User approval before rebuild
The system SHALL require explicit user approval before building a new image from `.pi-packages`.

##### Scenario: Approval prompt on first run with new packages
- GIVEN `.pi-packages` contains packages that would produce a new image name
- WHEN the sandbox is launched and the image does not exist
- THEN the system SHALL display the package list and prompt for approval before building

##### Scenario: No prompt when image already exists
- GIVEN `.pi-packages` is unchanged and the matching image already exists
- WHEN the sandbox is launched
- THEN the system SHALL NOT prompt for approval and SHALL use the existing image

##### Scenario: Prompt when .pi-packages is modified
- GIVEN a per-project image exists for the current `.pi-packages` content
- WHEN `.pi-packages` is modified (producing a different hash)
- THEN the system SHALL display the updated package list and prompt for approval before building a new image

##### Scenario: User declines approval
- GIVEN `.pi-packages` would require a rebuild
- WHEN the user declines the approval prompt
- THEN the system SHALL NOT build the image and SHALL exit with an error message

##### Scenario: Non-interactive fallback
- GIVEN `.pi-packages` would require a rebuild
- WHEN stdin is not a terminal
- THEN the system SHALL print an error message and SHALL NOT proceed with the build

#### Requirement: Input validation
The system SHALL reject `.pi-packages` files containing dangerous shell metacharacters.

##### Scenario: Shell metacharacters rejected (whole file)
- GIVEN `.pi-packages` contains a line with any of: `;`, `|`, `$`, `` ` ``, `&`, `>`, `<`, `*`, `?`, `~`, `\`, `!`
- WHEN the sandbox processes `.pi-packages`
- THEN the system SHALL reject the entire file, print an error, and SHALL NOT attempt to build

#### Requirement: Environment variable override
The `PI_AGENT_IMAGE` environment variable SHALL take precedence over all automatic image name derivation. When set, the system SHALL NOT read or validate `.pi-packages`.

##### Scenario: PI_AGENT_IMAGE overrides per-project image
- GIVEN `.pi-packages` contains `cmake` and `PI_AGENT_IMAGE` is set to `my-custom-image`
- WHEN the sandbox is launched
- THEN the system SHALL use `my-custom-image` and SHALL NOT trigger a per-project rebuild

##### Scenario: PI_AGENT_IMAGE overrides shared base image
- GIVEN `.pi-packages` does not exist and `PI_AGENT_IMAGE` is set to `my-custom-image`
- WHEN the sandbox is launched
- THEN the system SHALL use `my-custom-image`

##### Scenario: Normal derivation when PI_AGENT_IMAGE is unset
- GIVEN `PI_AGENT_IMAGE` is not set and `.pi-packages` does not exist
- WHEN the sandbox is launched
- THEN the system SHALL use `pi-agent-isolated`

#### Requirement: Build failure handling
The system SHALL report a clear error when a declared package cannot be installed during image build.

##### Scenario: Package not found during build
- GIVEN `.pi-packages` contains a non-existent package name
- WHEN the sandbox builds the image
- THEN the system SHALL print an error identifying the failing package with inspection instructions

#### Requirement: Image listing
The system SHALL provide a way to list per-project sandbox images.

##### Scenario: List images target
- GIVEN per-project images have been built
- WHEN the user runs `make images`
- THEN the system SHALL display all `pi-agent-isolated-*` images, or print nothing if none exist

#### Requirement: Agent documentation
The system SHALL document the `.pi-packages` workflow for the agent.

##### Scenario: APPEND_SYSTEM.md contains .pi-packages reference
- GIVEN the agent reads `APPEND_SYSTEM.md`
- WHEN the agent encounters a need for system packages
- THEN `APPEND_SYSTEM.md` SHALL contain the text `.pi-packages` and describe the user approval step
