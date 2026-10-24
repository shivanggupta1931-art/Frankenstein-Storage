import React, { useState, useEffect } from "react";
import {
  X,
  Download,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
  FileText,
  Image as ImageIcon,
  FileCode,
  File as FileIcon,
  Copy,
  Check,
  ExternalLink,
  AlertCircle,
  Loader2,
  Layers,
} from "lucide-react";
import { StoredFile } from "../types";
import { formatBytes } from "../utils/format";
import { api } from "../services/api";

interface FilePreviewModalProps {
  file: StoredFile | null;
  onClose: () => void;
  onDownload: (file: StoredFile) => void;
}

type PreviewType = "image" | "pdf" | "text" | "audio" | "video" | "unsupported";

function getFileType(fileName: string): PreviewType {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  const imageExts = ["png", "jpg", "jpeg", "webp", "gif", "svg", "bmp", "ico"];
  if (imageExts.includes(ext)) return "image";

  if (ext === "pdf") return "pdf";

  const textExts = [
    "txt",
    "md",
    "json",
    "csv",
    "tsv",
    "js",
    "jsx",
    "ts",
    "tsx",
    "py",
    "html",
    "htm",
    "css",
    "scss",
    "xml",
    "yaml",
    "yml",
    "sh",
    "bash",
    "zsh",
    "sql",
    "log",
    "env",
    "ini",
    "toml",
    "conf",
    "diff",
    "patch",
    "dockerfile",
    "makefile",
  ];
  if (textExts.includes(ext)) return "text";

  const videoExts = ["mp4", "webm", "ogg", "mov"];
  if (videoExts.includes(ext)) return "video";

  const audioExts = ["mp3", "wav", "ogg", "m4a", "flac"];
  if (audioExts.includes(ext)) return "audio";

  return "unsupported";
}

