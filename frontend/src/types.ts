export type EventType =
  | "AGENT_THOUGHT"
  | "AGENT_ACTION"
  | "TOOL_INVOCATION"
  | "TOOL_RESULT"
  | "ERROR"
  | "COMPLETED"
  | "HEARTBEAT";

export interface AgentEvent {
  event_id: string;
  sequence: number;
  task_id: string;
  event_type: EventType;
  agent: string;
  message: string;
  payload: Record<string, any>;
  timestamp: string;
}

export type ConnectionState = "connecting" | "live" | "reconnecting" | "closed";

export interface TaskResponse {
  task_id: string;
}

export interface TaskRunData {
  id: string;
  prompt: string;
  status: string;
  final_result: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  events: AgentEvent[];
}
