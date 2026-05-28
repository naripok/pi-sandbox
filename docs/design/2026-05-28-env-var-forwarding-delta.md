# Delta: Env Var Forwarding

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: Env var forwarding from host
The system SHALL forward environment variables from a host env file into the container at runtime. Variables are passed as `-e KEY` flags to `podman run`, allowing podman to inject the current process's value for each named variable.

##### Scenario: Variables from ~/.env are forwarded
- GIVEN `~/.env` contains `VLLM_API_KEY=abc123`
- WHEN the sandbox is launched
- THEN the podman run command SHALL include `-e VLLM_API_KEY`

##### Scenario: Multiple variables are forwarded
- GIVEN `~/.env` contains `VLLM_API_KEY=abc` and `OPENROUTER_API_KEY=def`
- WHEN the sandbox is launched
- THEN the podman run command SHALL include `-e VLLM_API_KEY` and `-e OPENROUTER_API_KEY`

#### Requirement: Env file path configuration
The system SHALL read environment variables from `~/.env` by default. The `PI_AGENT_ENV_FILE` environment variable SHALL override this path.

##### Scenario: Default env file path
- GIVEN `PI_AGENT_ENV_FILE` is not set and `~/.env` exists
- WHEN the sandbox is launched
- THEN variables from `~/.env` SHALL be forwarded into the container

##### Scenario: Custom env file path via PI_AGENT_ENV_FILE
- GIVEN `PI_AGENT_ENV_FILE` is set to `/custom/path.env`
- WHEN the sandbox is launched
- THEN variables from `/custom/path.env` SHALL be forwarded into the container

##### Scenario: No forwarding when env file does not exist
- GIVEN `~/.env` does not exist and `PI_AGENT_ENV_FILE` is not set
- WHEN the sandbox is launched
- THEN no environment variables SHALL be forwarded from an env file

#### Requirement: Env file parsing
The system SHALL parse the env file line by line, extracting variable names from `KEY=VALUE` pairs.

##### Scenario: Lines with export prefix are handled
- GIVEN the env file contains `export MY_VAR=value`
- WHEN the sandbox is launched
- THEN `MY_VAR` SHALL be forwarded into the container

##### Scenario: Comment lines are skipped
- GIVEN the env file contains `# this is a comment`
- WHEN the sandbox is launched
- THEN the comment line SHALL be ignored (no variable forwarded)

##### Scenario: Blank lines are skipped
- GIVEN the env file contains a blank line
- WHEN the sandbox is launched
- THEN the blank line SHALL be ignored (no variable forwarded)