export const FilePreviewModal: React.FC<FilePreviewModalProps> = ({
  file,
  onClose,
  onDownload,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Image viewer controls
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [fitToScreen, setFitToScreen] = useState(true);

  const previewType = file ? getFileType(file.name) : "unsupported";

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (previewType === "image") {
        if (e.key === "+" || e.key === "=") {
          setZoom((z) => Math.min(5, Math.round((z + 0.25) * 100) / 100));
        } else if (e.key === "-") {
          setZoom((z) => Math.max(0.25, Math.round((z - 0.25) * 100) / 100));
        } else if (e.key === "0") {
          setZoom(1);
          setFitToScreen(true);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, previewType]);

  // Load preview data
  useEffect(() => {
    if (!file) {
      setBlobUrl(null);
      setTextContent(null);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    setZoom(1);
    setRotation(0);
    setFitToScreen(true);

    const loadContent = async () => {
      try {
        const type = getFileType(file.name);

        if (type === "text") {
          const text = await api.fetchPreviewText(file.id);
          if (active) {
            setTextContent(text);
            setLoading(false);
          }
        } else if (type === "image" || type === "pdf" || type === "video" || type === "audio") {
          const { blob } = await api.fetchPreviewBlob(file.id);
          if (active) {
            const url = window.URL.createObjectURL(blob);
            setBlobUrl(url);
            setLoading(false);
          }
        } else {
          // Unsupported type
          if (active) {
            setLoading(false);
          }
        }
      } catch (err: any) {
        if (active) {
          setError(err.message || "Failed to load file preview");
          setLoading(false);
        }
      }
    };

    loadContent();

    return () => {
      active = false;
      if (blobUrl) {
        window.URL.revokeObjectURL(blobUrl);
      }
    };
  }, [file?.id]);

  if (!file) return null;

  const handleCopyText = async () => {
    if (!textContent) return;
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  };

  const handleOpenDirect = () => {
    const directUrl = api.getPreviewUrl(file.id);
    window.open(directUrl, "_blank");
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.78)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-title"
      onClick={onClose}
    >
      <div
        className="animate-slide-up"
        style={{
          width: "min(1100px, 94vw)",
          height: "min(820px, 90vh)",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 20px",
            borderBottom: "1px solid var(--border-subtle)",
            backgroundColor: "var(--bg-surface-elevated)",
            gap: "12px",
            flexShrink: 0,
          }}
        >
          {/* File Title & Badges */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "var(--radius-md)",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {previewType === "image" && <ImageIcon size={18} color="var(--accent-cyan-solid)" />}
              {previewType === "pdf" && <FileText size={18} color="#ef4444" />}
              {previewType === "text" && <FileCode size={18} color="#10b981" />}
              {previewType === "unsupported" && <FileIcon size={18} color="var(--text-muted)" />}
            </div>

            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                <h3
                  id="preview-title"
                  style={{
                    fontSize: "14px",
                    fontWeight: "700",
                    color: "var(--text-primary)",
                    margin: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: "400px",
                  }}
                  title={file.name}
                >
                  {file.name}
                </h3>

                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: "700",
                    padding: "2px 6px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--bg-base)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border-subtle)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {formatBytes(file.size)}
                </span>

                <span
                  style={{
                    fontSize: "9px",
                    fontWeight: "700",
                    padding: "2px 6px",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor:
                      file.storage_mode === "whole" ? "var(--bg-base)" : "var(--bg-surface-active)",
                    color:
                      file.storage_mode === "whole" ? "var(--text-secondary)" : "var(--accent-cyan-light)",
                    border: `1px solid ${
                      file.storage_mode === "whole" ? "var(--border-strong)" : "var(--accent-cyan-solid)"
                    }`,
                  }}
                >
                  {file.storage_mode === "whole" ? "WHOLE" : "XOR PARITY"}
                </span>
              </div>
              <p style={{ margin: "2px 0 0 0", fontSize: "11px", color: "var(--text-muted)" }}>
                Decrypted AES-256-GCM chunks • In-App Preview
              </p>
            </div>
          </div>

          {/* Action Toolbar */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
            {/* Image zoom controls */}
            {previewType === "image" && !loading && !error && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  backgroundColor: "var(--bg-base)",
                  padding: "3px 6px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <button
                  className="btn-interactive"
                  onClick={() => setZoom((z) => Math.max(0.25, Math.round((z - 0.25) * 100) / 100))}
                  title="Zoom Out (-)"
                  style={{ padding: "4px", color: "var(--text-secondary)" }}
                >
                  <ZoomOut size={15} />
                </button>
                <span
                  style={{
                    fontSize: "11px",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-primary)",
                    minWidth: "38px",
                    textAlign: "center",
                  }}
                >
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  className="btn-interactive"
                  onClick={() => setZoom((z) => Math.min(5, Math.round((z + 0.25) * 100) / 100))}
                  title="Zoom In (+)"
                  style={{ padding: "4px", color: "var(--text-secondary)" }}
                >
                  <ZoomIn size={15} />
                </button>
                <button
                  className="btn-interactive"
                  onClick={() => setRotation((r) => (r + 90) % 360)}
                  title="Rotate 90°"
                  style={{ padding: "4px", color: "var(--text-secondary)" }}
                >
                  <RotateCw size={14} />
                </button>
                <button
                  className="btn-interactive"
                  onClick={() => {
                    setFitToScreen(!fitToScreen);
                    setZoom(1);
                  }}
                  title={fitToScreen ? "Actual Size (100%)" : "Fit to Screen"}
                  style={{
                    padding: "4px 6px",
                    fontSize: "10px",
                    fontWeight: "600",
                    color: fitToScreen ? "var(--accent-cyan-solid)" : "var(--text-secondary)",
                  }}
                >
                  <Maximize2 size={13} />
                </button>
              </div>
            )}

            {/* Text Copy Button */}
            {previewType === "text" && textContent && (
              <button
                className="btn-interactive"
                onClick={handleCopyText}
                title="Copy contents to clipboard"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "5px 10px",
                  backgroundColor: "var(--bg-base)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "11px",
                  fontWeight: "600",
                  color: copied ? "var(--status-online-text)" : "var(--text-secondary)",
                }}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            )}

            {/* Open in new tab */}
            <button
              className="btn-interactive"
              onClick={handleOpenDirect}
              title="Open raw preview in new browser tab"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "5px",
                padding: "5px 10px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                fontSize: "11px",
                fontWeight: "600",
                color: "var(--text-secondary)",
              }}
            >
              <ExternalLink size={13} />
              <span>Open Tab</span>
            </button>

            {/* Download button */}
            <button
              className="btn-interactive"
              onClick={() => onDownload(file)}
              title="Download file"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "5px",
                padding: "6px 12px",
                backgroundColor: "var(--accent-cyan-solid)",
                color: "#ffffff",
                borderRadius: "var(--radius-sm)",
                fontSize: "11px",
                fontWeight: "600",
              }}
            >
              <Download size={13} />
              <span>Download</span>
            </button>

            {/* Close button */}
            <button
              className="btn-interactive"
              onClick={onClose}
              aria-label="Close preview"
              style={{
                padding: "6px",
                color: "var(--text-muted)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div
          style={{
            flex: 1,
            position: "relative",
            overflow: "hidden",
            backgroundColor: "var(--bg-base)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* Loading State */}
          {loading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "12px",
                color: "var(--text-secondary)",
              }}
            >
              <Loader2 size={32} className="animate-spin" color="var(--accent-cyan-solid)" />
              <p style={{ fontSize: "13px", fontWeight: "500", margin: 0 }}>
                Decrypting and reconstructing {file.name}...
              </p>
            </div>
          )}

          {/* Error State */}
          {!loading && error && (
            <div
              style={{
                maxWidth: "460px",
                textAlign: "center",
                padding: "24px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--status-offline)",
                borderRadius: "var(--radius-lg)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "12px",
              }}
            >
              <AlertCircle size={36} color="var(--status-offline)" />
              <h4 style={{ margin: 0, fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
                Preview Unavailable
              </h4>
              <p style={{ margin: 0, fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                {error}
              </p>
              <button
                className="btn-interactive"
                onClick={() => onDownload(file)}
                style={{
                  marginTop: "8px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 16px",
                  backgroundColor: "var(--accent-cyan-solid)",
                  color: "#ffffff",
                  fontSize: "12px",
                  fontWeight: "600",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <Download size={14} />
                <span>Download File Directly</span>
              </button>
            </div>
          )}

          {/* Images */}
          {!loading && !error && previewType === "image" && blobUrl && (
            <div
              style={{
                width: "100%",
                height: "100%",
                overflow: "auto",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "20px",
              }}
            >
              <img
                src={blobUrl}
                alt={file.name}
                style={{
                  transform: `scale(${zoom}) rotate(${rotation}deg)`,
                  transformOrigin: "center center",
                  transition: "transform 150ms ease",
                  maxWidth: fitToScreen && zoom <= 1 ? "100%" : "none",
                  maxHeight: fitToScreen && zoom <= 1 ? "100%" : "none",
                  objectFit: "contain",
                  boxShadow: "var(--shadow-md)",
                  borderRadius: "var(--radius-sm)",
                }}
              />
            </div>
          )}

          {/* PDF Viewer */}
          {!loading && !error && previewType === "pdf" && blobUrl && (
            <iframe
              src={blobUrl}
              title={file.name}
              style={{
                width: "100%",
                height: "100%",
                border: "none",
                backgroundColor: "#ffffff",
              }}
            />
          )}

          {/* Text / Code Viewer */}
          {!loading && !error && previewType === "text" && textContent !== null && (
            <div
              style={{
                width: "100%",
                height: "100%",
                overflow: "auto",
                padding: "20px 24px",
                backgroundColor: "var(--bg-base)",
              }}
            >
              <pre
                style={{
                  margin: 0,
                  fontFamily: "var(--font-mono)",
                  fontSize: "12px",
                  lineHeight: "1.6",
                  color: "var(--text-primary)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                <code>{textContent}</code>
              </pre>
            </div>
          )}

          {/* Audio Player */}
          {!loading && !error && previewType === "audio" && blobUrl && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "16px",
                padding: "30px",
                backgroundColor: "var(--bg-surface)",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <audio controls src={blobUrl} autoPlay style={{ width: "360px" }} />
              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{file.name}</span>
            </div>
          )}

          {/* Video Player */}
          {!loading && !error && previewType === "video" && blobUrl && (
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "16px",
              }}
            >
              <video
                controls
                src={blobUrl}
                style={{
                  maxWidth: "100%",
                  maxHeight: "100%",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "var(--shadow-md)",
                }}
              />
            </div>
          )}

          {/* Unsupported Format Banner */}
          {!loading && !error && previewType === "unsupported" && (
            <div
              style={{
                maxWidth: "460px",
                textAlign: "center",
                padding: "32px 28px",
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-lg)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "14px",
                boxShadow: "var(--shadow-md)",
              }}
            >
              <div
                style={{
                  width: "56px",
                  height: "56px",
                  borderRadius: "var(--radius-lg)",
                  backgroundColor: "var(--bg-base)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <Layers size={28} color="var(--accent-cyan-solid)" />
              </div>

              <div>
                <h4 style={{ margin: "0 0 4px 0", fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
                  No In-Browser Preview
                </h4>
                <p style={{ margin: 0, fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  This file format ({file.name.split(".").pop()?.toUpperCase() || "BIN"}) is safely encrypted across your Frankenstein storage drives.
                </p>
              </div>

              <div
                style={{
                  width: "100%",
                  backgroundColor: "var(--bg-base)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  padding: "10px 14px",
                  fontSize: "11px",
                  display: "flex",
                  justifyContent: "space-between",
                  color: "var(--text-muted)",
                }}
              >
                <span>Size: <strong style={{ color: "var(--text-secondary)" }}>{formatBytes(file.size)}</strong></span>
                <span>Mode: <strong style={{ color: "var(--text-secondary)" }}>{(file.storage_mode || "chunked_parity").toUpperCase()}</strong></span>
              </div>

              <button
                className="btn-interactive"
                onClick={() => onDownload(file)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "9px 20px",
                  backgroundColor: "var(--accent-cyan-solid)",
                  color: "#ffffff",
                  fontSize: "12px",
                  fontWeight: "600",
                  borderRadius: "var(--radius-sm)",
                  boxShadow: "var(--shadow-sm)",
                  marginTop: "6px",
                }}
              >
                <Download size={14} />
                <span>Download File</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
