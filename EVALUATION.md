# System Evaluation and Architecture Documentation

## 1. Orchestration Pattern Selection: LangGraph vs AutoGen

This system implements a state machine workflow using LangGraph rather than Microsoft AutoGen. The decision is based on concrete architectural and operational differences.

### 1.1 Technical Comparison

| Dimension | LangGraph Architecture | AutoGen Multi-Agent Architecture |
|---|---|---|
| State Representation | Explicit, typed `AgentState` object passed across graph nodes. Every field is strongly typed. | Implicit state scattered across conversational message dictionaries and agent-internal buffers. |
| Control Flow and Routing | Deterministic graph routing functions (`_after_planner`, `_after_researcher`) evaluating explicit state flags. | Conversational consensus and heuristic speaker-selection loops that can diverge into circular debate. |
| Persistence and Auditability | Atomic state deltas emitted after node completions, logged with monotonic sequence numbers in PostgreSQL. | Message history interception via callbacks, requiring internal event extraction to determine tool boundaries. |
| Context Management | Context scoping per step: Researcher receives only the current step and a bounded summary of previous findings. | Message concatenation: full conversation histories grow monotonically, risking context window exhaustion. |
| Tool Execution Model | Async node execution supporting decoupled background task queues (Celery over Redis) and inline calculation. | Historically synchronous execution loops; async tools require non-standard runtime hooks. |
| Failure Containment | Bounded tool loops per step with structured error strings returned to the model as observations. | Unhandled exceptions in tool execution often break conversational turns or trigger unconstrained retries. |

### 1.2 State Representation and Deterministic Transitions

LangGraph models execution as a directed cyclic graph over a typed state dictionary (`AgentState`). State transitions are governed by deterministic Python functions (`_after_planner`, `_after_researcher`, `_after_synthesizer`) that evaluate explicit state fields (`current_step`, `plan`, `fatal_error`). Control flows strictly through defined edges rather than open-ended multi-turn debate.

AutoGen models interaction as conversational turn-taking between autonomous agents. While effective for exploratory brainstorming, conversational routing lacks rigid step boundaries. Bounding task duration, tracking explicit sub-task completion, and enforcing single-step execution requires fragile conversational parsing.

### 1.3 State Persistence and Sequence Tracking

LangGraph operates with atomic state update deltas returned from each node function. Each transition emits an atomic event logged directly to PostgreSQL as an `AgentEvent` record with an incrementing integer `sequence`. This provides a sequential audit trail where each step can be replayed and verified.

AutoGen requires intercepting message dictionaries within an internal conversation manager. Correlating individual tool calls and intermediate decisions to discrete workflow steps requires monkey-patching conversational callbacks.

### 1.4 Context Window Management Strategy

LangGraph enables per-step context scoping. In the Researcher node, each sub-step starts with only the system prompt and the current step instruction.

To allow subsequent research steps to build upon previous data without unbounded prompt growth:
1. Completed step findings are stored in the state TypedDict as a list of structured `Finding` objects (`step_index`, `step_text`, `finding`).
2. Before invoking the model for step `N > 1`, `_format_previous_findings()` builds an accumulated findings block.
3. If the formatted findings exceed an 1800-character budget, the oldest findings are trimmed first, preserving the most recent findings and prepending a `[earlier findings trimmed]` marker.
4. The formatted block is injected into the Researcher system prompt under `{previous_findings}`, accompanied by explicit instructions to reuse earlier values and avoid redundant tool calls.

---

## 2. Architecture and Data Flow

The system implements the 11 numbered flows from the architecture flowchart:

