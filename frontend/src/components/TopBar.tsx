import React from "react";
import { Lock, Key, RefreshCw, Activity, Sun, Moon } from "lucide-react";

interface TopBarProps {
  unlocked: boolean;
  healthOk: boolean;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onOpenUnlock: () => void;
  onLock: () => void;
  onOpenSettings: () => void;
  onOpenActivity: () => void;
  onVerifyIntegrity: () => void;
  verifying: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({
  unlocked,
  healthOk,
  theme,
  onToggleTheme,
  onOpenUnlock,
  onLock,
  onOpenSettings,
  onOpenActivity,
  onVerifyIntegrity,
  verifying,
}) => {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 28px",
        backgroundColor: "var(--bg-surface)",
        borderBottom: "1px solid var(--border-subtle)",
        position: "sticky",
        top: 0,
        zIndex: 100,
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Brand logo & title */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "var(--radius-md)",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "18px",
            boxShadow: "var(--shadow-sm)",
          }}
          aria-hidden="true"
        >
          🧟
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <h1 style={{ fontSize: "15px", fontWeight: "700", letterSpacing: "0.02em", color: "var(--text-primary)" }}>
              FRANKENSTEIN <span style={{ color: "var(--accent-cyan-solid)" }}>STORAGE</span>
            </h1>
            <span
              style={{
                fontSize: "10px",
                fontWeight: "700",
                textTransform: "uppercase",
                padding: "2px 6px",
                backgroundColor: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                color: "var(--text-muted)",
                letterSpacing: "0.05em",
              }}
            >
              v1.0
            </span>
          </div>
          <p style={{ fontSize: "11px", color: "var(--text-muted)", letterSpacing: "0.02em" }}>
            Pooled • Encrypted • Parity-Protected
          </p>
        </div>
      </div>

      {/* Status pills and actions */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        {/* Backend health status pill */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "6px 12px",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-full)",
            fontSize: "12px",
            fontWeight: "500",
          }}
        >
          <span
            className={healthOk ? "ping-dot" : ""}
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              backgroundColor: healthOk ? "var(--status-online)" : "var(--status-offline)",
              color: healthOk ? "var(--status-online)" : "var(--status-offline)",
            }}
            aria-hidden="true"
          />
          <span style={{ color: healthOk ? "var(--text-secondary)" : "var(--status-offline)" }}>
            {healthOk ? "127.0.0.1:8765" : "Disconnected"}
          </span>
        </div>

        {/* Integrity verify button */}
        <button
          className="btn-interactive"
          onClick={onVerifyIntegrity}
          disabled={verifying || !unlocked}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            fontSize: "12px",
            fontWeight: "500",
            color: unlocked ? "var(--text-primary)" : "var(--text-muted)",
            opacity: unlocked ? 1 : 0.4,
            cursor: unlocked ? "pointer" : "not-allowed",
          }}
          aria-label="Run storage parity and integrity audit"
          title={unlocked ? "Verify parity and chunk integrity" : "Unlock vault to run integrity check"}
        >
          <RefreshCw size={13} className={verifying ? "animate-spin" : ""} />
          <span>Verify</span>
        </button>

        {/* Activity log button */}
        <button
          className="btn-interactive"
          onClick={onOpenActivity}
          disabled={!unlocked}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            fontSize: "12px",
            fontWeight: "500",
            color: unlocked ? "var(--text-primary)" : "var(--text-muted)",
            opacity: unlocked ? 1 : 0.4,
            cursor: unlocked ? "pointer" : "not-allowed",
          }}
          aria-label="View activity audit log"
          title={unlocked ? "View operation log" : "Unlock vault to view activity log"}
        >
          <Activity size={13} />
          <span>Activity</span>
        </button>

        {/* Token config button */}
        <button
          className="btn-interactive"
          onClick={onOpenSettings}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            fontSize: "12px",
            fontWeight: "500",
            color: "var(--text-primary)",
          }}
          aria-label="Configure API connection and session token"
          title="Session Token Settings"
        >
          <Key size={13} />
          <span>Token</span>
        </button>

        {/* Dark / Light theme toggle */}
        <button
          className="btn-interactive"
          onClick={onToggleTheme}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "32px",
            height: "32px",
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            color: "var(--text-secondary)",
          }}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? <Sun size={15} color="var(--status-warning)" /> : <Moon size={15} color="var(--accent-cyan-solid)" />}
        </button>

        {/* Vault lock / unlock button */}
        {unlocked ? (
          <button
            className="btn-interactive"
            onClick={onLock}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              backgroundColor: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.4)",
              borderRadius: "var(--radius-md)",
              color: "#ef4444",
              fontSize: "12px",
              fontWeight: "600",
              cursor: "pointer",
            }}
            aria-label="Lock storage vault"
            title="Lock dashboard & wipe encryption keys from memory"
          >
            <Lock size={14} />
            <span>Lock Vault</span>
          </button>
        ) : (
          <button
            className="btn-interactive"
            onClick={onOpenUnlock}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              backgroundColor: "var(--accent-cyan-solid)",
              border: "1px solid var(--accent-cyan-hover)",
              borderRadius: "var(--radius-md)",
              color: "#ffffff",
              fontSize: "12px",
              fontWeight: "600",
              boxShadow: "var(--shadow-sm)",
            }}
            aria-label="Unlock storage vault"
            title="Enter master password to unlock dashboard"
          >
            <Lock size={14} />
            <span>Unlock Vault</span>
          </button>
        )}
      </div>
    </header>
  );
};
