import React from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { ToastMessage } from "../types";

interface ToastsProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const Toasts: React.FC<ToastsProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: "24px",
        right: "24px",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        maxWidth: "380px",
        width: "calc(100% - 48px)",
      }}
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((toast) => {
        const isError = toast.type === "error";
        const isSuccess = toast.type === "success";

        return (
          <div
            key={toast.id}
            className="animate-toast"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 14px",
              backgroundColor: "var(--bg-surface)",
              border: `1px solid ${isError ? "var(--status-offline)" : isSuccess ? "var(--status-online)" : "var(--accent-cyan-solid)"}`,
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-lg)",
              color: "var(--text-primary)",
              fontSize: "13px",
            }}
          >
            {isSuccess && <CheckCircle2 size={16} color="var(--status-online)" aria-hidden="true" />}
            {isError && <AlertTriangle size={16} color="var(--status-offline)" aria-hidden="true" />}
            {!isSuccess && !isError && <Info size={16} color="var(--accent-cyan-solid)" aria-hidden="true" />}

            <div style={{ flex: 1, wordBreak: "break-word", lineHeight: 1.4 }}>{toast.message}</div>

            <button
              className="btn-interactive"
              onClick={() => onDismiss(toast.id)}
              aria-label="Dismiss notification"
              style={{
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
                padding: "2px",
              }}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
