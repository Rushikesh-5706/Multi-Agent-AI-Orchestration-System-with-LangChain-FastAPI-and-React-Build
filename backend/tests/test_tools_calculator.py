from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tools.calculator import run_calculator
from app.tools.schemas import CalculatorInput


def test_calculator_expression_basic():
    output = run_calculator(operation="expression", expression="(18 + 22) / 2")
    assert output == "Result: 20.0"


def test_calculator_expression_functions():
    assert run_calculator(operation="expression", expression="sqrt(144)") == "Result: 12.0"
    assert run_calculator(operation="expression", expression="abs(-42)") == "Result: 42.0"
    assert run_calculator(operation="expression", expression="round(3.14159, 2)") == "Result: 3.14"
    assert run_calculator(operation="expression", expression="min(10, 5, 20)") == "Result: 5.0"
    assert run_calculator(operation="expression", expression="max(10, 5, 20)") == "Result: 20.0"


def test_calculator_division_by_zero():
    output = run_calculator(operation="expression", expression="100 / 0")
    assert output.startswith("Error: Division by zero.")


def test_calculator_syntax_error():
    output = run_calculator(operation="expression", expression="2 + * 3")
    assert output.startswith("Error: Syntax error in expression:")


def test_calculator_security_disallowed_imports_and_calls():
    output = run_calculator(operation="expression", expression='__import__("os").system("ls")')
    assert output.startswith("Error:")

    output2 = run_calculator(operation="expression", expression="eval('2+2')")
    assert output2.startswith("Error:")
    assert "not allowed" in output2


def test_calculator_security_attribute_access():
    output = run_calculator(operation="expression", expression="(10).__class__")
    assert output.startswith("Error:")
    assert "Attribute access is not allowed" in output


def test_calculator_security_variable_names():
    output = run_calculator(operation="expression", expression="x + 5")
    assert output.startswith("Error:")
    assert "Variable name 'x' is not allowed" in output


def test_calculator_huge_exponent():
    output = run_calculator(operation="expression", expression="2 ** 10000")
    assert output.startswith("Error:")
    assert "exceeds limit" in output


def test_calculator_statistics():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert run_calculator(operation="sum", values=vals) == "Result: 150.0"
    assert run_calculator(operation="mean", values=vals) == "Result: 30.0"
    assert run_calculator(operation="median", values=vals) == "Result: 30.0"
    assert run_calculator(operation="min", values=vals) == "Result: 10.0"
    assert run_calculator(operation="max", values=vals) == "Result: 50.0"


def test_calculator_stdev():
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    output = run_calculator(operation="stdev", values=vals)
    assert output.startswith("Result: 2.138")


def test_calculator_percent_change():
    output = run_calculator(operation="percent_change", values=[100.0, 150.0])
    assert "50.0000% change from 100.0 to 150.0" in output

    output_div_zero = run_calculator(operation="percent_change", values=[0.0, 50.0])
    assert "Cannot compute percent change when the old value is 0" in output_div_zero


def test_calculator_schema_validation():
    # Missing expression for expression operation
    with pytest.raises(ValidationError):
        CalculatorInput(operation="expression")

    # Missing values for mean operation
    with pytest.raises(ValidationError):
        CalculatorInput(operation="mean")

    # Wrong number of values for percent_change
    with pytest.raises(ValidationError):
        CalculatorInput(operation="percent_change", values=[10.0, 20.0, 30.0])
