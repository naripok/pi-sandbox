# Delta: Security Hardening

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: Read-only root filesystem
The system SHALL mount the container's root filesystem as read-only. All paths outside of explicit writable mounts (`/workspace`, `/home/pi`, `/tmp`) SHALL be immutable.

##### Scenario: Cannot write to system directories
- GIVEN the container is running
- WHEN the user attempts to create a file in `/etc/`
- THEN the write SHALL fail

##### Scenario: Cannot modify installed binaries
- GIVEN the container is running
- WHEN the user attempts to overwrite `/usr/bin/ls`
- THEN the write SHALL fail

##### Scenario: Cannot install system packages
- GIVEN the container is running
- WHEN the user runs `pacman -S <package>`
- THEN the command SHALL fail (rootfs is read-only)

#### Requirement: All capabilities dropped
The system SHALL drop all Linux capabilities from the container process. The effective capability set (CapEff) SHALL be empty.

##### Scenario: No effective capabilities
- GIVEN the container is running
- WHEN inspecting CapEff from `/proc/self/status`
- THEN the value SHALL be `0000000000000000`

##### Scenario: Cannot perform privileged operations requiring capabilities
- GIVEN the container is running with no capabilities
- WHEN the user attempts an operation requiring a capability (e.g., binding to a port below 1024)
- THEN the operation SHALL fail

#### Requirement: No-new-privileges enforced
The system SHALL enforce the `no-new-privileges` security option on the container process. The kernel SHALL prevent any privilege escalation via setuid, setgid, or file capabilities.

##### Scenario: NoNewPrivs flag is set
- GIVEN the container is running
- WHEN inspecting NoNewPrivs from `/proc/self/status`
- THEN the value SHALL be `1`

##### Scenario: Setuid binaries cannot escalate privileges
- GIVEN a setuid root binary exists in the container
- WHEN the `pi` user executes it
- THEN the process SHALL NOT gain root privileges (NoNewPrivs blocks escalation)

#### Requirement: No setuid/setgid binaries in the image
The system SHALL strip setuid and setgid permission bits from all files in the container image at build time.

##### Scenario: No setuid binaries present
- GIVEN the container image is built
- WHEN searching the filesystem for files with the setuid bit (`-perm -4000`)
- THEN no such files SHALL exist

##### Scenario: No setgid binaries present
- GIVEN the container image is built
- WHEN searching the filesystem for files with the setgid bit (`-perm -2000`)
- THEN no such files SHALL exist

#### Requirement: Writable /tmp via tmpfs
The system SHALL provide a writable `/tmp` directory via a tmpfs mount. This directory SHALL be ephemeral — contents are lost when the container exits.

##### Scenario: /tmp is writable
- GIVEN the container is running
- WHEN the user creates a file in `/tmp/`
- THEN the write SHALL succeed

##### Scenario: /tmp is ephemeral
- GIVEN a file exists in `/tmp/` in one container run
- WHEN a new container run starts
- THEN the file SHALL NOT exist (tmpfs is recreated fresh)

#### Requirement: User namespace isolation
The system SHALL run the container with `--userns=keep-id` so that the container user's UID/GID map to the host user. A full container escape yields only the host user's unprivileged permissions.

##### Scenario: Container runs as non-root user
- GIVEN the container is running
- WHEN checking the effective user
- THEN it SHALL be `pi` (UID 1000), not root

##### Scenario: Escape yields only unprivileged host access
- GIVEN the container is running with `--userns=keep-id`
- WHEN a hypothetical container escape occurs
- THEN the escaping process SHALL have the host user's unprivileged permissions (not root)

#### Requirement: PID namespace isolation
The system SHALL run the container in a separate PID namespace. Processes inside the container SHALL NOT be able to observe host processes.

##### Scenario: Cannot see host processes
- GIVEN the container is running
- WHEN listing processes (e.g., `ps` or reading `/proc`)
- THEN only container-local processes SHALL be visible

##### Scenario: PID 1 is the container init, not host init
- GIVEN the container is running
- WHEN inspecting `/proc/1/cmdline`
- THEN PID 1 SHALL be the container's entrypoint or user command, not a host process (e.g., `systemd`)

#### Requirement: Container runtime socket not accessible
The system SHALL NOT mount Docker or Podman runtime sockets into the container. The agent SHALL be unable to control the container runtime from inside the container.

##### Scenario: Docker socket not present
- GIVEN the container is running
- WHEN checking for `/var/run/docker.sock`
- THEN the file SHALL NOT exist

##### Scenario: Podman socket not present
- GIVEN the container is running
- WHEN checking for `/var/run/podman/podman.sock`
- THEN the file SHALL NOT exist
