# Spec: Resource Limits

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: CPU limit
The system SHALL limit the container to 4 CPU cores.

##### Scenario: CPU limit flag is passed to podman
- GIVEN the sandbox is launched
- WHEN podman run is invoked
- THEN the command SHALL include `--cpus 4`

#### Requirement: Memory limit
The system SHALL limit the container to 8 GB of memory.

##### Scenario: Memory limit flag is passed to podman
- GIVEN the sandbox is launched
- WHEN podman run is invoked
- THEN the command SHALL include `--memory 8g`

#### Requirement: PID limit
The system SHALL limit the container to 1024 processes.

##### Scenario: PID limit flag is passed to podman
- GIVEN the sandbox is launched
- WHEN podman run is invoked
- THEN the command SHALL include `--pids-limit 1024`
