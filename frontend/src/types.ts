export type EventType =
  | "AGENT_THOUGHT"
  | "AGENT_ACTION"
  | "TOOL_INVOCATION"
  | "TOOL_RESULT"
  | "ERROR"
  | "COMPLETED"
  | "HEARTBEAT";

export interface EventPayload {
  kind?: string;
  steps?: string[];
  step_index?: number;
  step?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: string;
  is_error?: boolean;
  duration_ms?: number;
  node?: string;
  execution?: string;
  fatal?: boolean;
  final_result?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface AgentEvent {
  event_id: string;
  sequence: number;
  task_id: string;
  event_type: EventType;
  agent: string;
  message: string;
  payload: EventPayload;
  timestamp: string;
}

export type ConnectionState = "connecting" | "live" | "reconnecting" | "closed";

export interface TaskResponse {
  task_id: string;
}
