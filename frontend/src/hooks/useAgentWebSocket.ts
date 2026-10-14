import { useEffect, useRef, useState } from "react";
import { getWebSocketUrl } from "../api/client";
import { AgentEvent, ConnectionState } from "../types";

export interface UseAgentWebSocketReturn {
  events: AgentEvent[];
  connectionState: ConnectionState;
  finalResult: string | null;
  error: string | null;
  isFinished: boolean;
}

export function useAgentWebSocket(taskId: string | null): UseAgentWebSocketReturn {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("closed");
  const [finalResult, setFinalResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isFinished, setIsFinished] = useState<boolean>(false);

  const seenEventIds = useRef<Set<string>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef<number>(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isTerminalRef = useRef<boolean>(false);

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      setConnectionState("closed");
      setFinalResult(null);
      setError(null);
      setIsFinished(false);
      seenEventIds.current.clear();
      isTerminalRef.current = false;
      return;
    }

    setEvents([]);
    setFinalResult(null);
    setError(null);
    setIsFinished(false);
    seenEventIds.current.clear();
    isTerminalRef.current = false;
    reconnectAttempts.current = 0;

    let isUnmounted = false;
    const activeTaskId = taskId;

    function connect() {
      if (isUnmounted || isTerminalRef.current) return;

      setConnectionState(reconnectAttempts.current > 0 ? "reconnecting" : "connecting");

      const wsUrl = getWebSocketUrl(activeTaskId);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isUnmounted) {
          ws.close();
          return;
        }
        reconnectAttempts.current = 0;
        setConnectionState("live");
      };

      ws.onmessage = (event) => {
        if (isUnmounted) return;
        try {
          const data = JSON.parse(event.data);
          if (data.event_type === "HEARTBEAT") {
            return;
          }

          const agentEvent: AgentEvent = data;
          if (seenEventIds.current.has(agentEvent.event_id)) {
            return;
          }
          seenEventIds.current.add(agentEvent.event_id);

          setEvents((prev) => [...prev, agentEvent]);

          if (agentEvent.event_type === "COMPLETED") {
            isTerminalRef.current = true;
            setIsFinished(true);
            const result =
              agentEvent.payload?.final_answer || agentEvent.message || "Completed";
            setFinalResult(result);
            setConnectionState("closed");
            ws.close(1000);
          } else if (agentEvent.event_type === "ERROR" && agentEvent.payload?.fatal) {
            isTerminalRef.current = true;
            setIsFinished(true);
            const errMsg = agentEvent.message || "A fatal workflow error occurred.";
            setError(errMsg);
            setConnectionState("closed");
            ws.close(1000);
          }
        } catch {
          // Ignore malformed JSON frames
        }
      };

      ws.onerror = () => {
        // Handled on close
      };

      ws.onclose = (event) => {
        if (isUnmounted) return;

        if (event.code === 4404) {
          setError("Task not found or invalid task ID.");
          setConnectionState("closed");
          setIsFinished(true);
          isTerminalRef.current = true;
          return;
        }

        if (isTerminalRef.current || event.code === 1000) {
          setConnectionState("closed");
          return;
        }

        if (reconnectAttempts.current < 5) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000);
          reconnectAttempts.current += 1;
          setConnectionState("reconnecting");
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
        } else {
          setConnectionState("closed");
          setError("Connection lost. Unable to reconnect after 5 attempts.");
        }
      };
    }

    connect();

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [taskId]);

  return { events, connectionState, finalResult, error, isFinished };
}