| Flow | Operation | Source | Destination | Implementing File(s) | Description |
|---|---|---|---|---|---|
| 1 | POST /api/tasks | UI | API | `frontend/src/api/client.ts`, `backend/app/api/tasks.py` | Client submits prompt; API validates schema. |
| 2 | WS /api/ws/:task_id | UI | API | `frontend/src/hooks/useAgentWebSocket.ts`, `backend/app/api/websocket.py` | Client establishes persistent WebSocket connection. |
| 3 | Create TaskRun | API | DB | `backend/app/db/repositories.py`, `backend/app/db/models.py` | Inserts new task record in `PENDING` status. |
| 4 | Trigger workflow | API | Graph | `backend/app/api/tasks.py`, `backend/app/agents/runner.py` | Launches background `run_workflow` task. |
| 5 | Inferences and tool calls | Graph | LLM | `backend/app/agents/nodes/*.py`, `backend/app/agents/llm.py` | Agents execute prompts via Groq API. |
| 6 | Dispatch async task | Graph | Redis | `backend/app/agents/tool_executor.py`, `backend/app/worker/tasks.py` | Celery client queues tool task to Redis broker. |
| 7 | Consume task | Redis | Worker | `backend/app/worker/celery_app.py`, `backend/app/worker/tasks.py` | Celery worker picks task from Redis queue. |
| 8 | Execute tool | Worker | Tools | `backend/app/tools/web_search.py`, `backend/app/tools/weather.py` | Worker executes external HTTP requests. |
| 9 | Return and fetch result | Worker/Redis | Graph | `backend/app/agents/tool_executor.py` | Result retrieved via `asyncio.to_thread(async_result.get)`. |
| 10 | Persist AgentEvent | Graph | DB | `backend/app/agents/events.py`, `backend/app/db/repositories.py` | Atomic insert of event with incrementing sequence. |
| 11 | Broadcast wire payload | Graph/CM | UI | `backend/app/api/connection_manager.py`, `backend/app/api/serializers.py` | Serialized JSON pushed to active WebSockets. |

---

## 3. Shared State Schema and Routing Table

### 3.1 State Schema (`AgentState`)

The shared workflow state is defined as a `typing.TypedDict` with total typing:

```python
class Finding(TypedDict):
    step_index: int
    step_text: str
    finding: str

class AgentState(TypedDict):
    original_prompt: str
    plan: list[str]
    current_step: int
    findings: list[Finding]
    had_errors: bool
    final_answer: str | None
    fatal_error: str | None
```

### 3.2 Routing Functions

State machine transitions are evaluated by pure router functions:

| Router Function | Source Node | Condition | Destination | Purpose |
|---|---|---|---|---|
| `_after_planner` | `planner` | `state["fatal_error"] is not None` | `END` | Abort immediately if LLM configuration/auth failed |
| `_after_planner` | `planner` | `len(state.get("plan", [])) == 0` | `END` | Abort if planner produced an empty plan |
| `_after_planner` | `planner` | `len(state["plan"]) > 0` | `researcher` | Begin execution of plan step 0 |
| `_after_researcher` | `researcher` | `state["fatal_error"] is not None` | `END` | Abort immediately on fatal model/system error |
| `_after_researcher` | `researcher` | `state["current_step"] < len(state["plan"])` | `researcher` | Loop to execute the next plan step |
| `_after_researcher` | `researcher` | `state["current_step"] >= len(state["plan"])` | `synthesizer` | All steps complete; proceed to synthesis |
| `_after_synthesizer` | `synthesizer` | unconditionally | `END` | Workflow finished |

---

## 4. Agents

The system defines three specialized agents. Each agent has an explicit, bounded responsibility and operates under strict honesty constraints.

### 4.1 Planner Agent

- **Role**: Receives the initial prompt and tool catalog; decomposes the request into 1 to 5 concrete research steps.
- **Inputs**: `original_prompt`, `tool_catalog`, `today`, `max_plan_steps`.
- **Outputs**: `plan` (list of strings).
- **System Prompt**:

```text
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
- A step may rely on the result of an earlier step and should say so in words ("using the temperature found in step 1").
- Do not include steps that merely summarize or format; that is the Synthesizer's role.
- Do not invent facts. Your output is a plan, not an answer.
- Honesty rule: if you cannot determine what steps are needed, produce a single step
  instructing the Researcher to gather the relevant information directly.
```

