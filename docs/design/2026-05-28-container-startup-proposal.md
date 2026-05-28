# Proposal: Container Startup

## Intent

Several container startup behaviors are implemented but not specified: how the workspace is mounted, how the container is named, how TTY allocation works, how npm security is enforced, and how the agent receives its environment documentation. These behaviors are small individually but collectively define the agent's runtime environment.

## Scope

**In scope:**
- Workspace mount (`$(pwd):/workspace`)
- Container naming (`pi-agent-<project>-<random>`)
- TTY allocation (interactive vs non-interactive)
- npm lifecycle scripts disabled (`ignore-scripts=true`)
- Agent offline/telemetry flags (`PI_OFFLINE`, `PI_TELEMETRY`)
- APPEND_SYSTEM.md injection

**Out of scope:**
- Persistent volume setup (covered by persistent volume spec)
- Security hardening (covered by security hardening spec)
- Resource limits (covered by resource limits spec)
- Network mode (covered by network mode spec)

## Approach

Specify each startup behavior as a behavioral requirement with GIVEN/WHEN/THEN scenarios. Most are single-scenario requirements since the behavior is straightforward. The implementation is already complete — this spec formalizes the contract.

## Impact

- `docs/design/2026-05-28-container-startup-proposal.md` — new
- `docs/design/2026-05-28-container-startup-spec.md` — new
- `docs/design/2026-05-28-container-startup-delta.md` — new
- `docs/specs/sandbox-environment.md` — updated with startup requirements
