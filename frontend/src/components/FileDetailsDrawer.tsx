import React from "react";
import { X, Download, Trash2, Layers, Eye } from "lucide-react";
import { StoredFile, Drive } from "../types";
import { formatBytes, formatDate, truncateHash, getDriveColor } from "../utils/format";

interface FileDetailsDrawerProps {
  file: StoredFile | null;
  drives: Drive[];
  onClose: () => void;
  onDownload: (file: StoredFile) => void;
  onDelete: (file: StoredFile) => void;
  onPreview: (file: StoredFile) => void;
}

export const FileDetailsDrawer: React.FC<FileDetailsDrawerProps> = ({
  file,
  drives,
  onClose,
  onDownload,
  onDelete,
  onPreview,
}) => {
  if (!file) return null;

  const chunks = file.chunks || [];

  return (
    <div
      className="animate-drawer"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: "min(560px, 100vw)",
        backgroundColor: "var(--bg-surface)",
        borderLeft: "1px solid var(--border-strong)",
        boxShadow: "var(--shadow-lg)",
        zIndex: 500,
        display: "flex",
        flexDirection: "column",
      }}
      role="dialog"
      aria-labelledby="drawer-title"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "18px 24px",
          borderBottom: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-surface-elevated)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <Layers size={18} color="var(--accent-cyan-solid)" />
          <h2 id="drawer-title" style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
            File Metadata & Stripes
          </h2>
        </div>

        <button
          className="btn-interactive"
          onClick={onClose}
          aria-label="Close details panel"
          style={{
            padding: "6px",
            color: "var(--text-muted)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Body content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: "18px" }}>
        {/* Metadata card */}
        <div
          style={{
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            padding: "16px",
            display: "flex",
            flexDirection: "column",
            gap: "10px",
            fontSize: "13px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>Filename:</span>
            <strong style={{ color: "var(--text-primary)", wordBreak: "break-all" }}>{file.name}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>Size:</span>
            <span style={{ fontFamily: "var(--font-mono)" }}>
              {formatBytes(file.size)} ({file.size.toLocaleString()} bytes)
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)" }}>Protection Level:</span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: "700",
                padding: "2px 8px",
                borderRadius: "var(--radius-sm)",
                backgroundColor:
                  file.protection_status === "parity"
                    ? "rgba(16, 185, 129, 0.12)"
                    : file.protection_status === "mirrored"
                    ? "rgba(6, 182, 212, 0.12)"
                    : "rgba(245, 158, 11, 0.12)",
                color:
                  file.protection_status === "parity"
                    ? "#10b981"
                    : file.protection_status === "mirrored"
                    ? "#06b6d4"
                    : "#f59e0b",
                border: `1px solid ${
                  file.protection_status === "parity"
                    ? "rgba(16, 185, 129, 0.3)"
                    : file.protection_status === "mirrored"
                    ? "rgba(6, 182, 212, 0.3)"
                    : "rgba(245, 158, 11, 0.3)"
                }`,
              }}
            >
              {file.protection_label ||
                (file.protection_status === "parity"
                  ? "Parity-protected"
                  : file.protection_status === "mirrored"
                  ? "Mirrored (2x copies)"
                  : "Unprotected (single drive)")}
            </span>
          </div>
          {file.unprotected_reason && (
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
              <span style={{ color: "var(--text-secondary)" }}>Reason:</span>
              <span style={{ color: "#f59e0b", fontWeight: "500", textAlign: "right", maxWidth: "60%" }}>
                {file.unprotected_reason}
              </span>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)" }}>Storage Mode:</span>
            <span
              style={{
                fontSize: "10px",
                fontWeight: "700",
                padding: "2px 8px",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "var(--bg-base)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-strong)",
              }}
            >
              {file.storage_mode === "whole"
                ? "Whole Object (AES-256-GCM)"
                : file.storage_mode === "mirrored"
                ? "Mirrored (2x Chunks)"
                : "Chunked + XOR Parity"}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)" }}>Health:</span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: "700",
                textTransform: "uppercase",
                padding: "2px 8px",
                borderRadius: "var(--radius-full)",
                backgroundColor:
                  file.health === "Healthy"
                    ? "var(--status-online-bg)"
                    : file.health === "Rebuilt from parity"
                    ? "var(--status-warning-bg)"
                    : "var(--status-offline-bg)",
                border: `1px solid ${
                  file.health === "Healthy"
                    ? "var(--status-online)"
                    : file.health === "Rebuilt from parity"
                    ? "var(--status-warning)"
                    : "var(--status-offline)"
                }`,
                color:
                  file.health === "Healthy"
                    ? "var(--status-online-text)"
                    : file.health === "Rebuilt from parity"
                    ? "var(--status-warning-text)"
                    : "var(--status-offline-text)",
              }}
            >
              {file.health || "Healthy"}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>Created:</span>
            <span>{formatDate(file.created_at)}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <span style={{ color: "var(--text-secondary)", fontSize: "11px", fontWeight: "600", textTransform: "uppercase" }}>
              Plaintext SHA-256
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                backgroundColor: "var(--bg-base)",
                padding: "6px 8px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-subtle)",
                wordBreak: "break-all",
                color: "var(--accent-cyan-solid)",
              }}
            >
              {file.sha256}
            </span>
          </div>
        </div>

        {/* Chunks and Stripe details */}
        <div>
          <div style={{ fontSize: "13px", fontWeight: "700", marginBottom: "10px", color: "var(--text-primary)" }}>
            Stored Chunks ({chunks.length})
          </div>

          <div
            style={{
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              overflow: "hidden",
              backgroundColor: "var(--bg-surface-elevated)",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ backgroundColor: "var(--bg-base)", borderBottom: "1px solid var(--border-subtle)" }}>
                  <th style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-secondary)", fontSize: "11px", textTransform: "uppercase" }}>Slot</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-secondary)", fontSize: "11px", textTransform: "uppercase" }}>Role</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-secondary)", fontSize: "11px", textTransform: "uppercase" }}>Drive</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-secondary)", fontSize: "11px", textTransform: "uppercase" }}>Hash</th>
                </tr>
              </thead>
              <tbody>
                {chunks.map((c) => {
                  const driveIdx = drives.findIndex((d) => d.id === c.drive_id);
                  const color = driveIdx >= 0 ? getDriveColor(driveIdx) : getDriveColor(c.drive_id);

                  return (
                    <tr
                      key={c.id}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        opacity: c.drive_offline ? 0.45 : 1,
                      }}
                    >
                      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)" }}>
                        S{c.stripe_index}:P{c.position}
                      </td>
                      <td style={{ padding: "8px 12px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 6px",
                            borderRadius: "var(--radius-sm)",
                            fontSize: "10px",
                            fontWeight: "700",
                            backgroundColor: c.is_parity ? "var(--bg-surface-active)" : "var(--bg-base)",
                            color: c.is_parity ? "var(--accent-cyan-solid)" : "var(--text-secondary)",
                            border: `1px solid ${c.is_parity ? "var(--accent-cyan-solid)" : "var(--border-strong)"}`,
                          }}
                        >
                          {c.is_parity ? "PARITY" : "DATA"}
                        </span>
                      </td>
                      <td style={{ padding: "8px 12px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span
                            style={{
                              width: "8px",
                              height: "8px",
                              borderRadius: "2px",
                              backgroundColor: color,
                            }}
                          />
                          <span>{c.drive_name || c.drive_id.slice(0, 8)}</span>
                          {c.drive_offline && (
                            <span style={{ fontSize: "10px", color: "var(--status-offline)", fontWeight: "600" }}>[OFFLINE]</span>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                        {truncateHash(c.sha256, 6)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Footer action buttons */}
      <div
        style={{
          padding: "14px 24px",
          borderTop: "1px solid var(--border-subtle)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          backgroundColor: "var(--bg-surface-elevated)",
        }}
      >
        <button
          className="btn-interactive"
          onClick={() => onDelete(file)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            color: "var(--status-offline-text)",
            backgroundColor: "var(--status-offline-bg)",
            border: "1px solid var(--status-offline)",
            fontSize: "12px",
            fontWeight: "600",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <Trash2 size={14} />
          <span>Delete File</span>
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            className="btn-interactive"
            onClick={() => onPreview(file)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 14px",
              backgroundColor: "var(--bg-base)",
              border: "1px solid var(--border-subtle)",
              color: "var(--accent-cyan-solid)",
              fontWeight: "600",
              fontSize: "12px",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <Eye size={14} />
            <span>Preview File</span>
          </button>

          <button
            className="btn-interactive"
            onClick={() => onDownload(file)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 16px",
              backgroundColor: "var(--accent-cyan-solid)",
              color: "#ffffff",
              fontWeight: "600",
              fontSize: "12px",
              borderRadius: "var(--radius-sm)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <Download size={14} />
            <span>Download & Verify</span>
          </button>
        </div>
      </div>
    </div>
  );
};