### 4.2 Researcher Agent

- **Role**: Executes a single plan step per invocation using tool calling. Collects factual data and adapts to errors.
- **Inputs**: `current_step`, `step_index`, `total_steps`, `original_prompt`, `previous_findings`, `today`, `max_tool_iterations`.
- **Outputs**: `findings` entry appended, `had_errors` flag updated, `current_step` incremented.
- **System Prompt**:

```text
You are the Researcher agent in a multi-agent reasoning system.

Today's date (UTC): {today}

Your role is to execute a single research step by calling the available tools and collecting
factual information. You must use the tools to find real data; do not fabricate figures.

Current step ({step_index} of {total_steps}): {current_step}

Original user prompt for context: {original_prompt}

Earlier findings:
{previous_findings}
Reuse these values where relevant and do not re-fetch data they already contain.

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
```

### 4.3 Synthesizer Agent

- **Role**: Combines all research findings into a final, structured answer.
- **Inputs**: `original_prompt`, `plan_text`, `findings_text`.
- **Outputs**: `final_answer`.
- **System Prompt**:

```text
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
```

---

## 5. Custom Tools

### 5.1 Web Search Tool (`web_search`)

- **Purpose**: Search the web using DuckDuckGo for current news, facts, and documentation.
- **Execution Mode**: Distributed Celery task (`tools.web_search`) consumed via Redis.
- **Runner**: `app.tools.web_search.run_web_search`.

#### Parameter Schema (`WebSearchInput`)

| Field | Type | Constraints | Description |
|---|---|---|---|
| `query` | `string` | Min 2, Max 300 chars | The search query string. |
| `max_results` | `integer` | Min 1, Max 5, Default 3 | Maximum number of search results to return. |

#### Generated JSON Schema

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

#### Real Output Sample (Captured from Test Fixture)

```text
1. Tokyo Travel Guide - Weather and Seasonal Packing
   URL: https://example.com/tokyo-guide
   Summary: In autumn, Tokyo experiences mild temperatures around 20C with periodic rain. A waterproof jacket and light layers are recommended.

2. Tokyo Climate and Packing Advice
   URL: https://example.com/packing-tokyo
   Summary: Average October temperatures range between 18C and 22C. Visitors should bring an umbrella and water-resistant footwear.
```

#### Error Conditions and Exact Messages

The tool catches typed `ddgs.exceptions` classes:

| Condition | Caught Exception | Exact Returned Message |
|---|---|---|
| Rate limited by DuckDuckGo | `ddgs.exceptions.RatelimitException` | `Error: DuckDuckGo rate limit reached. Wait a moment and retry with the same query, or rephrase the query.` |
| Search timeout | `ddgs.exceptions.TimeoutException` | `Error: Web search timed out. Retry with a simpler query, or try a different tool.` |
| Generic search failure | `ddgs.exceptions.DDGSException` | `Error: Web search failed (<exc_class>: <details>). Retry with a different query or use another tool to gather the information.` |
| Unexpected exception | `Exception` (logged with `exc_info`) | `Error: Web search failed (<exc_class>: <details>). Retry with a different query or use another tool to gather the information.` |
| Empty results | Zero items returned | `No results found for the query '<query>'. Try rephrasing the query or searching for a related term.` |

### 5.2 Weather Tool (`get_weather`)

- **Purpose**: Retrieve real-time weather observations from OpenWeather.
- **Execution Mode**: Distributed Celery task (`tools.get_weather`) consumed via Redis.
- **Runner**: `app.tools.weather.run_get_weather`.

#### Parameter Schema (`WeatherSearchInput`)

| Field | Type | Constraints | Description |
|---|---|---|---|
| `location` | `string` | Min 2, Max 200 chars | City and country code, e.g. `'Tokyo, JP'`. |
| `units` | `string` | Enum `["metric", "imperial"]`, Default `"metric"` | Measurement system (`metric` for Celsius, `imperial` for Fahrenheit). |

