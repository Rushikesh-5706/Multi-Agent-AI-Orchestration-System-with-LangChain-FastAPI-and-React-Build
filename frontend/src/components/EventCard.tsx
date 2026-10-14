import React, { useState } from "react";
import {
  Compass,
  Search,
  FileText,
  Wrench,
  AlertOctagon,
  ChevronDown,
  ChevronRight,
  Clock,
  ArrowRight,
} from "lucide-react";
import { AgentEvent } from "../types";

interface EventCardProps {
  event: AgentEvent;
}

export const EventCard: React.FC<EventCardProps> = ({ event }) => {
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  // Transition event
  if (event.event_type === "AGENT_ACTION" && event.payload?.kind === "transition") {
    return (
      <div className="timeline-transition">
        <span className="transition-line" />
        <span className="transition-badge">
          Transition <ArrowRight className="transition-icon" aria-hidden="true" /> {event.payload.node}
        </span>
        <span className="transition-line" />
      </div>
    );
  }

  const getAgentTheme = () => {
    switch (event.agent.toLowerCase()) {
      case "planner":
        return {
          icon: Compass,
          accentClass: "theme-planner",
          label: "Planner",
        };
      case "researcher":
        return {
          icon: Search,
          accentClass: "theme-researcher",
          label: "Researcher",
        };
      case "synthesizer":
        return {
          icon: FileText,
          accentClass: "theme-synthesizer",
          label: "Synthesizer",
        };
      case "tool_executor":
        return {
          icon: Wrench,
          accentClass: "theme-tool",
          label: "Tool Execution",
        };
      default:
        return {
          icon: event.event_type === "ERROR" ? AlertOctagon : Clock,
          accentClass: event.event_type === "ERROR" ? "theme-error" : "theme-default",
          label: event.agent || "System",
        };
    }
  };

  const { icon: Icon, accentClass, label } = getAgentTheme();
  const isToolInvocation = event.event_type === "TOOL_INVOCATION";
  const isToolResult = event.event_type === "TOOL_RESULT";
  const hasToolDetails = isToolInvocation || isToolResult;
  const isError = event.event_type === "ERROR" || event.payload?.is_error;

  return (
    <article className={`event-card ${accentClass} ${isError ? "card-error" : ""}`}>
      <div className="event-header">
        <div className="event-meta">
          <span className="event-icon-container" aria-hidden="true">
            <Icon className="event-type-icon" />
          </span>
          <span className="event-agent-name">{label}</span>
          <span className="event-type-tag">{event.event_type}</span>
          <span className="event-seq">#{event.sequence}</span>
        </div>
        <time className="event-timestamp" dateTime={event.timestamp}>
          {new Date(event.timestamp).toLocaleTimeString()}
        </time>
      </div>

      <div className="event-body">
        <p className="event-message">{event.message}</p>

        {isToolResult && (
          <div className="tool-summary-row">
            <span className="tool-name-badge">{event.payload?.tool}</span>
            {event.payload?.duration_ms !== undefined && (
              <span className="tool-duration">
                <Clock className="mini-icon" aria-hidden="true" />
                {event.payload.duration_ms} ms
              </span>
            )}
            {event.payload?.execution && (
              <span className="tool-execution-type">({event.payload.execution})</span>
            )}
          </div>
        )}

        {hasToolDetails && (
          <div className="collapsible-details">
            <button
              type="button"
              className="details-toggle"
              onClick={() => setIsDetailsOpen(!isDetailsOpen)}
              aria-expanded={isDetailsOpen}
            >
              {isDetailsOpen ? (
                <ChevronDown className="toggle-icon" aria-hidden="true" />
              ) : (
                <ChevronRight className="toggle-icon" aria-hidden="true" />
              )}
              <span>{isDetailsOpen ? "Hide technical details" : "View parameters and payload"}</span>
            </button>

            {isDetailsOpen && (
              <div className="details-content">
                {event.payload?.arguments && (
                  <div className="detail-section">
                    <span className="detail-label">Arguments:</span>
                    <pre className="code-block">
                      {JSON.stringify(event.payload.arguments, null, 2)}
                    </pre>
                  </div>
                )}
                {event.payload?.result && (
                  <div className="detail-section">
                    <span className="detail-label">Result:</span>
                    <pre className="code-block result-block">
                      {event.payload.result}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
};
