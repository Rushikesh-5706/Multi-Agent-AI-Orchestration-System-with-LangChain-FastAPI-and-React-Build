import { TaskResponse, TaskRunData } from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

export function getWebSocketUrl(taskId: string): string {
  const parsed = new URL(API_BASE_URL);
  const wsProtocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  return `${wsProtocol}//${parsed.host}/api/ws/${taskId}`;
}

export async function submitTask(prompt: string): Promise<TaskResponse> {
  const response = await fetch(`${API_BASE_URL}/api/tasks`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === "string"
          ? errJson.detail
          : JSON.stringify(errJson.detail);
      }
    } catch {
      // Fallback to generic message
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export async function getTask(taskId: string): Promise<TaskRunData> {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch task: ${response.status}`);
  }
  return response.json();
}