#### Generated JSON Schema

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

#### Real Output Sample (Captured from Live Tier A Execution)

```text
Location: Tokyo, JP
Condition: moderate rain
Temperature: 20.78 C
Feels like: 20.66 C
Humidity: 67%
Wind: 3.84 m/s
```

#### Error Conditions and Exact Messages

| Condition | Trigger | Exact Returned Message |
|---|---|---|
| Missing configuration | `OPENWEATHER_API_KEY` is empty | `Error: OPENWEATHER_API_KEY is not configured. Weather data cannot be retrieved. Report to the user that weather is unavailable.` |
| Key rejected | HTTP 401 | `Error: OpenWeather API key rejected (HTTP 401). Do not retry this call. Report to the user that the weather API is not authorized.` |
| Location not found | Empty geocoding array / 404 | `Error: Location '<location>' was not found by OpenWeather. Try a more specific location name including the country code, for example 'Paris, FR' or 'Springfield, IL, US'.` |
| Rate limited | HTTP 429 | `Error: OpenWeather API rate limit reached (HTTP 429). Wait before retrying, or report that weather is temporarily unavailable.` |
| Server error | HTTP 5xx | `Error: OpenWeather server error (HTTP <status>). Retry once; if it fails again, report the outage.` |
| Network timeout | Connect > 5s, Read > 10s | `Error: Weather request timed out after <timeout>s. Retry the call or report that the weather service is slow.` |
| Connection failed | DNS / network down | `Error: Failed to connect to OpenWeather. Check network connectivity or retry later.` |
| Bad response payload | Non-JSON response | `Error: OpenWeather returned an invalid response (not JSON).` |

### 5.3 Calculator Tool (`data_calculator`)

- **Purpose**: AST-safe arithmetic expression evaluation and statistical calculations.
- **Execution Mode**: Inline execution within API worker process (zero network roundtrips).
- **Runner**: `app.tools.calculator.run_calculator`.

#### Parameter Schema (`CalculatorInput`)

| Field | Type | Constraints | Description |
|---|---|---|---|
| `operation` | `string` | Enum `["expression", "sum", "mean", "median", "min", "max", "stdev", "percent_change"]` | The mathematical operation to execute. |
| `expression` | `string \| null` | Max 200 chars | Expression string (required when operation is `"expression"`). |
| `values` | `array[number] \| null` | 1 to 500 items | Numeric array (required when operation is statistical; exactly 2 items for `"percent_change"`). |

#### Generated JSON Schema

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

#### Real Output Sample (Captured from Live Tier A Execution)

```text
Result: 35.90582079790713%
```
*(Computed for operation `"percent_change"` with values `[15.29, 20.78]`)*

#### Error Conditions and Exact Messages

| Condition | Trigger | Exact Returned Message |
|---|---|---|
| Missing expression | `operation="expression"` without `expression` | `Error: The 'expression' field is required when operation is 'expression'.` |
| Missing values | Statistical operation without `values` | `Error: The 'values' field is required when operation is '<op>'.` |
| Invalid percent change length | `operation="percent_change"` with len != 2 | `Error: percent_change requires exactly 2 values: [old_value, new_value].` |
| Division by zero (expression) | Division or modulo by 0 | `Error: Division by zero.` |
| Percent change division by zero | `old_value == 0` | `Error: Cannot compute percent change when the old value is 0 (division by zero).` |
| Stdev too few items | `values` has fewer than 2 items | `Error: Standard deviation requires at least 2 values.` |
| Disallowed function call | Function not in `[abs, round, min, max, sqrt]` | `Error: Function '<name>' is not allowed. Allowed functions: abs, min, max, round, sqrt.` |
| Disallowed syntax | Attribute access, assignment, etc. | `Error: Expression syntax '<node_type>' is not allowed.` |
| Disallowed variable name | Variable identifier not allowed | `Error: Variable '<name>' is not allowed. Use numeric literals directly.` |
| Syntax error | Malformed math string | `Error: Syntax error in expression: <error>` |

