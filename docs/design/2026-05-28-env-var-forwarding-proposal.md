# Proposal: Env Var Forwarding

## Intent

The sandbox needs access to API keys and other secrets (`VLLM_API_KEY`, `OPENROUTER_API_KEY`, etc.) from the host. Baking them into the image is insecure and inflexible. This change formalizes the existing behavior of forwarding environment variables from the host into the container at runtime.

## Scope

**In scope:**
- `.env` file parsing (comments, blank lines, `export` prefix)
- `PI_AGENT_ENV_FILE` override for custom env file path
- Forwarding variables as `-e KEY` flags to `podman run`
- Skipping empty variable names and malformed lines

**Out of scope:**
- Validation of env file contents
- Default values for missing variables
- Secret rotation or encryption

## Approach

The `run.sh` script reads `~/.env` (or the path set by `PI_AGENT_ENV_FILE`), extracts variable names using `awk`, and passes each as `-e KEY` to `podman run`. Podman automatically forwards the current process's value for each named variable.

## Impact

- `docs/specs/sandbox-environment.md` — new requirement for env var forwarding
- No code changes required (behavior is already implemented)
