import React, { useEffect, useRef, useState } from "react";
import { AgentEvent } from "../types";
import { EventCard } from "./EventCard";

interface TimelineProps {
  events: AgentEvent[];
}

export const Timeline: React.FC<TimelineProps> = ({ events }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 60;
    setAutoScroll(isAtBottom);
  };

  useEffect(() => {
    if (
      autoScroll &&
      bottomRef.current &&
      typeof bottomRef.current.scrollIntoView === "function"
    ) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, autoScroll]);

  if (events.length === 0) {
    return (
      <div className="empty-timeline">
        <p>No agent events yet. Submit a prompt above to start the orchestration workflow.</p>
      </div>
    );
  }

  return (
    <div
      className="timeline-container"
      ref={containerRef}
      onScroll={handleScroll}
      aria-live="polite"
      aria-label="Agent execution timeline"
    >
      <div className="timeline-track">
        {events.map((event) => (
          <EventCard key={event.event_id || `${event.sequence}-${event.timestamp}`} event={event} />
        ))}
        <div ref={bottomRef} className="timeline-bottom-anchor" />
      </div>
    </div>
  );
};
