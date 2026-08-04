from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
NPM_TEST = ROOT / "npm" / "scripts" / "test.js"
PACKAGE_JSON = ROOT / "package.json"


def _workflow_lines():
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def _step_names(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- name:"):
            names.append(stripped.split(":", 1)[1].strip())
    return names


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


def test_ci_workflow_matrix_and_step_order_are_structural():
    lines = _workflow_lines()
    text = "\n".join(lines)

    assert "os: [ubuntu-latest, windows-latest]" in text
    assert "jobs:" in text
    assert "test:" in text

    names = _step_names(lines)
    assert "Install npm package and isolated Python runtime" in names
    assert "Install Python test extras once (Unix)" in names
    assert "Install Python test extras once (Windows)" in names
    assert "Compile Python sources (Unix)" in names
    assert "Compile Python sources (Windows)" in names
    assert "Run npm wrapper test gate" in names
    assert "Pack dry run" in names

    install_idx = names.index("Install npm package and isolated Python runtime")
    extras_unix = names.index("Install Python test extras once (Unix)")
    extras_win = names.index("Install Python test extras once (Windows)")
    npm_test_idx = names.index("Run npm wrapper test gate")
    pack_idx = names.index("Pack dry run")

    assert install_idx < extras_unix < npm_test_idx < pack_idx
    assert install_idx < extras_win < npm_test_idx


def test_ci_workflow_skips_repeated_editable_reinstall_on_npm_test():
    lines = _workflow_lines()
    joined = "\n".join(lines)
    assert "SMART_SEARCH_SKIP_EDITABLE_REINSTALL" in joined
    assert '-e ".[dev]"' in joined or "-e \".[dev]\"" in joined

    # Env must be attached to the npm test step, not only mentioned elsewhere.
    npm_idx = next(i for i, line in enumerate(lines) if line.strip() == "- name: Run npm wrapper test gate")
    window = "\n".join(lines[npm_idx : npm_idx + 8])
    assert "SMART_SEARCH_SKIP_EDITABLE_REINSTALL: \"1\"" in window
    assert "run: npm test" in window


def test_npm_test_script_supports_skip_and_force_editable_reinstall():
    script = NPM_TEST.read_text(encoding="utf-8")
    assert "SMART_SEARCH_SKIP_EDITABLE_REINSTALL" in script
    assert "SMART_SEARCH_FORCE_EDITABLE_REINSTALL" in script
    assert "shouldInstallEditable" in script
    assert '-e", ".[dev]"' in script or "-e\", \".[dev]\"" in script


def test_package_json_exposes_test_fast_script():
    package = PACKAGE_JSON.read_text(encoding="utf-8")
    assert '"test:fast"' in package
    assert "SMART_SEARCH_SKIP_EDITABLE_REINSTALL" in package
