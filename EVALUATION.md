# System Evaluation and Architecture Documentation

## 1. Orchestration Pattern Selection: LangGraph vs AutoGen

This system implements a state machine workflow using LangGraph rather than Microsoft AutoGen. The decision is based on four concrete technical differences.

### 1.1 State Representation and Deterministic Transitions

LangGraph models execution as a directed cyclic graph over a typed state object (`AgentState`). State transitions are governed by deterministic Python functions (`_after_planner`, `_after_researcher`) that evaluate explicit state fields (`current_step`, `plan`, `fatal_error`). Control flows through defined edges rather than conversational consensus.

AutoGen models interaction as multi-turn conversational debate between autonomous conversational agents. While effective for open-ended brainstorming, conversational routing lacks deterministic step boundaries. An agent in AutoGen may continue conversational turns indefinitely unless hard stop criteria are met, making bounded task execution and deterministic step tracking difficult.

### 1.2 State Persistence and Sequence Tracking

LangGraph operates with state update deltas returned from each node function. Each transition emits an atomic state update that is logged directly to PostgreSQL as an `AgentEvent` record with an incrementing integer `sequence`. This provides a sequential audit trail where each step can be traced, replayed and verified.

AutoGen requires intercepting message dictionaries within an internal conversation manager. Correlating individual tool calls and intermediate decisions to discrete workflow steps requires monkey-patching conversational callbacks.

### 1.3 Asynchronous Tool Execution Integration

In this architecture, long-running I/O operations (`web_search` and `get_weather`) are dispatched to Celery worker processes via Redis, while CPU-light calculations (`data_calculator`) run inline. LangGraph node functions are native `async` functions that allow awaiting Celery task resolution (`asyncio.to_thread`) without blocking the FastAPI event loop or starving WebSocket ping frames.

AutoGen conversational loops are historically synchronous or require specialized async runtimes, which complicates integration with external task queues like Celery.

### 1.4 Context Window Management

LangGraph enables per-step context scoping. In the Researcher node, each sub-step starts with only the system prompt and the current step instruction. Findings from previous steps are stored in the state TypedDict rather than accumulated verbatim in a conversational message history. This prevents token explosion across multi-step research plans.

---

## 2. Agent Roles and System Prompts

The system defines three specialized agents. Each agent has an explicit, bounded responsibility and operates under strict honesty constraints.

### 2.1 Planner Agent

The Planner receives the user's initial prompt and a catalog of available tools. It breaks the user prompt down into a sequence of concrete, actionable sub-tasks (between 1 and 5 steps). It does not execute tools and does not fabricate answers.

The Planner system prompt:

You are the Planner agent in a multi-agent reasoning system.

Today's date (UTC): {today}

Your role is to receive the user's prompt and decompose it into a concise, ordered list of
research steps. Each step must be self-contained and specific enough for a tool-equipped
research agent to execute independently.

Inputs you receive:
- The original user prompt.
- A catalog of available tools with their purpose and parameters.

Available tools:
{tool_catalog}

Output format (strict):
Return a JSON array of strings and nothing else. No prose, no markdown fences, no keys.
Example:
["Step one description", "Step two description", "Step three description"]

If you cannot produce a valid array, return a JSON object with a single key "steps" whose
value is the array:
{{"steps": ["Step one", "Step two"]}}

Hard rules:
- Between 1 and {max_plan_steps} steps.
- Each step must describe a concrete research action (search, look up, calculate).
- Do not include steps that merely summarize or format; that is the Synthesizer's role.
- Do not invent facts. Your output is a plan, not an answer.
- Honesty rule: if you cannot determine what steps are needed, produce a single step
  instructing the Researcher to gather the relevant information directly.


### 2.2 Researcher Agent

The Researcher executes individual plan steps. It receives one step at a time, selects tools from the registry, executes them through the tool executor, and collects findings. The loop is bounded to at most 4 tool iterations per step. Tool errors are returned to the model as observations so the agent can adapt or report missing data.

The Researcher system prompt:

You are the Researcher agent in a multi-agent reasoning system.

Today's date (UTC): {today}

Your role is to execute a single research step by calling the available tools and collecting
factual information. You must use the tools to find real data; do not fabricate figures.

Current step ({step_index} of {total_steps}): {current_step}

Original user prompt for context: {original_prompt}

Tools you may call:
- web_search: Search the web with DuckDuckGo. Use for general facts, news and background info.
- get_weather: Get current weather for a location. Requires a city and country code.
- data_calculator: Evaluate arithmetic or compute statistics on a list of numbers.

Hard rules:
- Call tools to gather information; do not guess at values.
- If a tool returns an error string (starting with "Error:"), adapt: try a different query,
  a different tool, or note that the data is unavailable.
- After at most {max_tool_iterations} rounds of tool calls, produce a final answer for this
  step even if some data is missing. State clearly what could not be obtained.
