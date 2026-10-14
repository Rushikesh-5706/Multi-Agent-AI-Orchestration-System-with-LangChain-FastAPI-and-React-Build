from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class WebSearchInput(BaseModel):
    """Search the web using DuckDuckGo for current information on any topic.

    Use this tool when you need to find up-to-date facts, news, statistics or
    background information from the internet. Provide a focused search query
    that clearly states what you are looking for.
    """

    query: str = Field(
        description=(
            "The search query string. Must be specific and descriptive. "
            "Example: 'current population of Tokyo 2024' or 'Python asyncio best practices'."
        ),
        min_length=2,
        max_length=300,
    )
    max_results: int = Field(
        default=3,
        description="Maximum number of results to return. Between 1 and 5.",
        ge=1,
        le=5,
    )


class WeatherSearchInput(BaseModel):
    """Get the current weather conditions for any city or location worldwide.

    Use this tool when the user asks about current weather, temperature, humidity,
    wind or general conditions at a specific place. Always include the country code
    for unambiguous results.
    """

    location: str = Field(
        description=(
            "The city and state or country, e.g. 'Tokyo, JP' or 'San Francisco, CA, US'. "
            "Include the ISO country code or state abbreviation to avoid ambiguity."
        ),
        min_length=2,
        max_length=200,
    )
    units: Literal["metric", "imperial"] = Field(
        default="metric",
        description=(
            "Temperature unit system. 'metric' returns Celsius and m/s wind speed. "
            "'imperial' returns Fahrenheit and mph wind speed."
        ),
    )


class CalculatorInput(BaseModel):
    """Perform safe arithmetic evaluation or descriptive statistics on numeric data.

    Use this tool when you need to compute a mathematical expression, or when
    you have a list of numbers and need summary statistics such as mean, median
    or standard deviation. Do not use this tool for symbolic algebra.
    """

    operation: Literal[
        "expression", "sum", "mean", "median", "min", "max", "stdev", "percent_change"
    ] = Field(
        description=(
            "The operation to perform. "
            "'expression' evaluates a safe arithmetic expression (requires 'expression' field). "
            "'sum', 'mean', 'median', 'min', 'max', 'stdev' compute statistics on 'values'. "
            "'percent_change' computes (new - old) / old * 100 and requires exactly 2 values: "
            "[old_value, new_value]."
        )
    )
    expression: str | None = Field(
        default=None,
        description=(
            "An arithmetic expression to evaluate. Required when operation is 'expression'. "
            "Allowed: numbers, +, -, *, /, //, %, **, unary minus/plus, parentheses, "
            "and the functions abs(), round(), min(), max(), sqrt(). "
            "Example: '(18 + 22) / 2' or 'sqrt(144)'."
        ),
        max_length=200,
    )
    values: list[float] | None = Field(
        default=None,
        description=(
            "A list of numeric values for statistical operations. "
            "Required when operation is not 'expression'. "
            "For 'percent_change' supply exactly [old_value, new_value]. "
            "Example: [23.5, 18.0, 31.2, 27.8]."
        ),
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="after")
    def check_fields_for_operation(self) -> CalculatorInput:
        if self.operation == "expression":
            if not self.expression:
                raise ValueError("Field 'expression' is required when operation is 'expression'.")
        else:
            if not self.values:
                raise ValueError(
                    f"Field 'values' is required when operation is '{self.operation}'."
                )
            if self.operation == "percent_change" and len(self.values) != 2:
                raise ValueError(
                    "Operation 'percent_change' requires exactly 2 values: [old_value, new_value]."
                )
        return self
