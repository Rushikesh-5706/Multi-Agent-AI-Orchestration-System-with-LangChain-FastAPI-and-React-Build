import React, { useState } from "react";
import { Bot, Network } from "lucide-react";
import { submitTask } from "./api/client";
import { useAgentWebSocket } from "./hooks/useAgentWebSocket";
import { TaskForm } from "./components/TaskForm";
import { ConnectionBadge } from "./components/ConnectionBadge";
import { PlanPanel } from "./components/PlanPanel";
import { Timeline } from "./components/Timeline";
import { FinalResult } from "./components/FinalResult";

export const App: React.FC = () => {
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { events, connectionState, finalResult, error: wsError, isFinished } =
    useAgentWebSocket(currentTaskId);

  const handleTaskSubmit = async (prompt: string) => {
    setIsSubmitting(true);
    setFormError(null);
    try {
      const response = await submitTask(prompt);
      setCurrentTaskId(response.task_id);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to start orchestration task.";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-brand">
          <div className="brand-icon-wrapper" aria-hidden="true">
            <Bot className="brand-icon" />
          </div>
          <div>
            <h1 className="brand-title">Multi-Agent AI Orchestrator</h1>
            <p className="brand-subtitle">
              Collaborative reasoning with LangGraph, FastAPI, Celery and React
            </p>
          </div>
        </div>
        <div className="header-status">
          <ConnectionBadge state={connectionState} />
        </div>
      </header>

      <main className="app-main">
        <section className="input-section">
          <TaskForm
            onSubmit={handleTaskSubmit}
            isLoading={isSubmitting}
            error={formError}
          />
        </section>

        {currentTaskId && (
          <div className="task-info-bar">
            <span className="task-info-label">Active Task:</span>
            <code className="task-id-code">{currentTaskId}</code>
            {isFinished && <span className="task-finished-pill">Run Completed</span>}
          </div>
        )}

        {events.length > 0 && <PlanPanel events={events} />}

        <FinalResult finalResult={finalResult} error={wsError} />

        <section className="timeline-section" aria-label="Event stream">
          <div className="section-header">
            <Network className="section-icon" aria-hidden="true" />
            <h2 className="section-title">Live Agent Activity Log</h2>
          </div>
          <Timeline events={events} />
        </section>
      </main>

      <footer className="app-footer">
        <p>Stateful multi-agent system with real-time auditability and custom tool execution.</p>
      </footer>
    </div>
  );
};

export default App;
