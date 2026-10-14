import React from "react";
import { ConnectionState } from "../types";

interface ConnectionBadgeProps {
  state: ConnectionState;
}

export const ConnectionBadge: React.FC<ConnectionBadgeProps> = ({ state }) => {
  const getBadgeDetails = () => {
    switch (state) {
      case "live":
        return { label: "Live Connection", className: "badge-live" };
      case "connecting":
        return { label: "Connecting...", className: "badge-connecting" };
      case "reconnecting":
        return { label: "Reconnecting...", className: "badge-reconnecting" };
      case "closed":
      default:
        return { label: "Disconnected", className: "badge-closed" };
    }
  };

  const { label, className } = getBadgeDetails();

  return (
    <div className={`connection-badge ${className}`} role="status" aria-live="polite">
      <span className="badge-indicator" aria-hidden="true" />
      <span className="badge-text">{label}</span>
    </div>
  );
};
