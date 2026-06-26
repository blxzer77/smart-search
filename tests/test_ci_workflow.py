from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_ci_workflow_runs_release_gates_on_windows_and_linux():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "matrix:" in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "npm ci" in workflow
    assert "compileall" in workflow
    assert "npm test" in workflow
    assert "pack:dry" in workflow
    assert "actions/setup-node@" in workflow
    assert "actions/setup-python@" in workflow
