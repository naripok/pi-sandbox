# Delta: Persistent Per-Project Volume

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: Persistent volume per project
The system SHALL create a per-project persistent podman volume that survives across container runs. Data written to the volume inside the container SHALL be available in subsequent runs of the same project's container.

##### Scenario: Data persists across container runs
- GIVEN a container run writes a file to `/home/pi/.local/marker.txt`
- WHEN a subsequent container run for the same project starts
- THEN the file SHALL still exist with the same content

##### Scenario: Volume is podman-managed (not a host bind mount)
- GIVEN the persistent volume is created
- WHEN inspecting the volume with `podman volume ls`
- THEN the volume SHALL appear as a podman-managed volume (not a bind mount to the host filesystem)

#### Requirement: Volume name derived from project path
The system SHALL derive the persistent volume name from the current working directory path using the directory basename and a deterministic hash of the full path.

##### Scenario: Volume name includes project name and path hash
- GIVEN a project at `/home/user/myproject`
- WHEN the sandbox is launched
- THEN the volume name SHALL be `pi-agent-persist-myproject-<hash>` where `<hash>` is the first 8 hex characters of the SHA-256 of the resolved project path

##### Scenario: Volume creation is idempotent
- GIVEN the persistent volume already exists
- WHEN the sandbox is launched
- THEN the system SHALL NOT error and SHALL reuse the existing volume

#### Requirement: Volume mounted at /home/pi
The system SHALL mount the persistent volume at `/home/pi` with the `:U` ownership flag.

##### Scenario: /home/pi is writable
- GIVEN the container is running
- WHEN the user writes to `/home/pi/.local/test.txt`
- THEN the write SHALL succeed

##### Scenario: /home/pi is owned by the pi user
- GIVEN the container is running
- WHEN checking ownership of `/home/pi`
- THEN the owner SHALL be the `pi` user (UID 1000)

#### Requirement: Config sync on every start
The system SHALL sync host config from `/pi-source` into the persistent volume on every container start, propagating new and modified files while preserving user-generated data.

##### Scenario: New config files are synced
- GIVEN a new file is added to the host config directory (`~/.pi/agent/skills/new-skill.md`)
- WHEN the container starts
- THEN the file SHALL be present at `/home/pi/.pi-agent-data/skills/new-skill.md`

##### Scenario: Modified config files are synced
- GIVEN a config file on the host is modified
- WHEN the container starts
- THEN the updated content SHALL be present in the persistent volume

##### Scenario: Sessions are preserved during sync
- GIVEN a session file exists at `/home/pi/.pi-agent-data/sessions/test.json`
- WHEN the container starts and config sync runs
- THEN the session file SHALL still exist with the same content

##### Scenario: Lock files are preserved during sync
- GIVEN a lock file exists at `/home/pi/.pi-agent-data/some-file.lock`
- WHEN the container starts and config sync runs
- THEN the lock file SHALL still exist

##### Scenario: Files deleted from host are not removed from volume
- GIVEN a config file exists in the volume but is deleted from the host
- WHEN the container starts
- THEN the file SHALL still exist in the volume

#### Requirement: First-run package manager configuration
The system SHALL configure package managers for user-level installs on the first run of a persistent volume.

##### Scenario: npm global installs go to .local
- GIVEN a fresh persistent volume (first run)
- WHEN the container starts
- THEN `npm config get prefix` SHALL return `/home/pi/.local`

##### Scenario: pip installs go to .local
- GIVEN a fresh persistent volume (first run)
- WHEN the container starts
- THEN `PYTHONUSERBASE` SHALL be set to `/home/pi/.local`

##### Scenario: First-run setup is not repeated on subsequent runs
- GIVEN a persistent volume that has already been initialized
- WHEN the container starts again
- THEN the package manager configuration SHALL NOT be re-initialized (existing config preserved)

#### Requirement: Host config mounted read-only at /pi-source
The system SHALL mount the host config directory (`~/.pi/agent`) read-only at `/pi-source`.

