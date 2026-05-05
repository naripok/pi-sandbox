import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

def test_bashrc_exists():
    assert (REPO_ROOT / "config" / ".bashrc").exists()

def test_bashrc_sets_prompt():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert "PS1" in content

def test_bashrc_enables_color_ls():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert "ls --color=auto" in content


def test_bashrc_sets_local_bin_in_path():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert '$HOME/.local/bin' in content, "Missing $HOME/.local/bin in PATH"


def test_bashrc_sets_pythonuserbase():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'PYTHONUSERBASE' in content, "Missing PYTHONUSERBASE export"


def test_bashrc_sets_npm_config_prefix():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'NPM_CONFIG_PREFIX' in content, "Missing NPM_CONFIG_PREFIX export"


def test_bashrc_sets_pi_coding_agent_dir():
    content = (REPO_ROOT / "config" / ".bashrc").read_text()
    assert 'PI_CODING_AGENT_DIR' in content, "Missing PI_CODING_AGENT_DIR export"
