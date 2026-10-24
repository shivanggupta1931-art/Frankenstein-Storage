import React, { useEffect, useState } from "react";
import { Activity, X, RefreshCw } from "lucide-react";
import { ActivityItem } from "../types";
import { api } from "../services/api";
import { formatDate } from "../utils/format";

interface ActivityModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ActivityModal: React.FC<ActivityModalProps> = ({ isOpen, onClose }) => {
  const [logs, setLogs] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const items = await api.getActivity();
      setLogs(items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadLogs();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="animate-fade-in"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "20px",
      }}
      role="dialog"
      aria-labelledby="activity-title"
    >
      <div
        className="animate-modal"
        style={{
          width: "100%",
          maxWidth: "640px",
          maxHeight: "80vh",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-lg)",
          padding: "22px",
          display: "flex",
          flexDirection: "column",
          gap: "14px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <Activity size={18} color="var(--accent-cyan-solid)" />
            <h2 id="activity-title" style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
              Operation Audit Log
            </h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button
              className="btn-interactive"
              onClick={loadLogs}
              disabled={loading}
              aria-label="Refresh activity logs"
              style={{
                padding: "4px 8px",
                color: "var(--text-secondary)",
                fontSize: "12px",
                display: "flex",
                alignItems: "center",
                gap: "4px",
                backgroundColor: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              <span>Refresh</span>
            </button>
            <button className="btn-interactive" onClick={onClose} aria-label="Close activity log" style={{ color: "var(--text-muted)", padding: "4px" }}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "6px" }}>
          {logs.length === 0 && !loading && (
            <div style={{ textAlign: "center", padding: "32px", color: "var(--text-muted)", fontSize: "12px" }}>
              No recorded activity yet.
            </div>
          )}

          {logs.map((item) => (
            <div
              key={item.id}
              className="card-interactive"
              style={{
                backgroundColor: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 12px",
                display: "flex",
                flexDirection: "column",
                gap: "3px",
                fontSize: "12px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: "700", color: "var(--accent-cyan-solid)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                  {item.operation}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>{formatDate(item.created_at)}</span>
              </div>
              <div style={{ color: "var(--text-secondary)", wordBreak: "break-all", fontSize: "11px" }}>{item.details}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