---

## 6. Persistence and Auditability

### 6.1 Database Tables

The persistence model is implemented using PostgreSQL with SQLAlchemy 2.0:

#### Table `task_runs`
- `id` (`UUID`, Primary Key)
- `prompt` (`TEXT`, NOT NULL)
- `status` (`VARCHAR(32)`, NOT NULL, Default `'PENDING'`)
- `final_result` (`TEXT`, NULLABLE)
- `created_at` (`TIMESTAMPTZ`, NOT NULL)
- `updated_at` (`TIMESTAMPTZ`, NOT NULL)
- `completed_at` (`TIMESTAMPTZ`, NULLABLE)

#### Table `agent_events`
- `id` (`UUID`, Primary Key)
- `task_run_id` (`UUID`, Foreign Key referencing `task_runs.id` ON DELETE CASCADE)
- `sequence` (`INTEGER`, NOT NULL)
- `agent_name` (`VARCHAR(64)`, NOT NULL)
- `event_type` (`VARCHAR(32)`, NOT NULL)
- `payload` (`JSONB`, NOT NULL)
- `timestamp` (`TIMESTAMPTZ`, NOT NULL)
- Table constraint: `UNIQUE (task_run_id, sequence)`

### 6.2 Event Types and Payload Shapes

All events stored in the database and delivered over WebSockets belong to one of these types:

#### 1. `AGENT_THOUGHT`
```json
{
  "message": "Created plan with 2 step(s).",
  "plan": ["Step 1 description", "Step 2 description"]
}
```

#### 2. `AGENT_ACTION`
```json
{
  "message": "Starting step 1/2: Use get_weather to check Tokyo conditions",
  "node": "researcher",
  "step_index": 0
}
```

#### 3. `TOOL_INVOCATION`
```json
{
  "message": "Invoking tool 'get_weather'",
  "tool": "get_weather",
  "arguments": {
    "location": "Tokyo, JP",
    "units": "metric"
  },
  "execution": "celery"
}
```

#### 4. `TOOL_RESULT`
```json
{
  "message": "Tool 'get_weather' completed in 445ms",
  "tool": "get_weather",
  "result": "Location: Tokyo, JP\nCondition: moderate rain...",
  "duration_ms": 445,
  "is_error": false,
  "execution": "celery"
}
```

#### 5. `COMPLETED`
```json
{
  "message": "Final answer delivered to user and stored in database.",
  "final_result": "Based on the retrieved weather data..."
}
```

#### 6. `ERROR`
```json
{
  "message": "Groq API key is invalid or not authorized",
  "fatal": true
}
```

#### 7. `HEARTBEAT`
```json
{
  "message": "heartbeat"
}
```

### 6.3 Sequence Guarantees and Rejected Call Auditing

- **Monotonic Integer Sequence**: In `backend/app/db/repositories.py`, the sequence is computed inside an atomic transaction:
  `SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_events WHERE task_run_id = :task_id`.
  The unique database constraint `UNIQUE (task_run_id, sequence)` prevents sequence collisions and guarantees gapless ordering.
- **Rejected Tool Invocations**: In `backend/app/agents/tool_executor.py`, if an LLM calls an unknown tool or supplies arguments failing Pydantic validation, both `TOOL_INVOCATION` and `TOOL_RESULT` events are persisted with `is_error=true` and `execution="rejected"`. Every attempted action leaves a verifiable audit trail.

---

## 7. Real-Time Delivery

### 7.1 WebSocket Wire Format

Every event delivered over WebSocket conforms to the standard wire schema serialized by `app.api.serializers.serialize_event`:

