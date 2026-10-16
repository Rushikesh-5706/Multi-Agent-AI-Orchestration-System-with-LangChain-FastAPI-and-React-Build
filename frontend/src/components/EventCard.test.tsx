import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { EventCard } from "./EventCard";
import { AgentEvent } from "../types";

describe("EventCard", () => {
  it("renders transition separator correctly", () => {
    const event: AgentEvent = {
      event_id: "trans-1",
      sequence: 3,
      task_id: "task-1",
      event_type: "AGENT_ACTION",
      agent: "planner",
      message: "Node 'planner' completed.",
      payload: { kind: "transition", node: "researcher" },
      timestamp: "2026-10-16T12:00:00.000Z",
    };

    const { container } = render(<EventCard event={event} />);
    expect(container.querySelector(".timeline-transition")).toBeInTheDocument();
    expect(screen.getByText(/researcher/)).toBeInTheDocument();
  });

  it("renders tool error state with card-error class", () => {
    const event: AgentEvent = {
      event_id: "tool-err-1",
      sequence: 4,
      task_id: "task-1",
      event_type: "TOOL_RESULT",
      agent: "tool_executor",
      message: "Tool 'get_weather' failed",
      payload: {
        tool: "get_weather",
        is_error: true,
        result: "Error: 401 Unauthorized",
        duration_ms: 120,
      },
      timestamp: "2026-10-16T12:00:01.000Z",
    };

    const { container } = render(<EventCard event={event} />);
    const article = container.querySelector("article");
    expect(article).toHaveClass("card-error");
    expect(screen.getByText("Tool 'get_weather' failed")).toBeInTheDocument();
    expect(screen.getByText("120 ms")).toBeInTheDocument();
  });

  it("toggles technical details on button click", () => {
    const event: AgentEvent = {
      event_id: "tool-inv-1",
      sequence: 5,
      task_id: "task-1",
      event_type: "TOOL_INVOCATION",
      agent: "tool_executor",
      message: "Invoking tool 'web_search'",
      payload: {
        tool: "web_search",
        arguments: { query: "Tokyo weather" },
      },
      timestamp: "2026-10-16T12:00:02.000Z",
    };

    render(<EventCard event={event} />);
    const toggleBtn = screen.getByRole("button", { name: /view parameters and payload/i });
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByText(/"Tokyo weather"/)).toBeInTheDocument();
  });

  it("renders thought and completed event cards", () => {
    const thoughtEvent: AgentEvent = {
      event_id: "thought-1",
      sequence: 6,
      task_id: "task-1",
      event_type: "AGENT_THOUGHT",
      agent: "Synthesizer",
      message: "Synthesizing final findings",
      payload: {},
      timestamp: "2026-10-16T12:00:03.000Z",
    };
    render(<EventCard event={thoughtEvent} />);
    expect(screen.getByText("Synthesizing final findings")).toBeInTheDocument();

    const completedEvent: AgentEvent = {
      event_id: "comp-1",
      sequence: 7,
      task_id: "task-1",
      event_type: "COMPLETED",
      agent: "system",
      message: "Task completed successfully",
      payload: { final_result: "Done" },
      timestamp: "2026-10-16T12:00:04.000Z",
    };
    render(<EventCard event={completedEvent} />);
    expect(screen.getByText("Task completed successfully")).toBeInTheDocument();
  });
});
