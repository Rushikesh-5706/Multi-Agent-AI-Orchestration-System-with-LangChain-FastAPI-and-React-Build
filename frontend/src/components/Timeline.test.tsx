import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Timeline } from "./Timeline";
import { AgentEvent } from "../types";

describe("Timeline", () => {
  it("renders empty placeholder when no events are provided", () => {
    render(<Timeline events={[]} />);
    expect(screen.getByText(/no agent events yet/i)).toBeInTheDocument();
  });

  it("renders events for Planner, Researcher, and Tool Execution", () => {
    const mockEvents: AgentEvent[] = [
      {
        event_id: "1",
        sequence: 1,
        task_id: "t1",
        event_type: "AGENT_THOUGHT",
        agent: "Planner",
        message: "Formulating a plan of action",
        payload: { kind: "plan", steps: ["Step 1", "Step 2"] },
        timestamp: "2026-10-14T10:00:00Z",
      },
      {
        event_id: "2",
        sequence: 2,
        task_id: "t1",
        event_type: "TOOL_INVOCATION",
        agent: "tool_executor",
        message: "Invoking tool 'web_search'",
        payload: { tool: "web_search", arguments: { query: "tokyo weather" } },
        timestamp: "2026-10-14T10:00:02Z",
      },
      {
        event_id: "3",
        sequence: 3,
        task_id: "t1",
        event_type: "TOOL_RESULT",
        agent: "tool_executor",
        message: "Tool 'web_search' completed in 150ms",
        payload: { tool: "web_search", result: "Tokyo is 18C and pleasant", duration_ms: 150 },
        timestamp: "2026-10-14T10:00:03Z",
      },
    ];

    render(<Timeline events={mockEvents} />);
    expect(screen.getByText("Formulating a plan of action")).toBeInTheDocument();
    expect(screen.getByText("Invoking tool 'web_search'")).toBeInTheDocument();
    expect(screen.getByText("150 ms")).toBeInTheDocument();
  });
});
