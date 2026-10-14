from __future__ import annotations

import pathlib

from app.agents.prompts import (
    PLANNER_SYSTEM_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    SYNTHESIZER_SYSTEM_PROMPT,
)
from app.tools.registry import get_tool_registry

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent


def test_system_prompts_appear_verbatim_in_evaluation():
    eval_file = ROOT_DIR / "EVALUATION.md"
    assert eval_file.exists(), "EVALUATION.md does not exist"
    content = eval_file.read_text(encoding="utf-8")

    assert PLANNER_SYSTEM_PROMPT in content, (
        "PLANNER_SYSTEM_PROMPT not found verbatim in EVALUATION.md"
    )
    assert RESEARCHER_SYSTEM_PROMPT in content, (
        "RESEARCHER_SYSTEM_PROMPT not found verbatim in EVALUATION.md"
    )
    assert SYNTHESIZER_SYSTEM_PROMPT in content, (
        "SYNTHESIZER_SYSTEM_PROMPT not found verbatim in EVALUATION.md"
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
