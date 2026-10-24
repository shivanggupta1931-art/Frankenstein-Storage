import React, { useState, useEffect } from "react";
import { Key, X, Check, Sliders, Trash2 } from "lucide-react";
import { api } from "../services/api";
import { formatBytes } from "../utils/format";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const [token, setToken] = useState(api.getToken());
  const [baseUrl, setBaseUrl] = useState(api.getBaseUrl());
  const [preferredMode, setPreferredMode] = useState<"whole" | "chunked_parity" | "mirrored" | "none">("none");
  const [thresholdBytes, setThresholdBytes] = useState<number>(1048576);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setToken(api.getToken());
      setBaseUrl(api.getBaseUrl());
      api.getUploadPreference()
        .then((pref) => {
          setPreferredMode(pref.preferred_mode || "none");
          setThresholdBytes(pref.threshold_bytes || 1048576);
        })
        .catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      api.setToken(token);
      api.setBaseUrl(baseUrl);
      const modeToSave = preferredMode === "none" ? null : preferredMode;
      await api.setUploadPreference(modeToSave);
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const handleClearPreference = async () => {
    setPreferredMode("none");
    await api.setUploadPreference(null);
    onSaved();
  };

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
      aria-labelledby="settings-title"
    >
      <div
        className="animate-modal"
        style={{
          width: "100%",
          maxWidth: "460px",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-lg)",
          padding: "22px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <Key size={18} color="var(--accent-cyan-solid)" />
            <h2 id="settings-title" style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
              Settings & Preferences
            </h2>
          </div>
          <button className="btn-interactive" onClick={onClose} aria-label="Close settings" style={{ color: "var(--text-muted)", padding: "4px" }}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <label htmlFor="base-url-input" style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
              API BASE URL
            </label>
            <input
              id="base-url-input"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                fontFamily: "var(--font-mono)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          <div>
            <label htmlFor="session-token-input" style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
              SESSION BEARER TOKEN
            </label>
            <input
              id="session-token-input"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste token from dev console..."
              style={{
                width: "100%",
                padding: "8px 12px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                fontFamily: "var(--font-mono)",
                color: "var(--text-primary)",
              }}
            />
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
              Printed in terminal on backend startup: <code>SESSION TOKEN: &lt;token&gt;</code>
            </div>
          </div>

          {/* Upload Decisions Preference Section */}
          <div
            style={{
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <Sliders size={13} color="var(--accent-cyan-solid)" />
                <span style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)" }}>
                  Default Upload Mode
                </span>
              </div>
              {preferredMode !== "none" && (
                <button
                  type="button"
                  className="btn-interactive"
                  onClick={handleClearPreference}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    fontSize: "11px",
                    color: "var(--status-offline-text)",
                    backgroundColor: "var(--status-offline-bg)",
                    border: "1px solid var(--status-offline)",
                    borderRadius: "var(--radius-sm)",
                    padding: "2px 6px",
                  }}
                  title="Clear saved preference"
                >
                  <Trash2 size={11} />
                  <span>Clear preference</span>
                </button>
              )}
            </div>

            <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: 0 }}>
              Files &lt; {formatBytes(thresholdBytes)} recommend Whole Object; files &ge; {formatBytes(thresholdBytes)} recommend Chunked + Parity.
            </p>

            <select
              id="upload-preference-select"
              value={preferredMode}
              onChange={(e) => setPreferredMode(e.target.value as any)}
              style={{
                width: "100%",
                padding: "8px 12px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                color: "var(--text-primary)",
              }}
            >
              <option value="none">Always ask on upload (Smart Decision Dialog)</option>
              <option value="whole">Always use Whole Encrypted Object</option>
              <option value="mirrored">Always use Mirrored (2x copies)</option>
              <option value="chunked_parity">Always use Chunked + XOR Parity</option>
            </select>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "4px" }}>
            <button
              type="button"
              className="btn-interactive"
              onClick={onClose}
              style={{ padding: "6px 12px", fontSize: "12px", color: "var(--text-secondary)" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-interactive"
              disabled={saving}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 16px",
                backgroundColor: "var(--accent-cyan-solid)",
                color: "#ffffff",
                fontWeight: "600",
                fontSize: "12px",
                borderRadius: "var(--radius-sm)",
                opacity: saving ? 0.7 : 1,
              }}
            >
              <Check size={14} />
              <span>{saving ? "Saving..." : "Save Settings"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
