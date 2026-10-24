import React, { useState, useEffect } from "react";
import {
  FileText,
  Shield,
  Layers,
  Sparkles,
  AlertTriangle,
  X,
  UploadCloud,
} from "lucide-react";
import { formatBytes } from "../utils/format";

export type StorageMode = "whole" | "chunked_parity";

interface UploadDecisionModalProps {
  isOpen: boolean;
  file: File | null;
  onlineDrivesCount: number;
  thresholdBytes: number;
  onConfirm: (mode: StorageMode, remember: boolean) => void;
  onCancel: () => void;
}

export const UploadDecisionModal: React.FC<UploadDecisionModalProps> = ({
  isOpen,
  file,
  onlineDrivesCount,
  thresholdBytes,
  onConfirm,
  onCancel,
}) => {
  if (!isOpen || !file) return null;

  const isSmallFile = file.size < thresholdBytes;
  const recommendedMode: StorageMode = isSmallFile ? "whole" : "chunked_parity";

  const [selectedMode, setSelectedMode] = useState<StorageMode>(recommendedMode);
  const [remember, setRemember] = useState(false);

  // Sync recommendation whenever a new file is chosen
  useEffect(() => {
    setSelectedMode(recommendedMode);
    setRemember(false);
  }, [file?.name, file?.size, thresholdBytes]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  const canUseChunked = onlineDrivesCount >= 3;
  const isSelectedModeInvalid = selectedMode === "chunked_parity" && !canUseChunked;

  const handleConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    if (isSelectedModeInvalid) return;
    onConfirm(selectedMode, remember);
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
      aria-labelledby="upload-decision-title"
      aria-modal="true"
    >
      <div
        className="animate-modal"
        style={{
          width: "100%",
          maxWidth: "520px",
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
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
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
                color: "var(--accent-cyan-solid)",
              }}
            >
              <UploadCloud size={18} />
            </div>
            <div>
              <h2
                id="upload-decision-title"
                style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}
              >
                Upload Storage Decision
              </h2>
              <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                Choose placement strategy for this file
              </p>
            </div>
          </div>
          <button
            className="btn-interactive"
            onClick={onCancel}
            aria-label="Cancel upload"
            style={{ color: "var(--text-muted)", padding: "4px", borderRadius: "var(--radius-sm)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Selected file preview */}
        <div
          style={{
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            padding: "12px 14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
            <FileText size={18} color="var(--accent-cyan-solid)" style={{ flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: "13px",
                  fontWeight: "600",
                  color: "var(--text-primary)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={file.name}
              >
                {file.name}
              </div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "1px" }}>
                Size: <span style={{ fontFamily: "var(--font-mono)" }}>{formatBytes(file.size)}</span>
              </div>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              padding: "3px 8px",
              backgroundColor: "var(--bg-base)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-sm)",
              fontSize: "10px",
              fontWeight: "700",
              color: "var(--accent-cyan-solid)",
              flexShrink: 0,
            }}
          >
            <Sparkles size={11} />
            <span>Rec: {recommendedMode === "whole" ? "Whole" : "Parity"}</span>
          </div>
        </div>

        {/* Recommendation reason */}
        <div
          style={{
            fontSize: "12px",
            color: "var(--text-secondary)",
            lineHeight: "1.4",
            padding: "8px 12px",
            backgroundColor: "var(--bg-base)",
            borderRadius: "var(--radius-sm)",
            borderLeft: "3px solid var(--accent-cyan-solid)",
          }}
        >
          {isSmallFile ? (
            <span>
              <strong>Smart recommendation:</strong> Smaller than {formatBytes(thresholdBytes)}.{" "}
              <strong>Whole object</strong> eliminates striping latency while retaining AES-256-GCM.
            </span>
          ) : (
            <span>
              <strong>Smart recommendation:</strong> File &ge; {formatBytes(thresholdBytes)}.{" "}
              <strong>Chunked + XOR parity</strong> stripes blocks across 3+ drives with 1-drive fault recovery.
            </span>
          )}
        </div>

        {/* Radio Option Cards */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {/* Option 1: Whole Encrypted Object */}
          <label
            className="card-interactive"
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "12px",
              padding: "12px 14px",
              borderRadius: "var(--radius-md)",
              border: `1.5px solid ${
                selectedMode === "whole" ? "var(--accent-cyan-solid)" : "var(--border-subtle)"
              }`,
              backgroundColor:
                selectedMode === "whole" ? "var(--bg-surface-active)" : "var(--bg-surface-elevated)",
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="storage_mode"
              value="whole"
              checked={selectedMode === "whole"}
              onChange={() => setSelectedMode("whole")}
              style={{ marginTop: "3px", accentColor: "var(--accent-cyan-solid)" }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Shield size={14} color="var(--accent-cyan-solid)" />
                <span style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-primary)" }}>
                  Whole encrypted object
                </span>
                {recommendedMode === "whole" && (
                  <span
                    style={{
                      fontSize: "9px",
                      padding: "1px 6px",
                      backgroundColor: "var(--status-online-bg)",
                      color: "var(--status-online-text)",
                      border: "1px solid var(--status-online)",
                      borderRadius: "var(--radius-sm)",
                      fontWeight: "700",
                    }}
                  >
                    RECOMMENDED
                  </span>
                )}
              </div>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                Single AES-256-GCM block on drive with most free space. Requires only 1 drive. No parity.
              </p>
            </div>
          </label>

          {/* Option 2: Chunked + XOR Parity */}
          <label
            className="card-interactive"
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "12px",
              padding: "12px 14px",
              borderRadius: "var(--radius-md)",
              border: `1.5px solid ${
                selectedMode === "chunked_parity" ? "var(--accent-cyan-solid)" : "var(--border-subtle)"
              }`,
              backgroundColor:
                selectedMode === "chunked_parity"
                  ? "var(--bg-surface-active)"
                  : "var(--bg-surface-elevated)",
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="storage_mode"
              value="chunked_parity"
              checked={selectedMode === "chunked_parity"}
              onChange={() => setSelectedMode("chunked_parity")}
              style={{ marginTop: "3px", accentColor: "var(--accent-cyan-solid)" }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <Layers size={14} color="var(--accent-cyan-solid)" />
                <span style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-primary)" }}>
                  Chunked + XOR parity
                </span>
                {recommendedMode === "chunked_parity" && (
                  <span
                    style={{
                      fontSize: "9px",
                      padding: "1px 6px",
                      backgroundColor: "var(--status-online-bg)",
                      color: "var(--status-online-text)",
                      border: "1px solid var(--status-online)",
                      borderRadius: "var(--radius-sm)",
                      fontWeight: "700",
                    }}
                  >
                    RECOMMENDED
                  </span>
                )}
              </div>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                Striped into 1 MiB chunks with rotating XOR parity across distinct drives (tolerates 1 drive failure).
              </p>
            </div>
          </label>
        </div>

        {/* Warning if chunked chosen but < 3 online drives */}
        {isSelectedModeInvalid && (
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "8px",
              padding: "8px 12px",
              backgroundColor: "var(--status-offline-bg)",
              border: "1px solid var(--status-offline)",
              borderRadius: "var(--radius-md)",
              color: "var(--status-offline-text)",
              fontSize: "12px",
            }}
          >
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
            <div>
              At least 3 online drives required for chunked parity (found {onlineDrivesCount}). Choose whole object or bring drives online.
            </div>
          </div>
        )}

        {/* Remember preference checkbox */}
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "12px",
            color: "var(--text-primary)",
            cursor: "pointer",
            userSelect: "none",
          }}
        >
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            style={{ accentColor: "var(--accent-cyan-solid)", width: "15px", height: "15px" }}
          />
          <span>Remember my preference for future uploads</span>
        </label>

        {/* Action buttons */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: "8px",
            paddingTop: "8px",
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <button
            type="button"
            className="btn-interactive"
            onClick={onCancel}
            style={{
              padding: "7px 14px",
              fontSize: "12px",
              color: "var(--text-secondary)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn-interactive"
            onClick={handleConfirm}
            disabled={isSelectedModeInvalid}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 16px",
              backgroundColor: isSelectedModeInvalid ? "var(--bg-surface-elevated)" : "var(--accent-cyan-solid)",
              color: isSelectedModeInvalid ? "var(--text-muted)" : "#ffffff",
              fontWeight: "600",
              fontSize: "12px",
              borderRadius: "var(--radius-sm)",
              cursor: isSelectedModeInvalid ? "not-allowed" : "pointer",
              opacity: isSelectedModeInvalid ? 0.5 : 1,
            }}
          >
            <UploadCloud size={14} />
            <span>Confirm & Upload</span>
          </button>
        </div>
      </div>
    </div>
  );
};
