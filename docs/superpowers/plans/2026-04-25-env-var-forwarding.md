# Env Var Forwarding via ~/.env Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded API key injection in `run.sh` with automatic forwarding of all variables from `~/.env` (or `PI_AGENT_ENV_FILE`).

**Architecture:** `run.sh` sources the env file, extracts variable names with awk, and passes each as `-e <var>` to `podman run`. Tests verify the variables appear in the podman command line.

**Tech Stack:** Bash (dotenv parsing), Python/pytest (testing)

---

## File Structure

| File                          | Responsibility                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------- |
| `run.sh`                      | Modified: replace hardcoded `-e` flags with `~/.env` parsing and forwarding    |
| `tests/test_run.py`           | Modified: test assertions for env vars from `~/.env` instead of env vars       |
| `tests/test_integration.py`   | Modified: `_run_env` helper creates a fake `~/.env` for run.sh invocations     |

---

## Spec Reference

This plan implements the changes described in `SPEC.md` (commit `83f9d76`):
- `ENV_FILE="${PI_AGENT_ENV_FILE:-${HOME}/.env}"` variable added
- `~/.env` is sourced and all defined variables are forwarded via `-e <var>` flags
- Table row updated: `-e ANTHROPIC_API_KEY=...` → `~/.env → -e <var>`
- FE-001 marked as implemented

---

### Task 1: Update run.sh to forward ~/.env variables

**Files:**

- Modify: `run.sh`
- Modify: `tests/test_run.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_run.py`, update `test_run_script_generates_correct_podman_command`:

Replace the hardcoded API key environment variables with a fake `~/.env` file, and update assertions to check for the forwarded variable names:

```python
        env = os.environ.copy()
        env["PATH"] = f"{tmpdir}:{env['PATH']}"
        env["HOME"] = str(tmpdir)
        env["PI_AGENT_CONFIG"] = str(fake_config)

        # Create a fake ~/.env with test API keys
        (tmpdir / ".env").write_text("VLLM_API_KEY=test-vllm-key\nOPENROUTER_API_KEY=test-openrouter-key\n")
```

Replace the assertion lines:

```python
-        assert "ANTHROPIC_API_KEY" in run_line
-        assert "OPENAI_API_KEY" in run_line
+        assert "VLLM_API_KEY" in run_line
+        assert "OPENROUTER_API_KEY" in run_line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_run.py::test_run_script_generates_correct_podman_command -v`

Expected: FAIL — `run.sh` still uses hardcoded `-e ANTHROPIC_API_KEY=...` and `-e OPENAI_API_KEY=...`

- [ ] **Step 3: Write minimal implementation**

In `run.sh`, after the `GLOBAL_CONFIG` variable declaration and before the "Ensure mount sources exist" block, add:

```bash
ENV_FILE="${PI_AGENT_ENV_FILE:-${HOME}/.env}"
```

After the image build block and before the TTY allocation, add the env forwarding logic:

```bash
# Forward all variables defined in the env file
ENV_ARGS=()
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a

    while IFS= read -r key; do
        [[ -z "$key" ]] && continue
        ENV_ARGS+=(-e "$key")
    done < <(awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        {
            gsub(/^[[:space:]]*export[[:space:]]+/, "")
            match($0, /^[[:space:]]*[^=[:space:]]+/)
            if (RLENGTH > 0) {
                key = substr($0, RSTART, RLENGTH)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
                print key
            }
        }
    ' "$ENV_FILE")
fi
```

In the `podman run` command, replace:

```bash
-    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
-    -e OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
+    "${ENV_ARGS[@]}" \
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_run.py -v`

Expected: PASS (2/2 tests pass)

- [ ] **Step 5: Commit**

```bash
git add run.sh tests/test_run.py
git commit -m "feat: forward ~/.env variables to container instead of hardcoded keys"
```

---

### Task 2: Update integration tests for ~/.env

**Files:**

- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_integration.py`, update the `_run_env` helper:

```python
def _run_env(tmpdir):
    """Build the environment dict for run.sh invocations."""
    env = os.environ.copy()
    env["PI_AGENT_IMAGE"] = TEST_IMAGE
    env["PI_AGENT_CONFIG"] = str(pathlib.Path(tmpdir) / "pi-config")
    env["HOME"] = str(tmpdir)

    # Create a fake ~/.env so run.sh has something to source
    env_file = pathlib.Path(tmpdir) / ".env"
    env_file.write_text("VLLM_API_KEY=\nOPENROUTER_API_KEY=\n")
    return env
```

Remove the old lines:
```python
-    env["ANTHROPIC_API_KEY"] = ""
-    env["OPENAI_API_KEY"] = ""
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`

Expected: PASS (all integration tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: update integration tests to use ~/.env forwarding"
```

---

## Review Loop

After completing the plan document, dispatch the plan-document-reviewer subagent with:

- **Plan:** `docs/superpowers/plans/2026-04-25-env-var-forwarding.md`
- **Spec:** `SPEC.md`

Fix any issues found, then re-dispatch the reviewer. Loop up to 3 times before surfacing to human.
