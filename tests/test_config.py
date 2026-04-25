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