##### Scenario: /pi-source is read-only
- GIVEN the container is running
- WHEN the user attempts to write to `/pi-source`
- THEN the write SHALL fail

##### Scenario: /pi-source contains host config
- GIVEN the host config directory contains files
- WHEN the container starts
- THEN the files SHALL be accessible at `/pi-source`

#### Requirement: Reset mechanism
The system SHALL provide a `--reset` flag that removes the project's persistent volume.

##### Scenario: --reset removes the volume
- GIVEN a persistent volume exists for the current project
- WHEN `run.sh --reset` is executed
- THEN the volume SHALL be removed and the script SHALL exit with code 0

##### Scenario: --reset is safe when volume does not exist
- GIVEN no persistent volume exists for the current project
- WHEN `run.sh --reset` is executed
- THEN the script SHALL exit with code 0 (no error)

#### Requirement: Volume isolation between projects
The system SHALL ensure that different projects have isolated persistent volumes. Data written in one project's volume SHALL NOT be accessible from another project's container.

##### Scenario: Project A data not visible from project B
- GIVEN project A writes data to its persistent volume
- WHEN project B's container starts
- THEN project B SHALL NOT see project A's data

#### Requirement: Entrypoint script
The system SHALL use an entrypoint script to perform container initialization before exec-ing the user command.

##### Scenario: Entrypoint runs before user command
- GIVEN the container starts with command `echo hello`
- WHEN the container runs
- THEN the entrypoint SHALL execute config sync and setup before `echo hello` runs

##### Scenario: Entrypoint exports PI_CODING_AGENT_DIR
- GIVEN the container is running
- WHEN checking the `PI_CODING_AGENT_DIR` environment variable
- THEN it SHALL be set to `/home/pi/.pi-agent-data`

#### Requirement: Shell configuration in .bashrc
The system SHALL configure the shell environment in `.bashrc` to support persistent volume paths.

##### Scenario: PATH includes .local/bin
- GIVEN the shell starts in the container
- WHEN checking `$PATH`
- THEN it SHALL include `$HOME/.local/bin`

##### Scenario: PYTHONUSERBASE is set
- GIVEN the shell starts in the container
- WHEN checking `$PYTHONUSERBASE`
- THEN it SHALL be set to `$HOME/.local`

##### Scenario: NPM_CONFIG_PREFIX is set
- GIVEN the shell starts in the container
- WHEN checking `$NPM_CONFIG_PREFIX`
- THEN it SHALL be set to `$HOME/.local`

#### Requirement: Makefile targets
The system SHALL provide Makefile targets for volume management.

##### Scenario: make volumes lists persistent volumes
- GIVEN persistent volumes exist
- WHEN the user runs `make volumes`
- THEN the system SHALL display all `pi-agent-persist-*` volumes

##### Scenario: make reset resets persistent state
- GIVEN a persistent volume exists
- WHEN the user runs `make reset`
- THEN the system SHALL remove the volume (equivalent to `./run.sh --reset`)

### MODIFIED Requirements

#### Requirement: Container filesystem layout
##### Scenario: /home/pi is a persistent volume (was tmpfs)
- GIVEN the container is running
- WHEN inspecting the mount at `/home/pi`
- THEN it SHALL be a persistent podman volume (not a tmpfs mount)

##### Scenario: /pi-source replaces /pi-data
- GIVEN the container is running
- WHEN inspecting the read-only config mount
- THEN it SHALL be mounted at `/pi-source` (not `/pi-data`)

### REMOVED Requirements

#### Requirement: Ephemeral /home/pi tmpfs mount
The previous design used `--mount type=tmpfs,destination=/home/pi` for an ephemeral writable layer. This is replaced by the persistent volume mount.

#### Requirement: Separate sessions bind mount
The previous design used `-v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw"` for a writable sessions directory. This is replaced by the persistent volume which contains sessions at `/home/pi/.pi-agent-data/sessions/`.
