# Sandbox Environment

## Purpose

Defines the behavioral requirements for the pi-coding-agent sandbox environment, including container image management, per-project system dependencies, and security boundaries.

## Requirements

### Requirement: Per-project image naming
When a `.pi-packages` file exists in the current working directory, the system SHALL derive a unique image name using the directory basename and a deterministic hash of the `.pi-packages` contents.

#### Scenario: Image name includes project name and package hash
- GIVEN a project named `myproject` with `.pi-packages` containing `cmake`
- WHEN the sandbox is launched
- THEN the image name SHALL be `pi-agent-isolated-myproject-<hash>` where `<hash>` is a deterministic suffix derived from the raw byte contents of `.pi-packages`

#### Scenario: Shared base image when no .pi-packages
- GIVEN a project without `.pi-packages`
- WHEN the sandbox is launched
- THEN the image name SHALL be `pi-agent-isolated` (the shared base)

### Requirement: Package declaration file format
The system SHALL accept a `.pi-packages` file containing one system package name per line. Leading and trailing whitespace SHALL be stripped. Lines beginning with `#` (after stripping) are comments. Blank lines SHALL be ignored. Trailing `\r` SHALL be stripped.

#### Scenario: Simple package list
- GIVEN `.pi-packages` containing `cmake\npkgconf\n`
- WHEN the sandbox builds the image
- THEN both `cmake` and `pkgconf` SHALL be installed in the resulting image

#### Scenario: Comments are ignored
- GIVEN `.pi-packages` containing `# build tools\ncmake\n`
- WHEN the sandbox builds the image
- THEN only `cmake` SHALL be installed in the image

#### Scenario: Blank lines are ignored
- GIVEN `.pi-packages` containing `cmake\n\npkgconf\n`
- WHEN the sandbox builds the image
- THEN both `cmake` and `pkgconf` SHALL be installed in the image

#### Scenario: Comment-only file uses shared base image
- GIVEN `.pi-packages` contains only comments and blank lines
- WHEN the sandbox is launched
- THEN the system SHALL use the shared base image `pi-agent-isolated`

#### Scenario: Empty file uses shared base image
- GIVEN `.pi-packages` is an empty (0-byte) file
- WHEN the sandbox is launched
- THEN the system SHALL use the shared base image `pi-agent-isolated`

### Requirement: User approval before rebuild
The system SHALL require explicit user approval before building a new image from `.pi-packages`.

#### Scenario: Approval prompt on first run with new packages
- GIVEN `.pi-packages` contains packages that would produce a new image name
- WHEN the sandbox is launched and the image does not exist
- THEN the system SHALL display the package list and prompt for approval before building

#### Scenario: No prompt when image already exists
- GIVEN `.pi-packages` is unchanged and the matching image already exists
- WHEN the sandbox is launched
- THEN the system SHALL NOT prompt for approval and SHALL use the existing image

#### Scenario: Prompt when .pi-packages is modified
- GIVEN a per-project image exists for the current `.pi-packages` content
- WHEN `.pi-packages` is modified (producing a different hash)
- THEN the system SHALL display the updated package list and prompt for approval before building a new image

#### Scenario: User declines approval
- GIVEN `.pi-packages` would require a rebuild
- WHEN the user declines the approval prompt
- THEN the system SHALL NOT build the image and SHALL exit with an error message

#### Scenario: Non-interactive fallback
- GIVEN `.pi-packages` would require a rebuild
- WHEN stdin is not a terminal
- THEN the system SHALL print an error message and SHALL NOT proceed with the build

### Requirement: Input validation
The system SHALL reject `.pi-packages` files containing dangerous shell metacharacters.