```json
{
  "event_id": "d0ef635b-c2e3-4d43-bb92-c4eec031945c",
  "sequence": 3,
  "task_id": "7c82a536-e054-4bd5-94be-d731835eec06",
  "event_type": "TOOL_INVOCATION",
  "agent": "tool_executor",
  "message": "Invoking tool 'get_weather'",
  "payload": {
    "tool": "get_weather",
    "arguments": {
      "location": "Tokyo, JP",
      "units": "metric"
    },
    "execution": "celery"
  },
  "timestamp": "2026-10-14T10:00:04.123Z"
}
```

### 7.2 Replay and One-Delivery Guarantee

When a client connects to `/api/ws/{task_id}`:
1. The WebSocket handler verifies the task exists (closes with code 4404 if not found).
2. The client is registered with `ConnectionManager`.
3. `replay_and_stream()` queries all persisted historical events ordered by `sequence ASC` and streams them.
4. Concurrently, new events emitted by the runner are queued for broadcast.
5. To prevent duplicate deliveries if an event is committed while replay is active, `_Connection.send()` executes under an `asyncio.Lock()` and asserts `sequence > self.last_sequence`. Duplicate or out-of-order sequence frames are discarded.
6. Idle connections receive a `HEARTBEAT` event every `WS_HEARTBEAT_SECONDS` (15s).
7. Upon delivering a terminal event (`COMPLETED` or fatal `ERROR`), `replay_and_stream()` returns `True`, and the WebSocket closes cleanly with status code 1000.

---

## 8. Failure Handling and Recovery

### 8.1 Third-Party Tool Failures

When external services fail (e.g. OpenWeather HTTP 401, DuckDuckGo rate limiting), the tool catches the exception and returns a structured string starting with `"Error: "`.
The error string is logged in `agent_events` with `is_error=true` and passed back to the Researcher as an observation. The agent observes the failure and either adapts its arguments or reports the limitation to the Synthesizer.

### 8.2 LLM Provider Rate Limits (HTTP 429)

In `app.agents.llm.py`, Groq `RateLimitError` exceptions are caught. The handler:
1. Parses the `retry-after` header from the response or extracts the delay from the provider message (e.g. `"Please try again in 14.5s"`).
2. Caps the wait at 60 seconds.
3. Publishes a non-fatal `system` action event (`rate_limit_wait`) over WebSocket so the UI displays the wait countdown.
4. Sleeps asynchronously and retries up to `LLM_MAX_RETRIES` times.

### 8.3 Authentication and Configuration Failures

If Groq returns `AuthenticationError` (HTTP 401) or `PermissionDeniedError` (HTTP 403), retrying is futile. The system raises `LLMConfigurationError`, publishes a fatal `ERROR` event, sets `state["fatal_error"]`, and routes immediately to `END`. The task status is marked `FAILED`.

### 8.4 Planner Failure Recovery

In `app.agents.nodes.planner.py`, the model output is parsed into a list of step strings. If the model produces unparseable output or invalid JSON, it retries up to 2 times. If both retries fail, it falls back to a deterministic single-step plan using the user's raw prompt, emits a non-fatal `ERROR` event, and continues execution.

### 8.5 Researcher Per-Step Error Recovery

If an individual research step encounters a model failure after tool calls, `researcher_node` catches the exception, logs a non-fatal `ERROR` event, records `"Unavailable: the model request failed (...)"` as the finding for that step, sets `had_errors=True`, and advances `current_step`. The workflow does not terminate; subsequent steps continue.

### 8.6 Workflow Timeout

`app.agents.runner.run_workflow` wraps execution in `asyncio.wait_for(timeout=settings.WORKFLOW_TIMEOUT_SECONDS)` (default: 300s). If exceeded, the graph task is cancelled, an `ERROR` event (`"Workflow timed out after 300s."`) is published, and the task status is marked `FAILED`.

### 8.7 Server Interruption Recovery

In `app.main.py`, the application startup lifespan handler invokes `mark_interrupted_runs_failed()`. Any `TaskRun` records left in `PENDING` or `IN_PROGRESS` state from an unexpected container shutdown or process crash are transitioned to `FAILED` with an explanatory `ERROR` event.

---

## 9. Testing

