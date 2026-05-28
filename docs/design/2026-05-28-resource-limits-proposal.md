# Proposal: Resource Limits

## Intent

The sandbox must prevent a runaway agent from consuming unlimited host resources. Without limits, an agent in an infinite loop, a fork bomb, or an out-of-control build process could starve the host of CPU, memory, or process slots.

Currently `run.sh` applies `--cpus 4`, `--memory 8g`, and `--pids-limit 1024` to every container run. These limits are documented in `APPEND_SYSTEM.md` but have no behavioral specification.

## Scope

**In scope:**
- CPU limit (`--cpus 4`)
- Memory limit (`--memory 8g`)
- PID limit (`--pids-limit 1024`)
- Limits are enforced on every container run

**Out of scope:**
- Configurable limits (limits are fixed, not user-tunable)
- Disk I/O limits
- Network bandwidth limits

## Approach

Specify the resource limits as behavioral requirements. Each limit has a requirement stating the maximum the container SHALL consume, with scenarios that verify the flags are passed to podman. The implementation is already complete — this spec formalizes the contract.

## Impact

- `docs/design/2026-05-28-resource-limits-proposal.md` — new
- `docs/design/2026-05-28-resource-limits-spec.md` — new
- `docs/design/2026-05-28-resource-limits-delta.md` — new
- `docs/specs/sandbox-environment.md` — updated with resource limit requirements