- Do not repeat tool calls with identical arguments.
- Honesty rule: report only values that appear in tool output. Never invent numbers, dates
  or names. If data is unavailable, say so explicitly.
- Your final text response (without further tool calls) becomes the finding for this step.
  Keep it focused and factual.


### 2.3 Synthesizer Agent

The Synthesizer combines all research findings into a structured final response. It has no tool access and relies entirely on verified findings produced during the research phase. If any finding includes an error or unavailable data, the Synthesizer acknowledges that limitation.

The Synthesizer system prompt:

You are the Synthesizer agent in a multi-agent reasoning system.

Your role is to combine the research findings from all completed steps and produce a clear,
well-organized final answer to the original user prompt.

Original prompt: {original_prompt}

Execution plan:
{plan_text}

Research findings:
{findings_text}

Hard rules:
- Address the original prompt directly and completely.
- If a finding includes an error or notes that data was unavailable, acknowledge that
  limitation explicitly in your answer. Do not fabricate substitute data.
- Do not call any tools. Your only input is the findings above.
- Honesty rule: every number, fact or name in your answer must appear in the findings.
  If a finding contains an error message, report the limitation to the user clearly.
- Structure your answer for readability: use short paragraphs or a brief list where
  appropriate, but do not pad with filler.


---

## 3. Custom Tools Specification

The system implements three custom tools. Each tool defines a Pydantic input schema with explicit descriptions, runs through a dedicated runner function, and returns formatted strings with bounded length.

### 3.1 Web Search Tool (`web_search`)

- Name: `web_search`
- Execution mode: Celery distributed task (`tools.web_search`)
- Runner: `app.tools.web_search.run_web_search`
- Purpose: DuckDuckGo text search for real-time information, news and facts.

#### Input Schema (`WebSearchInput`)

Fields:
- `query`: string, min length 2, max length 300. Description: The search query string.
- `max_results`: integer, min 1, max 5, default 3. Description: Maximum number of results to return.

```json
{
  "description": "Search the web using DuckDuckGo for current information on any topic.\n\nUse this tool when you need to find up-to-date facts, news, statistics or\nbackground information from the internet. Provide a focused search query\nthat clearly states what you are looking for.",
  "properties": {
    "query": {
      "description": "The search query string. Must be specific and descriptive. Example: 'current population of Tokyo 2024' or 'Python asyncio best practices'.",
      "maxLength": 300,
      "minLength": 2,
      "title": "Query",
      "type": "string"
    },
    "max_results": {
      "default": 3,
      "description": "Maximum number of results to return. Between 1 and 5.",
      "maximum": 5,
      "minimum": 1,
      "title": "Max Results",
      "type": "integer"
    }
  },
  "required": [
    "query"
  ],
  "title": "WebSearchInput",
  "type": "object"
}
```

#### Output and Error Handling Strategy

- Output: Numbered list with result title, target URL, and trimmed snippet.
- Truncation: Output capped at `MAX_TOOL_OUTPUT_CHARS` (1500 chars) with `[truncated]` marker.
- Empty result: Returns `"No results found for the query '<query>'. Try rephrasing the query or searching for a related term."` (not an error).
- Rate limit: Catches DuckDuckGo 202/rate-limit exceptions and returns `"Error: DuckDuckGo rate limit reached. Wait a moment and retry with the same query, or rephrase the query."`
- Timeout: Catches socket and request timeouts and returns `"Error: Web search timed out. Retry with a simpler query, or try a different tool."`
- Generic errors: Returns `"Error: Web search failed (<exc_type>). Retry with a different query or use another tool to gather the information."`

### 3.2 Weather Tool (`get_weather`)

- Name: `get_weather`
- Execution mode: Celery distributed task (`tools.get_weather`)
- Runner: `app.tools.weather.run_get_weather`
- Purpose: OpenWeather current weather lookup via two-phase geocoding and weather observations.

#### Input Schema (`WeatherSearchInput`)

Fields:
- `location`: string, min length 2, max length 200. Description: City and state or country code.
- `units`: string literal (`"metric"` or `"imperial"`), default `"metric"`. Description: Temperature unit system.

```json
{
  "description": "Get the current weather conditions for any city or location worldwide.\n\nUse this tool when the user asks about current weather, temperature, humidity,\nwind or general conditions at a specific place. Always include the country code\nfor unambiguous results.",
  "properties": {
    "location": {
      "description": "The city and state or country, e.g. 'Tokyo, JP' or 'San Francisco, CA, US'. Include the ISO country code or state abbreviation to avoid ambiguity.",
      "maxLength": 200,
      "minLength": 2,
      "title": "Location",
      "type": "string"
    },
    "units": {
      "default": "metric",
      "description": "Temperature unit system. 'metric' returns Celsius and m/s wind speed. 'imperial' returns Fahrenheit and mph wind speed.",
      "enum": [
        "metric",
        "imperial"
      ],
      "title": "Units",
      "type": "string"
    }
  },
  "required": [
    "location"
  ],
  "title": "WeatherSearchInput",
  "type": "object"
}
```

