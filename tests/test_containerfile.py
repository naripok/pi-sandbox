import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_containerfile_exists():
    assert (REPO_ROOT / "Containerfile").exists()

def test_containerfile_has_required_directives():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "FROM archlinux" in content
    assert "nodejs" in content
    assert "npm" in content
    assert "git" in content
    assert "openssh" in content
    assert "bash" in content
    assert "@mariozechner/pi-coding-agent" in content
    assert "useradd" in content
    assert "USER pi" in content
    assert "WORKDIR /workspace" in content
    assert "config/.bashrc" in content


def test_containerfile_has_rsync_package():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "rsync" in content, "Missing rsync package for config sync"



def test_containerfile_has_entrypoint():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "entrypoint.sh" in content, "Missing entrypoint.sh reference"
    assert "ENTRYPOINT" in content, "Missing ENTRYPOINT directive"


def test_containerfile_has_user_pi():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "USER pi" in content, "Missing USER pi directive"


def test_containerfile_pins_pi_agent_version():
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "ARG PI_AGENT_VERSION=" in content, "Missing version ARG for pi-coding-agent"
    assert "@${PI_AGENT_VERSION}" in content, "pi-coding-agent install should use the version ARG"


def test_containerfile_accepts_extra_packages_arg():
    """Verifies Containerfile defines EXTRA_PACKAGES build arg."""
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "ARG EXTRA_PACKAGES" in content, "Missing ARG EXTRA_PACKAGES"
    assert "EXTRA_PACKAGES" in content, "EXTRA_PACKAGES must be used in the build"


def test_containerfile_has_build_error_handling():
    """Verifies Containerfile has error handling for package installation failures."""
    content = (REPO_ROOT / "Containerfile").read_text()
    assert "exit 1" in content, "Must have explicit error exit on package failure"
