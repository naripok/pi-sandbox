# Proposal: Network Mode

## Intent

The sandbox needs outbound network access (installing packages, calling LLM APIs, pushing git) but must not be reachable from the host or external network. Currently `run.sh` uses `--network=pasta` to provide this asymmetric access, but the behavioral contract is not specified.

## Scope

**In scope:**
- Outbound network access (HTTP, DNS, etc.)
- Inbound network blocked (no port forwarding, no host reachability)
- Host `localhost` unreachable from container
- Separate network namespace

**Out of scope:**
- Network bandwidth limits
- Firewall rules
- DNS configuration customization

## Approach

Specify the network behavior as behavioral requirements. Pasta provides a separate network namespace with outbound access but no inbound reachability. The implementation is already complete — this spec formalizes the contract.

## Impact

- `docs/design/2026-05-28-network-mode-proposal.md` — new
- `docs/design/2026-05-28-network-mode-spec.md` — new
- `docs/design/2026-05-28-network-mode-delta.md` — new
- `docs/specs/sandbox-environment.md` — updated with network mode requirements
