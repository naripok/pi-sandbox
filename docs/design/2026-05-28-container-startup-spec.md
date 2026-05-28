# Spec: Container Startup

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: Workspace mount
The system SHALL mount the current working directory (the project root) at `/workspace` inside the container with read-write access.

##### Scenario: Current directory is mounted at /workspace
- GIVEN the sandbox is launched from `/home/user/myproject`
- WHEN podman run is invoked
- THEN the command SHALL include `-v /home/user/myproject:/workspace`

##### Scenario: /workspace is read-write
- GIVEN the container is running
- WHEN the user creates or modifies a file in `/workspace/`
- THEN the operation SHALL succeed

#### Requirement: Container naming
The system SHALL assign the container a name derived from the project directory basename and a random suffix.

##### Scenario: Container name includes project name
- GIVEN the sandbox is launched from `/home/user/myproject`
- WHEN podman run is invoked
- THEN the `--name` flag SHALL contain `pi-agent-myproject`

#### Requirement: TTY allocation
The system SHALL allocate a TTY for the container only when stdin is a terminal. Non-interactive runs (pipes, scripts) SHALL NOT allocate a TTY.

##### Scenario: TTY allocated for interactive runs
- GIVEN stdin is a terminal
- WHEN podman run is invoked
- THEN the command SHALL include the `-t` flag

##### Scenario: No TTY for non-interactive runs
- GIVEN stdin is not a terminal (e.g., piped input)
- WHEN podman run is invoked
- THEN the command SHALL NOT include the `-t` flag

#### Requirement: npm lifecycle scripts disabled
The system SHALL disable npm lifecycle scripts (`postinstall`, `preinstall`, etc.) by default to prevent arbitrary code execution from compromised packages.

##### Scenario: ignore-scripts is set to true
- GIVEN the container is running
- WHEN checking npm configuration (`npm config get ignore-scripts`)
- THEN the value SHALL be `true`

#### Requirement: Agent offline mode
The system SHALL set `PI_OFFLINE=1` in the container to prevent the agent from making network calls outside the sandbox.

##### Scenario: PI_OFFLINE is set
- GIVEN the container is running
- WHEN checking the `PI_OFFLINE` environment variable
- THEN it SHALL be set to `1`

#### Requirement: Agent telemetry disabled
The system SHALL set `PI_TELEMETRY=0` in the container to disable telemetry from the sandbox agent.

##### Scenario: PI_TELEMETRY is set
- GIVEN the container is running
- WHEN checking the `PI_TELEMETRY` environment variable
- THEN it SHALL be set to `0`

#### Requirement: APPEND_SYSTEM.md injection
The system SHALL copy `APPEND_SYSTEM.md` from the workspace into the persistent volume so the agent can auto-inject the sandbox environment reference into its system prompt.

##### Scenario: APPEND_SYSTEM.md is copied on startup
- GIVEN `config/APPEND_SYSTEM.md` exists in the workspace
- WHEN the container starts
- THEN the file SHALL be present at `/home/pi/.pi-agent-data/APPEND_SYSTEM.md`