#### Scenario: Shell metacharacters rejected (whole file)
- GIVEN `.pi-packages` contains a line with any of: `;`, `|`, `$`, `` ` ``, `&`, `>`, `<`, `*`, `?`, `~`, `\`, `!`
- WHEN the sandbox processes `.pi-packages`
- THEN the system SHALL reject the entire file, print an error, and SHALL NOT attempt to build

### Requirement: Environment variable override
The `PI_AGENT_IMAGE` environment variable SHALL take precedence over all automatic image name derivation. When set, the system SHALL NOT read or validate `.pi-packages`.

#### Scenario: PI_AGENT_IMAGE overrides per-project image
- GIVEN `.pi-packages` contains `cmake` and `PI_AGENT_IMAGE` is set to `my-custom-image`
- WHEN the sandbox is launched
- THEN the system SHALL use `my-custom-image` and SHALL NOT trigger a per-project rebuild

#### Scenario: PI_AGENT_IMAGE overrides shared base image
- GIVEN `.pi-packages` does not exist and `PI_AGENT_IMAGE` is set to `my-custom-image`
- WHEN the sandbox is launched
- THEN the system SHALL use `my-custom-image`

#### Scenario: Normal derivation when PI_AGENT_IMAGE is unset
- GIVEN `PI_AGENT_IMAGE` is not set and `.pi-packages` does not exist
- WHEN the sandbox is launched
- THEN the system SHALL use `pi-agent-isolated`

### Requirement: Build failure handling
The system SHALL report a clear error when a declared package cannot be installed during image build.

#### Scenario: Package not found during build
- GIVEN `.pi-packages` contains a non-existent package name
- WHEN the sandbox builds the image
- THEN the system SHALL print an error identifying the failing package with inspection instructions

### Requirement: Image listing
The system SHALL provide a way to list per-project sandbox images.

#### Scenario: List images target
- GIVEN per-project images have been built
- WHEN the user runs `make images`
- THEN the system SHALL display all `pi-agent-isolated-*` images, or print nothing if none exist

### Requirement: Agent documentation
The system SHALL document the `.pi-packages` workflow for the agent.

#### Scenario: APPEND_SYSTEM.md contains .pi-packages reference
- GIVEN the agent reads `APPEND_SYSTEM.md`
- WHEN the agent encounters a need for system packages
- THEN `APPEND_SYSTEM.md` SHALL contain the text `.pi-packages` and describe the user approval step

### Requirement: Persistent volume per project
The system SHALL create a per-project persistent podman volume that survives across container runs. Data written to the volume inside the container SHALL be available in subsequent runs of the same project's container.

#### Scenario: Data persists across container runs
- GIVEN a container run writes a file to `/home/pi/.local/marker.txt`
- WHEN a subsequent container run for the same project starts
- THEN the file SHALL still exist with the same content

#### Scenario: Volume is podman-managed (not a host bind mount)
- GIVEN the persistent volume is created
- WHEN inspecting the volume with `podman volume ls`
- THEN the volume SHALL appear as a podman-managed volume (not a bind mount to the host filesystem)

### Requirement: Volume name derived from project path
The system SHALL derive the persistent volume name from the current working directory path using the directory basename and a deterministic hash of the full path.

#### Scenario: Volume name includes project name and path hash
- GIVEN a project at `/home/user/myproject`
- WHEN the sandbox is launched
- THEN the volume name SHALL be `pi-agent-persist-myproject-<hash>` where `<hash>` is the first 8 hex characters of the SHA-256 of the resolved project path

#### Scenario: Volume creation is idempotent
- GIVEN the persistent volume already exists
- WHEN the sandbox is launched
- THEN the system SHALL NOT error and SHALL reuse the existing volume

### Requirement: Volume mounted at /home/pi
The system SHALL mount the persistent volume at `/home/pi` with the `:U` ownership flag.

#### Scenario: /home/pi is writable
- GIVEN the container is running
- WHEN the user writes to `/home/pi/.local/test.txt`
- THEN the write SHALL succeed

#### Scenario: /home/pi is owned by the pi user
- GIVEN the container is running
- WHEN checking ownership of `/home/pi`
- THEN the owner SHALL be the `pi` user (UID 1000)

### Requirement: Config sync on every start
The system SHALL sync host config from `/pi-source` into the persistent volume on every container start, propagating new and modified files while preserving user-generated data.

#### Scenario: New config files are synced
- GIVEN a new file is added to the host config directory (`~/.pi/agent/skills/new-skill.md`)
- WHEN the container starts
- THEN the file SHALL be present at `/home/pi/.pi-agent-data/skills/new-skill.md`

#### Scenario: Modified config files are synced
- GIVEN a config file on the host is modified
- WHEN the container starts
- THEN the updated content SHALL be present in the persistent volume

#### Scenario: Sessions are preserved during sync
- GIVEN a session file exists at `/home/pi/.pi-agent-data/sessions/test.json`
- WHEN the container starts and config sync runs
- THEN the session file SHALL still exist with the same content

#### Scenario: Lock files are preserved during sync
- GIVEN a lock file exists at `/home/pi/.pi-agent-data/some-file.lock`
- WHEN the container starts and config sync runs
- THEN the lock file SHALL still exist

#### Scenario: Files deleted from host are not removed from volume
- GIVEN a config file exists in the volume but is deleted from the host
- WHEN the container starts
- THEN the file SHALL still exist in the volume

### Requirement: First-run package manager configuration
The system SHALL configure package managers for user-level installs on the first run of a persistent volume.

#### Scenario: npm global installs go to .local
- GIVEN a fresh persistent volume (first run)
- WHEN the container starts
- THEN `npm config get prefix` SHALL return `/home/pi/.local`

#### Scenario: pip installs go to .local
- GIVEN a fresh persistent volume (first run)
- WHEN the container starts
- THEN `PYTHONUSERBASE` SHALL be set to `/home/pi/.local`

#### Scenario: First-run setup is not repeated on subsequent runs
- GIVEN a persistent volume that has already been initialized
- WHEN the container starts again
- THEN the package manager configuration SHALL NOT be re-initialized (existing config preserved)

### Requirement: Host config mounted read-only at /pi-source
The system SHALL mount the host config directory (`~/.pi/agent`) read-only at `/pi-source`.

#### Scenario: /pi-source is read-only
- GIVEN the container is running
- WHEN the user attempts to write to `/pi-source`
- THEN the write SHALL fail

#### Scenario: /pi-source contains host config
- GIVEN the host config directory contains files
- WHEN the container starts
- THEN the files SHALL be accessible at `/pi-source`

### Requirement: Reset mechanism
The system SHALL provide a `--reset` flag that removes the project's persistent volume.

#### Scenario: --reset removes the volume
- GIVEN a persistent volume exists for the current project
- WHEN `run.sh --reset` is executed
- THEN the volume SHALL be removed and the script SHALL exit with code 0

#### Scenario: --reset is safe when volume does not exist
- GIVEN no persistent volume exists for the current project
- WHEN `run.sh --reset` is executed
- THEN the script SHALL exit with code 0 (no error)

### Requirement: Volume isolation between projects
The system SHALL ensure that different projects have isolated persistent volumes. Data written in one project's volume SHALL NOT be accessible from another project's container.

#### Scenario: Project A data not visible from project B
- GIVEN project A writes data to its persistent volume
- WHEN project B's container starts
- THEN project B SHALL NOT see project A's data

### Requirement: Entrypoint script
The system SHALL use an entrypoint script to perform container initialization before exec-ing the user command.

#### Scenario: Entrypoint runs before user command
- GIVEN the container starts with command `echo hello`
- WHEN the container runs
- THEN the entrypoint SHALL execute config sync and setup before `echo hello` runs

#### Scenario: Entrypoint exports PI_CODING_AGENT_DIR
- GIVEN the container is running
- WHEN checking the `PI_CODING_AGENT_DIR` environment variable
- THEN it SHALL be set to `/home/pi/.pi-agent-data`

### Requirement: Shell configuration in .bashrc
The system SHALL configure the shell environment in `.bashrc` to support persistent volume paths.

#### Scenario: PATH includes .local/bin
- GIVEN the shell starts in the container
- WHEN checking `$PATH`
- THEN it SHALL include `$HOME/.local/bin`

#### Scenario: PYTHONUSERBASE is set
- GIVEN the shell starts in the container
- WHEN checking `$PYTHONUSERBASE`
- THEN it SHALL be set to `$HOME/.local`

#### Scenario: NPM_CONFIG_PREFIX is set
- GIVEN the shell starts in the container
- WHEN checking `$NPM_CONFIG_PREFIX`
- THEN it SHALL be set to `$HOME/.local`

### Requirement: Read-only root filesystem
The system SHALL mount the container's root filesystem as read-only. All paths outside of explicit writable mounts (`/workspace`, `/home/pi`, `/tmp`) SHALL be immutable.

#### Scenario: Cannot write to system directories
- GIVEN the container is running
- WHEN the user attempts to create a file in `/etc/`
- THEN the write SHALL fail

#### Scenario: Cannot modify installed binaries
- GIVEN the container is running
- WHEN the user attempts to overwrite `/usr/bin/ls`
- THEN the write SHALL fail

#### Scenario: Cannot install system packages
- GIVEN the container is running
- WHEN the user runs `pacman -S <package>`
- THEN the command SHALL fail (rootfs is read-only)

### Requirement: All capabilities dropped
The system SHALL drop all Linux capabilities from the container process. The effective capability set (CapEff) SHALL be empty.

#### Scenario: No effective capabilities
- GIVEN the container is running
- WHEN inspecting CapEff from `/proc/self/status`
- THEN the value SHALL be `0000000000000000`

#### Scenario: Cannot perform privileged operations requiring capabilities
- GIVEN the container is running with no capabilities
- WHEN the user attempts an operation requiring a capability (e.g., binding to a port below 1024)
- THEN the operation SHALL fail

### Requirement: No-new-privileges enforced
The system SHALL enforce the `no-new-privileges` security option on the container process. The kernel SHALL prevent any privilege escalation via setuid, setgid, or file capabilities.

#### Scenario: NoNewPrivs flag is set
- GIVEN the container is running
- WHEN inspecting NoNewPrivs from `/proc/self/status`
- THEN the value SHALL be `1`

#### Scenario: Setuid binaries cannot escalate privileges
- GIVEN a setuid root binary exists in the container
- WHEN the `pi` user executes it
- THEN the process SHALL NOT gain root privileges (NoNewPrivs blocks escalation)

### Requirement: No setuid/setgid binaries in the image
The system SHALL strip setuid and setgid permission bits from all files in the container image at build time.

#### Scenario: No setuid binaries present
- GIVEN the container image is built
- WHEN searching the filesystem for files with the setuid bit (`-perm -4000`)
- THEN no such files SHALL exist

#### Scenario: No setgid binaries present
- GIVEN the container image is built
- WHEN searching the filesystem for files with the setgid bit (`-perm -2000`)
- THEN no such files SHALL exist

### Requirement: Writable /tmp via tmpfs
The system SHALL provide a writable `/tmp` directory via a tmpfs mount. This directory SHALL be ephemeral — contents are lost when the container exits.

#### Scenario: /tmp is writable
- GIVEN the container is running
- WHEN the user creates a file in `/tmp/`
- THEN the write SHALL succeed

#### Scenario: /tmp is ephemeral
- GIVEN a file exists in `/tmp/` in one container run
- WHEN a new container run starts
- THEN the file SHALL NOT exist (tmpfs is recreated fresh)

### Requirement: User namespace isolation
The system SHALL run the container with `--userns=keep-id` so that the container user's UID/GID map to the host user. A full container escape yields only the host user's unprivileged permissions.

#### Scenario: Container runs as non-root user
- GIVEN the container is running
- WHEN checking the effective user
- THEN it SHALL be `pi` (UID 1000), not root

#### Scenario: Escape yields only unprivileged host access
- GIVEN the container is running with `--userns=keep-id`
- WHEN a hypothetical container escape occurs
- THEN the escaping process SHALL have the host user's unprivileged permissions (not root)

### Requirement: PID namespace isolation
The system SHALL run the container in a separate PID namespace. Processes inside the container SHALL NOT be able to observe host processes.

#### Scenario: Cannot see host processes
- GIVEN the container is running
- WHEN listing processes (e.g., `ps` or reading `/proc`)
- THEN only container-local processes SHALL be visible

#### Scenario: PID 1 is the container init, not host init
- GIVEN the container is running
- WHEN inspecting `/proc/1/cmdline`
- THEN PID 1 SHALL be the container's entrypoint or user command, not a host process (e.g., `systemd`)

### Requirement: Container runtime socket not accessible
The system SHALL NOT mount Docker or Podman runtime sockets into the container. The agent SHALL be unable to control the container runtime from inside the container.

#### Scenario: Docker socket not present
- GIVEN the container is running
- WHEN checking for `/var/run/docker.sock`
- THEN the file SHALL NOT exist

#### Scenario: Podman socket not present
- GIVEN the container is running
- WHEN checking for `/var/run/podman/podman.sock`
- THEN the file SHALL NOT exist

### Requirement: Makefile targets
The system SHALL provide Makefile targets for volume management.

#### Scenario: make volumes lists persistent volumes
- GIVEN persistent volumes exist
- WHEN the user runs `make volumes`
- THEN the system SHALL display all `pi-agent-persist-*` volumes

#### Scenario: make reset resets persistent state
- GIVEN a persistent volume exists
- WHEN the user runs `make reset`
- THEN the system SHALL remove the volume (equivalent to `./run.sh --reset`)
