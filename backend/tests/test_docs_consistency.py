from __future__ import annotations

import json
import pathlib
import re

from app.agents.prompts import (
    PLANNER_SYSTEM_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    SYNTHESIZER_SYSTEM_PROMPT,
)
from app.tools.registry import get_tool_registry

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent


def test_system_prompts_appear_verbatim_inside_fenced_blocks_in_evaluation():
    eval_file = ROOT_DIR / "EVALUATION.md"
    assert eval_file.exists(), "EVALUATION.md does not exist"
    content = eval_file.read_text(encoding="utf-8")

    prompts = [
        ("PLANNER", PLANNER_SYSTEM_PROMPT),
        ("RESEARCHER", RESEARCHER_SYSTEM_PROMPT),
        ("SYNTHESIZER", SYNTHESIZER_SYSTEM_PROMPT),
    ]
    for name, prompt in prompts:
        fenced_block = f"```text\n{prompt}```"
        assert fenced_block in content, (
            f"{name}_SYSTEM_PROMPT not found inside fenced text block in EVALUATION.md"
        )


def test_tool_names_and_fields_appear_in_evaluation():
    eval_file = ROOT_DIR / "EVALUATION.md"
    assert eval_file.exists(), "EVALUATION.md does not exist"
    content = eval_file.read_text(encoding="utf-8")

    specs = get_tool_registry()
    for spec in specs:
        assert spec.name in content, f"Tool name '{spec.name}' not found in EVALUATION.md"
        schema = spec.args_schema.model_json_schema()
        properties = schema.get("properties", {})
        for prop in properties:
            assert prop in content, (
                f"Tool field '{prop}' of '{spec.name}' not found in EVALUATION.md"
            )


def test_env_variables_appear_in_readme():
    readme_file = ROOT_DIR / "README.md"
    assert readme_file.exists(), "README.md does not exist"
    readme_content = readme_file.read_text(encoding="utf-8")

    env_example_file = ROOT_DIR / ".env.example"
    assert env_example_file.exists(), ".env.example does not exist"

    variables = []
    for line in env_example_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            var_name = line.split("=", 1)[0].strip()
            variables.append(var_name)

    for var in variables:
        assert var in readme_content, f"Environment variable '{var}' not found in README.md"


def test_technology_versions_match_requirements_and_package_lock():
    readme_file = ROOT_DIR / "README.md"
    assert readme_file.exists(), "README.md does not exist"
    readme_content = readme_file.read_text(encoding="utf-8")

    reqs_file = ROOT_DIR / "backend" / "requirements.txt"
    assert reqs_file.exists(), "backend/requirements.txt does not exist"
    reqs_content = reqs_file.read_text(encoding="utf-8")

    pinned_python: dict[str, str] = {}
    for line in reqs_content.splitlines():
        line = line.strip()
        if "==" in line:
            pkg, ver = line.split("==", 1)
            pkg_name = pkg.split("[")[0].strip().lower()
            pinned_python[pkg_name] = ver.strip()

    package_lock_file = ROOT_DIR / "frontend" / "package-lock.json"
    assert package_lock_file.exists(), "frontend/package-lock.json does not exist"
    pkg_lock = json.loads(package_lock_file.read_text(encoding="utf-8"))

    pinned_npm: dict[str, str] = {}
    for path, data in pkg_lock.get("packages", {}).items():
        name = path.replace("node_modules/", "")
        if name in ("react", "vite", "typescript"):
            pinned_npm[name] = data.get("version", "")

    # Match rows from README technology table
    rows = re.findall(
        r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|",
        readme_content,
    )
    for _comp, tech, ver, _desc in rows:
        tech_clean = tech.strip().lower()
        ver_clean = ver.strip()
        if tech_clean in pinned_python:
            assert ver_clean == pinned_python[tech_clean], (
                f"Technology '{tech}' version mismatch: README={ver_clean}, requirements.txt={pinned_python[tech_clean]}"
            )
        elif tech_clean in pinned_npm:
            assert ver_clean == pinned_npm[tech_clean], (
                f"Technology '{tech}' version mismatch: README={ver_clean}, package-lock.json={pinned_npm[tech_clean]}"
            )
