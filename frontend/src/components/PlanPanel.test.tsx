import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PlanPanel } from "./PlanPanel";
import { AgentEvent } from "../types";

describe("PlanPanel", () => {
  it("renders null when no plan events exist", () => {
    const events: AgentEvent[] = [
      {
        event_id: "1",
        sequence: 1,
        task_id: "task-1",
        event_type: "AGENT_ACTION",
        agent: "Planner",
        message: "Starting",
        payload: {},
        timestamp: new Date().toISOString(),
      },
    ];
    const { container } = render(<PlanPanel events={events} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders plan checklist and tracks progress", () => {
    const events: AgentEvent[] = [
      {
        event_id: "1",
        sequence: 1,
        task_id: "task-1",
        event_type: "AGENT_THOUGHT",
        agent: "Planner",
        message: "Plan formulated",
        payload: { kind: "plan", steps: ["Check Tokyo weather", "Calculate difference", "Suggest clothing"] },
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "2",
        sequence: 2,
        task_id: "task-1",
        event_type: "AGENT_ACTION",
        agent: "Researcher",
        message: "Starting step 1",
        payload: { kind: "step_started", step_index: 0 },
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "3",
        sequence: 3,
        task_id: "task-1",
        event_type: "AGENT_THOUGHT",
        agent: "Researcher",
        message: "Found Tokyo weather",
        payload: { kind: "finding", step_index: 0 },
        timestamp: new Date().toISOString(),
      },
      {
        event_id: "4",
        sequence: 4,
        task_id: "task-1",
        event_type: "AGENT_ACTION",
        agent: "Researcher",
        message: "Starting step 2",
        payload: { kind: "step_started", step_index: 1 },
        timestamp: new Date().toISOString(),
      },
    ];

    render(<PlanPanel events={events} />);

    expect(screen.getByText(/Execution Plan \(1\/3\)/)).toBeInTheDocument();
    expect(screen.getByText("Check Tokyo weather")).toBeInTheDocument();
    expect(screen.getByText("Calculate difference")).toBeInTheDocument();
    expect(screen.getByText("Suggest clothing")).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveClass("plan-item-done");
    expect(items[1]).toHaveClass("plan-item-active");
    expect(items[2]).toHaveClass("plan-item-pending");
  });
});
