import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useAgentWebSocket } from "./useAgentWebSocket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason?: string }) => void) | null = null;
  onerror: ((error: unknown) => void) | null = null;
  readyState: number = 0;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      if (this.onopen) this.onopen();
    }, 10);
  }

  close(code: number = 1000) {
    this.readyState = 3;
    if (this.onclose) {
      this.onclose({ code });
    }
  }

  send() {}
}

describe("useAgentWebSocket", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllTimers();
  });

  it("handles null taskId gracefully", () => {
    const { result } = renderHook(() => useAgentWebSocket(null));
    expect(result.current.events).toEqual([]);
    expect(result.current.connectionState).toBe("closed");
    expect(result.current.finalResult).toBeNull();
  });

  it("connects and receives events, ignoring duplicates and heartbeats", async () => {
    const { result } = renderHook(() => useAgentWebSocket("task-123"));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    expect(result.current.connectionState).toBe("live");

    const ws = MockWebSocket.instances[0];

    // Send normal event
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "evt-1",
          sequence: 1,
          task_id: "task-123",
          event_type: "AGENT_THOUGHT",
          agent: "Planner",
          message: "Step 1 planned",
          payload: {},
          timestamp: new Date().toISOString(),
        }),
      });
    });

    // Send HEARTBEAT
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_type: "HEARTBEAT",
          timestamp: new Date().toISOString(),
        }),
      });
    });

    // Send duplicate event (replay de-duplication)
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "evt-1",
          sequence: 1,
          task_id: "task-123",
          event_type: "AGENT_THOUGHT",
          agent: "Planner",
          message: "Step 1 planned",
          payload: {},
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(result.current.events.length).toBe(1);
    expect(result.current.events[0].event_id).toBe("evt-1");
  });

  it("handles terminal COMPLETED event with final_result key", async () => {
    const { result } = renderHook(() => useAgentWebSocket("task-456"));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "evt-comp",
          sequence: 2,
          task_id: "task-456",
          event_type: "COMPLETED",
          agent: "system",
          message: "Everything done",
          payload: { final_result: "Final synthesis result" },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(result.current.isFinished).toBe(true);
    expect(result.current.finalResult).toBe("Final synthesis result");
    expect(result.current.connectionState).toBe("closed");
  });

  it("handles fatal ERROR terminal event", async () => {
    const { result } = renderHook(() => useAgentWebSocket("task-err"));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          event_id: "evt-err",
          sequence: 2,
          task_id: "task-err",
          event_type: "ERROR",
          agent: "system",
          message: "API key invalid",
          payload: { fatal: true },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    expect(result.current.isFinished).toBe(true);
    expect(result.current.error).toBe("API key invalid");
    expect(result.current.connectionState).toBe("closed");
  });

  it("reconnects with exponential delay on abnormal disconnect", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useAgentWebSocket("task-reconn"));

    // Initial connection
    act(() => {
      vi.advanceTimersByTime(20);
    });
    expect(MockWebSocket.instances.length).toBe(1);

    // Simulate unexpected drop (code 1006)
    act(() => {
      MockWebSocket.instances[0].close(1006);
    });

    expect(result.current.connectionState).toBe("reconnecting");

    // First reconnect delay is 1000ms
    act(() => {
      vi.advanceTimersByTime(1050);
    });

    expect(MockWebSocket.instances.length).toBe(2);
    vi.useRealTimers();
  });
});
