import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send() {}
  close(code: number = 1000) {
    if (this.onclose) {
      this.onclose({ code });
    }
  }
}

describe("App Integration", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ task_id: "task-integration-123" }),
        })
      )
    );
  });

  it("submits prompt, shows plan, tool error, and final result", async () => {
    render(<App />);

    const textarea = screen.getByRole("textbox", { name: /task prompt/i });
    const submitBtn = screen.getByRole("button", { name: /start workflow/i });

    fireEvent.change(textarea, { target: { value: "Test prompt for agent execution" } });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("task-integration-123")).toBeInTheDocument();
    });

    expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    const ws = FakeWebSocket.instances[0];

    act(() => {
      ws.onopen?.();
    });

    // 1. Plan panel appears
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "plan-1",
          sequence: 1,
          task_id: "task-integration-123",
          event_type: "AGENT_THOUGHT",
          agent: "Planner",
          message: "Created plan with 2 steps",
          payload: { kind: "plan", steps: ["Inspect database", "Format report"] },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(screen.getByText("Execution Plan (0/2)")).toBeInTheDocument();
    expect(screen.getByText("Inspect database")).toBeInTheDocument();

    // 2. Tool card with error styling appears
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "tool-err-1",
          sequence: 2,
          task_id: "task-integration-123",
          event_type: "TOOL_RESULT",
          agent: "tool_executor",
          message: "Tool 'web_search' failed with 429",
          payload: {
            tool: "web_search",
            is_error: true,
            result: "Error: Rate limit reached",
            duration_ms: 80,
          },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(screen.getByText("Tool 'web_search' failed with 429")).toBeInTheDocument();
    const errorCard = document.querySelector(".card-error");
    expect(errorCard).toBeInTheDocument();

    // 3. Final result renders
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "comp-1",
          sequence: 3,
          task_id: "task-integration-123",
          event_type: "COMPLETED",
          agent: "system",
          message: "Synthesis completed",
          payload: { final_result: "Everything verified successfully." },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(screen.getByText("Synthesized Final Answer")).toBeInTheDocument();
    expect(screen.getByText("Everything verified successfully.")).toBeInTheDocument();
  });

  it("renders fatal error panel when fatal error event is received", async () => {
    render(<App />);

    const textarea = screen.getByRole("textbox", { name: /task prompt/i });
    const submitBtn = screen.getByRole("button", { name: /start workflow/i });

    fireEvent.change(textarea, { target: { value: "Test prompt failure" } });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("task-integration-123")).toBeInTheDocument();
    });

    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.onopen?.();
    });

    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "fatal-1",
          sequence: 1,
          task_id: "task-integration-123",
          event_type: "ERROR",
          agent: "system",
          message: "Groq API key invalid or not authorized",
          payload: { fatal: true, detail: "401 Unauthorized" },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Groq API key invalid or not authorized");
  });
});