The test suite provides complete automated coverage across all system boundaries:

### 9.1 Test Suites and Coverage

| Suite | File | What It Proves | Command |
|---|---|---|---|
| Repositories | `test_db_repositories.py` | CRUD operations, atomic sequence generation, status lifecycle, interrupted run sweep. | `pytest backend/tests/test_db_repositories.py` |
| Tool Executor | `test_tool_executor.py` | Celery dispatch, inline execution, Celery timeout revocation, duration metrics, rejection audit events. | `pytest backend/tests/test_tool_executor.py` |
| Web Search Tool | `test_tools_web_search.py` | DuckDuckGo search, `ddgs.exceptions` typed catching (rate limit, timeout, generic), truncation marker. | `pytest backend/tests/test_tools_web_search.py` |
| Weather Tool | `test_tools_weather.py` | OpenWeather 2-phase lookup, 401 non-retry instruction, 404 location lookup, timeouts, formatting. | `pytest backend/tests/test_tools_weather.py` |
| Calculator Tool | `test_tools_calculator.py` | AST allow-list, expression evaluation, statistical functions, zero-division guarding, syntax rejection. | `pytest backend/tests/test_tools_calculator.py` |
| Celery Tasks | `test_tools_celery.py` | Celery task signatures, serialization, simulated delay integration. | `pytest backend/tests/test_tools_celery.py` |
| LLM Retries | `test_llm_retry.py` | Groq exception categorization, `retry-after` extraction, sleep duration capping, tool-use error retry. | `pytest backend/tests/test_llm_retry.py` |
| Graph Flow | `test_graph_flow.py` | Multi-step plan execution, context passing to Researcher, planner fallbacks, router isolation. | `pytest backend/tests/test_graph_flow.py` |
| Runner | `test_runner.py` | Workflow timeout, task cancellation, missing final answer handling, node transition events. | `pytest backend/tests/test_runner.py` |
| Live WebSocket | `test_ws_live.py` | Mid-run replay, sequence monotonicity, idle heartbeats, clean 1000 closure, invalid UUID 4404. | `pytest backend/tests/test_ws_live.py` |
| WebSocket Race | `test_ws_race.py` | Concurrent replay and live broadcast deduplication under lock. | `pytest backend/tests/test_ws_race.py` |
| Health and Lifespan | `test_api_health.py`, `test_lifespan.py` | Component health reporting (200 vs 503), OpenAPI schema omission, startup interrupted run cleanup. | `pytest backend/tests/test_api_health.py backend/tests/test_lifespan.py` |
| Docs Consistency | `test_docs_consistency.py` | Verbatim system prompts in `EVALUATION.md`, technology versions in `README.md`, environment variable parity. | `pytest backend/tests/test_docs_consistency.py` |
| Frontend Components | `*.test.tsx`, `*.test.ts` | Form submission, event timeline cards, plan progress, final answer rendering, WebSocket hook state. | `npm test -- --run` |

---

## 10. Known Limitations

- **Single Uvicorn Process for WebSockets**: The `ConnectionManager` maintains client WebSocket objects in Python memory. To run multiple Uvicorn worker processes or horizontally scale backend containers across nodes, a Redis Pub/Sub message broker must be integrated into `ConnectionManager`.
- **Bounded Step Context**: In multi-step research plans, findings from earlier steps are capped at 1800 characters before injection into subsequent step prompts. Highly verbose search outputs from earlier steps are trimmed to prevent model context window saturation.
- **DuckDuckGo Rate Limits**: DuckDuckGo's public search endpoint may throttle frequent queries. While handled gracefully with descriptive error strings, production environments with high search frequency benefit from a dedicated search API subscription (such as Google Custom Search or Tavily).
- **Free-Tier Weather Endpoints**: The `get_weather` tool targets OpenWeather Current Weather 2.5 API endpoints. Ambiguous location queries without an explicit ISO country code (e.g. `"Springfield"`) may resolve unexpectedly.
