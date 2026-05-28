# Proposal: Security Hardening

## Intent

The sandbox must prevent a compromised or malicious agent from escaping the container, modifying system files, escalating privileges, or accessing host resources. These guarantees are the core value proposition of running an AI coding agent in an isolated environment.

Currently these security properties are implemented in `run.sh` and `Containerfile` but have no behavioral specification — they exist as implementation details without a stated contract.

## Scope

**In scope:**
- Read-only root filesystem (`--read-only`)
- Dropped capabilities (`--cap-drop=ALL`)
- No-new-privileges enforcement (`--security-opt=no-new-privileges`)
- Setuid/setgid binary stripping at image build time
- Ephemeral writable `/tmp` via tmpfs
- User namespace isolation (`--userns=keep-id`)
- PID namespace isolation (implicit with podman)

**Out of scope:**
- Network isolation (outbound/inbound rules — separate concern)
- Resource limits (CPU, memory, PIDs — separate concern)
- Volume/workspace mount permissions (covered by persistent volume spec)
- Host config read-only mount (covered by persistent volume spec)

## Approach

Specify the security hardening properties as behavioral requirements against the running container. Each requirement states what the container SHALL or SHALL NOT allow, with GIVEN/WHEN/THEN scenarios that map directly to the existing security tests.

The implementation is already complete — this spec formalizes the contract.

## Impact

- `docs/design/2026-05-28-security-hardening-proposal.md` — new
- `docs/design/2026-05-28-security-hardening-spec.md` — new
- `docs/design/2026-05-28-security-hardening-delta.md` — new
- `docs/specs/sandbox-environment.md` — updated with security requirements