#### Output and Error Handling Strategy

- Output: Formatted summary including resolved city name, country, weather condition, temperature, feels-like temperature, relative humidity percentage, and wind speed with unit labels.
- Missing API key: Returns `"Error: OPENWEATHER_API_KEY is not configured. Weather data cannot be retrieved. Report to the user that weather is unavailable."`
- Key rejected (HTTP 401): Returns `"Error: OpenWeather API key rejected (HTTP 401). Do not retry this call. Report to the user that the weather API is not authorized."` This explicit instruction prevents model retry loops.
- Location not found: Returns `"Error: Location '<location>' was not found by OpenWeather. Try a more specific location name including the country code, for example 'Paris, FR' or 'Springfield, IL, US'."`
- Rate limit (HTTP 429): Returns `"Error: OpenWeather API rate limit reached (HTTP 429). Wait before retrying, or report that weather is temporarily unavailable."`
- Server error (HTTP 5xx): Returns `"Error: OpenWeather server error (HTTP <status>). Retry once; if it fails again, report the outage."`
- Network errors: Distinct timeout and connection failure messages with connect timeout 5 seconds and read timeout 10 seconds.
- Non-JSON / malformed payload: Returns format error string.

### 3.3 Calculator Tool (`data_calculator`)

- Name: `data_calculator`
- Execution mode: Inline execution within API worker process
- Runner: `app.tools.calculator.run_calculator`
- Purpose: Safe arithmetic expression evaluation and descriptive statistics on numeric arrays.

#### Input Schema (`CalculatorInput`)

Fields:
- `operation`: string literal (`"expression"`, `"sum"`, `"mean"`, `"median"`, `"min"`, `"max"`, `"stdev"`, `"percent_change"`).
- `expression`: string or null, max length 200. Required when operation is `"expression"`.
- `values`: array of numbers or null, 1 to 500 items. Required when operation is statistical. For `"percent_change"` requires exactly 2 items `[old_value, new_value]`.

```json
{
  "description": "Perform safe arithmetic evaluation or descriptive statistics on numeric data.\n\nUse this tool when you need to compute a mathematical expression, or when\nyou have a list of numbers and need summary statistics such as mean, median\nor standard deviation. Do not use this tool for symbolic algebra.",
  "properties": {
    "operation": {
      "description": "The operation to perform. 'expression' evaluates a safe arithmetic expression (requires 'expression' field). 'sum', 'mean', 'median', 'min', 'max', 'stdev' compute statistics on 'values'. 'percent_change' computes (new - old) / old * 100 and requires exactly 2 values: [old_value, new_value].",
      "enum": [
        "expression",
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "stdev",
        "percent_change"
      ],
      "title": "Operation",
      "type": "string"
    },
    "expression": {
      "anyOf": [
        {
          "maxLength": 200,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "An arithmetic expression to evaluate. Required when operation is 'expression'. Allowed: numbers, +, -, *, /, //, %, **, unary minus/plus, parentheses, and the functions abs(), round(), min(), max(), sqrt(). Example: '(18 + 22) / 2' or 'sqrt(144)'.",
      "title": "Expression"
    },
    "values": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "maxItems": 500,
          "minItems": 1,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "A list of numeric values for statistical operations. Required when operation is not 'expression'. For 'percent_change' supply exactly [old_value, new_value]. Example: [23.5, 18.0, 31.2, 27.8].",
      "title": "Values"
    }
  },
  "required": [
    "operation"
  ],
  "title": "CalculatorInput",
  "type": "object"
}
```

#### Output and Error Handling Strategy

- Execution: Expression evaluation via Python AST (`ast.parse`) using an explicit node allow-list: `ast.Expression`, `ast.Constant`, `ast.UnaryOp`, `ast.BinOp`, `ast.Call`.
- Allowed functions: `abs`, `round`, `min`, `max`, `sqrt`. All other function names rejected.
- Security enforcement: Rejects `ast.Attribute` access, variable identifiers (`ast.Name` not in allow-list), imports, and expressions exceeding 200 characters.
- Power operation safeguard: Limits exponent magnitude to 1000 to prevent CPU exhaustion.
- Division by zero: Trapped and returns `"Error: Division by zero."` or `"Error: Modulo by zero."`
- Percent change by zero: If the old value is zero, returns `"Error: Cannot compute percent change when the old value is 0 (division by zero)."`
- Statistics: Computes sum, mean, median, min, max, standard deviation via the standard library `statistics` module. Standard deviation on fewer than 2 values returns clear error.
- Output: Returns formatted string prefixed with `"Result: "` or `"Error: "`.
