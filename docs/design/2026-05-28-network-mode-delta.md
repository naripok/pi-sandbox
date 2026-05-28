# Delta: Network Mode

## Domain: sandbox-environment

### ADDED Requirements

#### Requirement: Outbound network access
The system SHALL allow the container to make outbound network connections. HTTP requests, DNS resolution, package installs, and git operations SHALL work.

##### Scenario: HTTP requests succeed
- GIVEN the sandbox is launched
- WHEN the user makes an HTTP request (e.g., `curl https://example.com`)
- THEN the request SHALL succeed

##### Scenario: DNS resolution works
- GIVEN the sandbox is launched
- WHEN the user resolves a domain name (e.g., `host github.com`)
- THEN the resolution SHALL succeed

#### Requirement: Host localhost unreachable
The system SHALL prevent the container from reaching host services on `localhost` or `127.0.0.1`. The container's `localhost` SHALL refer to the container itself, not the host.

##### Scenario: Cannot reach host services on localhost
- GIVEN the container is running
- WHEN the user attempts to connect to `localhost` (e.g., `curl http://localhost:8080`)
- THEN the connection SHALL fail (host services are not accessible)

#### Requirement: Network mode flag
The system SHALL run the container with `--network=pasta` to provide outbound-only network access.

##### Scenario: Network mode is set to pasta
- GIVEN the sandbox is launched
- WHEN podman run is invoked
- THEN the command SHALL include `--network=pasta`
