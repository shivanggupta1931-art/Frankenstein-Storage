import React, { useState } from "react";
import { Lock, Shield, Eye, EyeOff, KeyRound, AlertCircle, HardDrive, Cloud, ShieldAlert, Settings } from "lucide-react";
import { api } from "../services/api";

interface VaultLockScreenProps {
  onUnlock: (password: string) => Promise<void>;
  onOpenSettings?: () => void;
}

export const VaultLockScreen: React.FC<VaultLockScreenProps> = ({ onUnlock, onOpenSettings }) => {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError("Please enter your vault master password");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await onUnlock(password);
      setPassword("");
    } catch (err: any) {
      setError(err.message || "Failed to unlock vault. Incorrect master password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="animate-fade-in"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 20px 80px",
        minHeight: "75vh",
      }}
    >
      <div
        className="animate-slide-up"
        style={{
          width: "100%",
          maxWidth: "480px",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.4), 0 0 0 1px var(--border-subtle)",
          padding: "36px 32px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: "24px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Top glowing ambient accent */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: "15%",
            right: "15%",
            height: "3px",
            background: "linear-gradient(90deg, transparent, var(--accent-cyan-solid), #3b82f6, transparent)",
            borderRadius: "3px",
          }}
        />

        {/* Shield & Lock Icon with ambient badge */}
        <div style={{ position: "relative" }}>
          <div
            style={{
              width: "72px",
              height: "72px",
              borderRadius: "50%",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "2px solid var(--border-strong)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--accent-cyan-solid)",
              boxShadow: "0 0 24px rgba(6, 182, 212, 0.2)",
            }}
          >
            <Lock size={32} />
          </div>
          <div
            style={{
              position: "absolute",
              bottom: "-4px",
              right: "-4px",
              width: "26px",
              height: "26px",
              borderRadius: "50%",
              backgroundColor: "#ef4444",
              border: "2px solid var(--bg-surface)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ffffff",
            }}
            title="Dashboard Locked"
          >
            <ShieldAlert size={14} />
          </div>
        </div>

        {/* Title & Security description */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
            <h1 style={{ fontSize: "20px", fontWeight: "800", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              Storage Vault is Locked
            </h1>
          </div>
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", lineHeight: "1.5", margin: 0 }}>
            Zero-knowledge AES-256 encryption is active. All drives, files, encrypted chunks, and operations are sealed. Enter your master password to unlock the dashboard.
          </p>
        </div>

        {/* Unlock Form */}
        <form
          onSubmit={handleSubmit}
          style={{
            width: "100%",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
          }}
        >
          {error && (
            <div
              className="animate-slide-up"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                padding: "12px 14px",
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.4)",
                borderRadius: "var(--radius-md)",
                color: "#f87171",
                fontSize: "12px",
                textAlign: "left",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span style={{ fontWeight: 600 }}>
                  {error.toLowerCase().includes("fetch") ? "Cannot connect to backend server" : error}
                </span>
              </div>
              {error.toLowerCase().includes("fetch") && (
                <div style={{ fontSize: "11px", color: "var(--text-secondary)", lineHeight: "1.5" }}>
                  <span>Attempted URL: </span>
                  <code style={{ color: "var(--text-primary)", backgroundColor: "rgba(0,0,0,0.2)", padding: "1px 4px", borderRadius: "3px" }}>
                    {api.getBaseUrl()}
                  </code>
                  <p style={{ margin: "6px 0 0" }}>
                    Your browser cannot reach the backend. If this site is loaded over HTTPS on Vercel, browsers block unencrypted HTTP/localhost connections (Mixed Content), or your backend server is offline.
                  </p>
                  {onOpenSettings && (
                    <div style={{ marginTop: "8px" }}>
                      <button
                        type="button"
                        onClick={onOpenSettings}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "11px",
                          fontWeight: 600,
                          padding: "5px 10px",
                          backgroundColor: "var(--accent-cyan-solid)",
                          color: "#0f172a",
                          borderRadius: "var(--radius-sm)",
                          border: "none",
                          cursor: "pointer",
                        }}
                      >
                        <Settings size={12} />
                        <span>Configure Backend API URL & Token</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div style={{ textAlign: "left", display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              htmlFor="vault-password-input"
              style={{
                fontSize: "12px",
                fontWeight: "600",
                color: "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <KeyRound size={13} />
              <span>Master Encryption Password</span>
            </label>
            <div style={{ position: "relative", width: "100%" }}>
              <input
                id="vault-password-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter master password..."
                autoFocus
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "12px 42px 12px 14px",
                  fontSize: "14px",
                  backgroundColor: "var(--bg-base)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text-primary)",
                  outline: "none",
                  transition: "border-color 0.15s ease",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: "absolute",
                  right: "12px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  padding: "4px",
                }}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {/* Demo Password Hint / Auto-Fill */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "6px 10px",
                backgroundColor: "rgba(6, 182, 212, 0.08)",
                border: "1px dashed rgba(6, 182, 212, 0.3)",
                borderRadius: "var(--radius-sm)",
                fontSize: "11px",
                color: "var(--text-secondary)",
              }}
            >
              <span>
                Demo Master Password:{" "}
                <code
                  onClick={() => setPassword("iitr@123")}
                  style={{
                    color: "var(--accent-cyan-solid)",
                    cursor: "pointer",
                    fontWeight: 700,
                    letterSpacing: "0.5px",
                  }}
                  title="Click to auto-fill"
                >
                  iitr@123
                </code>
              </span>
              <button
                type="button"
                onClick={() => setPassword("iitr@123")}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent-cyan-solid)",
                  cursor: "pointer",
                  fontSize: "11px",
                  fontWeight: 600,
                  textDecoration: "underline",
                  padding: 0,
                }}
              >
                Auto-fill
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn-interactive"
            disabled={loading || !password.trim()}
            style={{
              width: "100%",
              padding: "12px 20px",
              fontSize: "13px",
              fontWeight: "700",
              color: "#ffffff",
              backgroundColor: "var(--accent-cyan-solid)",
              border: "1px solid var(--accent-cyan-hover)",
              borderRadius: "var(--radius-md)",
              cursor: loading || !password.trim() ? "not-allowed" : "pointer",
              opacity: loading || !password.trim() ? 0.6 : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              boxShadow: "0 2px 8px rgba(6, 182, 212, 0.35)",
              transition: "all 0.15s ease",
            }}
          >
            <Lock size={15} />
            <span>{loading ? "Deriving Key & Unlocking..." : "Unlock Dashboard"}</span>
          </button>
        </form>

        {/* Security badges */}
        <div
          style={{
            width: "100%",
            paddingTop: "16px",
            borderTop: "1px solid var(--border-subtle)",
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "10px",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
            <Shield size={16} color="var(--accent-cyan-solid)" />
            <span style={{ fontWeight: "600" }}>Zero-Knowledge</span>
            <span style={{ fontSize: "10px" }}>scrypt + AES-256</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
            <HardDrive size={16} color="#3b82f6" />
            <span style={{ fontWeight: "600" }}>Hardware Vault</span>
            <span style={{ fontSize: "10px" }}>Local SSD + USB</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
            <Cloud size={16} color="#10b981" />
            <span style={{ fontWeight: "600" }}>Multi-Cloud</span>
            <span style={{ fontSize: "10px" }}>iCloud + GDrive + S3</span>
          </div>
        </div>
      </div>
    </div>
  );
};
