import React, { useState } from "react";
import { Lock, AlertCircle } from "lucide-react";

interface UnlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUnlock: (password: string) => Promise<void>;
}

export const UnlockModal: React.FC<UnlockModalProps> = ({ isOpen, onClose, onUnlock }) => {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError("Please enter a master password");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await onUnlock(password);
      setPassword("");
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to unlock vault. Incorrect password.");
    } finally {
      setLoading(false);
    }
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
      aria-labelledby="unlock-title"
    >
      <div
        className="animate-modal"
        style={{
          width: "100%",
          maxWidth: "400px",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-lg)",
          padding: "24px",
          display: "flex",
          flexDirection: "column",
          gap: "18px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              width: "38px",
              height: "38px",
              borderRadius: "var(--radius-md)",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--accent-cyan-solid)",
            }}
          >
            <Lock size={18} />
          </div>
          <div>
            <h2 id="unlock-title" style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
              Unlock Storage Vault
            </h2>
            <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Derives AES-256 master key in-memory via scrypt
            </p>
          </div>
        </div>

        {error && (
          <div
            className="animate-slide-up"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 12px",
              backgroundColor: "var(--status-offline-bg)",
              border: "1px solid var(--status-offline)",
              borderRadius: "var(--radius-sm)",
              color: "var(--status-offline-text)",
              fontSize: "12px",
            }}
          >
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div>
            <label
              htmlFor="vault-password"
              style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}
            >
              MASTER PASSWORD
            </label>
            <input
              id="vault-password"
              type="password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter master password..."
              style={{
                width: "100%",
                padding: "8px 12px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                color: "var(--text-primary)",
              }}
            />
            <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
              If starting for the first time, this password initializes your vault.
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "4px" }}>
            <button
              type="button"
              className="btn-interactive"
              onClick={onClose}
              style={{
                padding: "7px 14px",
                fontSize: "12px",
                color: "var(--text-secondary)",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-interactive"
              disabled={loading}
              style={{
                padding: "7px 18px",
                backgroundColor: "var(--accent-cyan-solid)",
                color: "#ffffff",
                fontWeight: "600",
                fontSize: "12px",
                borderRadius: "var(--radius-sm)",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Deriving Key..." : "Unlock Vault"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
