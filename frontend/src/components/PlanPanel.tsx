import React from "react";
import { CheckCircle2, Circle, Clock, ListChecks } from "lucide-react";
import { AgentEvent } from "../types";

interface PlanPanelProps {
  events: AgentEvent[];
}

export const PlanPanel: React.FC<PlanPanelProps> = ({ events }) => {
  let steps: string[] = [];
  let currentStepIndex = -1;
  const completedStepIndices = new Set<number>();

  for (const event of events) {
    if (event.event_type === "AGENT_THOUGHT" && event.payload?.kind === "plan") {
      if (Array.isArray(event.payload.steps)) {
        steps = event.payload.steps;
      }
    } else if (event.payload?.kind === "step_started") {
      currentStepIndex = event.payload.step_index;
    } else if (event.payload?.kind === "finding") {
      completedStepIndices.add(event.payload.step_index);
    }
  }

  if (steps.length === 0) {
    return null;
  }

  return (
    <section className="plan-panel" aria-label="Execution plan checklist">
      <div className="plan-header">
        <ListChecks className="plan-header-icon" aria-hidden="true" />
        <h3 className="plan-title">Execution Plan ({completedStepIndices.size}/{steps.length})</h3>
      </div>
      <ol className="plan-list">
        {steps.map((stepText, idx) => {
          const isDone = completedStepIndices.has(idx);
          const isCurrent = currentStepIndex === idx && !isDone;

          return (
            <li
              key={idx}
              className={`plan-item ${isDone ? "plan-item-done" : isCurrent ? "plan-item-active" : "plan-item-pending"}`}
            >
              <div className="plan-item-status" aria-hidden="true">
                {isDone ? (
                  <CheckCircle2 className="step-icon done-icon" />
                ) : isCurrent ? (
                  <Clock className="step-icon active-icon" />
                ) : (
                  <Circle className="step-icon pending-icon" />
                )}
              </div>
              <span className="plan-item-text">
                <span className="step-number">Step {idx + 1}:</span> {stepText}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
