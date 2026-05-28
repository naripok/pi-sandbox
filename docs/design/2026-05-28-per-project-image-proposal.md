# Proposal: Per-Project Sandbox Images

## Intent

Projects that need system-level dependencies (CMake, libffi, ffmpeg) cannot install them inside the sandbox due to the read-only rootfs and lack of root access. Currently the only option is to manually edit the Containerfile and rebuild — a fragile, non-reproducible workflow that requires the agent to instruct the user to modify the pi-coding-agent project itself.

This change enables projects to declare system packages declaratively (`.pi-packages`), get a per-project isolated image, and require explicit user approval before any rebuild. The agent writes `.pi-packages`, the user approves on next run, the image rebuilds — no manual intervention beyond the approval gate.

## Scope

**In scope:**
- `.pi-packages` file format (one package per line, `#` comments)
- Automatic detection in `run.sh` with hash-based image naming
- Explicit user approval before rebuild
- Input validation (reject dangerous characters)
- `make images` target for listing per-project images
- Updated `Containerfile` to accept `EXTRA_PACKAGES` build arg
- Updated `APPEND_SYSTEM.md` documentation for the agent

**Out of scope:**
- Automatic image pruning
- Custom base images per project
- Binary-only or source-built packages (beyond what pacman provides)
- Cross-project package sharing

## Approach

The `run.sh` script detects `.pi-packages` in the project root. If present, it computes a SHA-256 hash of the file contents, derives a per-project image name (`pi-agent-isolated-<project>-<hash>`), and passes the packages as a `--build-arg EXTRA_PACKAGES` to the Containerfile. Before rebuilding, the script prompts the user to confirm the package list. The Containerfile appends `$EXTRA_PACKAGES` to the `pacman -S` install line.

If no `.pi-packages` exists, the project uses the shared base image `pi-agent-isolated` — zero overhead for projects with no extra dependencies.

## Impact

- `run.sh` — new image name derivation, approval prompt, build arg passing
- `Containerfile` — new `ARG EXTRA_PACKAGES`, conditional append to pacman line
- `Makefile` — new `images` target
- `config/APPEND_SYSTEM.md` — document the `.pi-packages` workflow for the agent
- `tests/test_run.py` — tests for detection, hash, approval, image naming
- `tests/test_containerfile.py` — test for EXTRA_PACKAGES arg
- `tests/test_integration.py` — end-to-end rebuild flow
