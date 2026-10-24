import React, { useState, useRef, useMemo } from "react";
import {
  UploadCloud,
  FileText,
  Download,
  Trash2,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileUp,
  Eye,
  Search,
  ArrowUpDown,
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
  X,
} from "lucide-react";
import { StoredFile, Drive } from "../types";
import { formatBytes, formatDate } from "../utils/format";
import { ChunkSquare } from "./ChunkSquare";

interface FilesPanelProps {
  files: StoredFile[];
  drives: Drive[];
  loading: boolean;
  unlocked: boolean;
  onUploadFile: (file: File, overwrite: boolean) => Promise<void>;
  onDownloadFile: (file: StoredFile) => void;
  onDeleteFile: (file: StoredFile) => void;
  onSelectFile: (file: StoredFile) => void;
  onPreviewFile: (file: StoredFile) => void;
  uploadProgress: number | null;
}

export type SortOption =
  | "date_desc"
  | "date_asc"
  | "size_desc"
  | "size_asc"
  | "name_asc"
  | "name_desc";

export const FilesPanel: React.FC<FilesPanelProps> = ({
  files,
  drives,
  loading,
  unlocked,
  onUploadFile,
  onDownloadFile,
  onDeleteFile,
  onSelectFile,
  onPreviewFile,
  uploadProgress,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOption, setSortOption] = useState<SortOption>(() => {
    return (localStorage.getItem("frankenstein_file_sort") as SortOption) || "date_desc";
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSortChange = (newSort: SortOption) => {
    setSortOption(newSort);
    localStorage.setItem("frankenstein_file_sort", newSort);
  };

  const sortedFiles = useMemo(() => {
    let result = [...files];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((f) => f.name.toLowerCase().includes(q));
    }
    return result.sort((a, b) => {
      switch (sortOption) {
        case "date_desc": {
          const tA = new Date(a.created_at || 0).getTime();
          const tB = new Date(b.created_at || 0).getTime();
          return tB - tA;
        }
        case "date_asc": {
          const tA = new Date(a.created_at || 0).getTime();
          const tB = new Date(b.created_at || 0).getTime();
          return tA - tB;
        }
        case "size_desc":
          return b.size - a.size;
        case "size_asc":
          return a.size - b.size;
        case "name_asc":
          return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
        case "name_desc":
          return b.name.localeCompare(a.name, undefined, { numeric: true, sensitivity: "base" });
        default:
          return 0;
      }
    });
  }, [files, sortOption, searchQuery]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (!unlocked) return;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      await onUploadFile(file, overwrite);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      await onUploadFile(file, overwrite);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div
      className="animate-slide-up"
      style={{
        backgroundColor: "var(--bg-surface)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        padding: "22px",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Header and upload bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <h2 style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
            Pooled Files ({files.length})
          </h2>
          <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            AES-256-GCM encrypted chunks striped across storage drives
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {/* Overwrite toggle */}
          <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--text-secondary)", cursor: "pointer", userSelect: "none" }}>
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              style={{ accentColor: "var(--accent-cyan-solid)" }}
            />
            <span>Overwrite</span>
          </label>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileChange}
            style={{ display: "none" }}
            id="file-upload-input"
          />

          {/* Upload trigger button */}
          <button
            className="btn-interactive"
            onClick={() => fileInputRef.current?.click()}
            disabled={!unlocked || uploadProgress !== null}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 14px",
              backgroundColor: "var(--accent-cyan-solid)",
              color: "#ffffff",
              fontWeight: "600",
              fontSize: "12px",
              borderRadius: "var(--radius-md)",
              opacity: !unlocked || uploadProgress !== null ? 0.5 : 1,
              boxShadow: "var(--shadow-sm)",
            }}
            aria-label="Upload file to pool"
          >
            <UploadCloud size={15} />
            <span>Upload File</span>
          </button>
        </div>
      </div>

      {/* Drag & Drop Area */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: `1.5px dashed ${isDragging ? "var(--accent-cyan-solid)" : "var(--border-strong)"}`,
          borderRadius: "var(--radius-md)",
          padding: "16px 20px",
          textAlign: "center",
          backgroundColor: isDragging ? "var(--bg-surface-hover)" : "var(--bg-surface-elevated)",
          transition: "all var(--transition-fast)",
          cursor: unlocked ? "pointer" : "not-allowed",
        }}
        onClick={() => {
          if (unlocked && uploadProgress === null) fileInputRef.current?.click();
        }}
      >
        <FileUp size={24} color={isDragging ? "var(--accent-cyan-light)" : "var(--text-muted)"} style={{ margin: "0 auto 6px" }} />
        <div style={{ fontSize: "13px", color: "var(--text-primary)", fontWeight: "500" }}>
          {unlocked
            ? "Drop a file here, or click to browse"
            : "Unlock storage vault above to upload and manage files"}
        </div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
          Files &ge; 1 MiB chunked with rotating XOR parity • Files &lt; 1 MiB stored whole
        </div>
      </div>

      {/* Upload progress indicator */}
      {uploadProgress !== null && (
        <div
          className="animate-slide-up"
          style={{
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--accent-cyan-solid)",
            borderRadius: "var(--radius-md)",
            padding: "12px 16px",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
            <span style={{ color: "var(--accent-cyan-solid)", fontWeight: "600" }}>
              Encrypting & Streaming Chunks...
            </span>
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>{uploadProgress}%</span>
          </div>
          <div
            style={{
              height: "5px",
              backgroundColor: "var(--bg-base)",
              borderRadius: "var(--radius-full)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${uploadProgress}%`,
                backgroundColor: "var(--accent-cyan-solid)",
                borderRadius: "var(--radius-full)",
                transition: "width 120ms ease",
              }}
            />
          </div>
        </div>
      )}

      {/* Files List / Table with Search & Sort Bar */}
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {files.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "10px",
              padding: "10px 14px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
            }}
          >
            {/* Search Input */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                padding: "5px 10px",
                minWidth: "180px",
                flex: "1 1 200px",
                maxWidth: "340px",
              }}
            >
              <Search size={14} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Search files by name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  backgroundColor: "transparent",
                  border: "none",
                  outline: "none",
                  fontSize: "12px",
                  color: "var(--text-primary)",
                  width: "100%",
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: 0,
                    display: "flex",
                  }}
                  title="Clear search"
                >
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Sorting controls */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: "600",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                <ArrowUpDown size={13} color="var(--accent-cyan-solid)" />
                <span>Sort by:</span>
              </span>

              {/* Sort Dropdown */}
              <select
                value={sortOption}
                onChange={(e) => handleSortChange(e.target.value as SortOption)}
                style={{
                  backgroundColor: "var(--bg-base)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  padding: "5px 10px",
                  fontSize: "12px",
                  fontWeight: "500",
                  outline: "none",
                  cursor: "pointer",
                }}
              >
                <option value="date_desc">Date: Latest First</option>
                <option value="date_asc">Date: Oldest First</option>
                <option value="size_desc">Size: Largest First</option>
                <option value="size_asc">Size: Smallest First</option>
                <option value="name_asc">Name: A &rarr; Z</option>
                <option value="name_desc">Name: Z &rarr; A</option>
              </select>

              {/* Quick Direction Toggle */}
              <button
                className="btn-interactive"
                onClick={() => {
                  const toggles: Record<SortOption, SortOption> = {
                    date_desc: "date_asc",
                    date_asc: "date_desc",
                    size_desc: "size_asc",
                    size_asc: "size_desc",
                    name_asc: "name_desc",
                    name_desc: "name_asc",
                  };
                  handleSortChange(toggles[sortOption]);
                }}
                title={sortOption.endsWith("_desc") ? "Switch to Ascending" : "Switch to Descending"}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "5px 9px",
                  backgroundColor: "var(--bg-base)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "11px",
                  fontWeight: "600",
                  color: "var(--text-secondary)",
                }}
              >
                {sortOption.endsWith("_desc") ? (
                  <>
                    <ArrowDownWideNarrow size={13} color="var(--accent-cyan-solid)" />
                    <span>Desc</span>
                  </>
                ) : (
                  <>
                    <ArrowUpNarrowWide size={13} color="var(--accent-cyan-solid)" />
                    <span>Asc</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {files.length === 0 && !loading && (
          <div
            style={{
              padding: "40px 24px",
              textAlign: "center",
              color: "var(--text-muted)",
              border: "1px dashed var(--border-subtle)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <FileText size={32} style={{ margin: "0 auto 10px", opacity: 0.3 }} />
            <div style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-secondary)" }}>
              No files in storage volume
            </div>
            <div style={{ fontSize: "12px", marginTop: "4px" }}>
              Upload any document or seed the demo to inspect chunk placement and parity rebuilds.
            </div>
          </div>
        )}

        {files.length > 0 && sortedFiles.length === 0 && (
          <div
            style={{
              padding: "30px 20px",
              textAlign: "center",
              color: "var(--text-muted)",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px dashed var(--border-subtle)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <Search size={28} style={{ margin: "0 auto 8px", opacity: 0.4 }} />
            <div style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-secondary)" }}>
              No files matching "{searchQuery}"
            </div>
            <button
              className="btn-interactive"
              onClick={() => setSearchQuery("")}
              style={{
                marginTop: "10px",
                padding: "4px 10px",
                fontSize: "11px",
                color: "var(--accent-cyan-solid)",
                backgroundColor: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              Clear Filter
            </button>
          </div>
        )}

        {sortedFiles.map((file) => {
          const isHealthy = file.health === "Healthy";
          const isRebuilt = file.health === "Rebuilt from parity";
          const isUnavailable = file.health === "Unavailable";
          const chunks = file.chunks || [];

          return (
            <div
              key={file.id}
              className="card-interactive"
              style={{
                backgroundColor: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "14px 16px",
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              {/* File Row Header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "var(--bg-base)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    <FileText size={16} color="var(--accent-cyan-solid)" />
                  </div>

                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-primary)", wordBreak: "break-all" }}>
                        {file.name}
                      </span>

                      {/* Health badge - solid colors */}
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "2px 7px",
                          borderRadius: "var(--radius-full)",
                          fontSize: "10px",
                          fontWeight: "700",
                          textTransform: "uppercase",
                          letterSpacing: "0.03em",
                          backgroundColor: isHealthy
                            ? "var(--status-online-bg)"
                            : isRebuilt
                            ? "var(--status-warning-bg)"
                            : "var(--status-offline-bg)",
                          border: `1px solid ${
                            isHealthy
                              ? "var(--status-online)"
                              : isRebuilt
                              ? "var(--status-warning)"
                              : "var(--status-offline)"
                          }`,
                          color: isHealthy
                            ? "var(--status-online-text)"
                            : isRebuilt
                            ? "var(--status-warning-text)"
                            : "var(--status-offline-text)",
                        }}
                      >
                        {isHealthy && <CheckCircle2 size={11} />}
                        {isRebuilt && <AlertTriangle size={11} />}
                        {isUnavailable && <XCircle size={11} />}
                        <span>{file.health || "Healthy"}</span>
                      </span>

                      {/* Storage mode badge - solid colors */}
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "2px 6px",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "10px",
                          fontWeight: "700",
                          backgroundColor:
                            file.storage_mode === "whole"
                              ? "var(--bg-base)"
                              : "var(--bg-surface-active)",
                          color:
                            file.storage_mode === "whole"
                              ? "var(--text-secondary)"
                              : "var(--accent-cyan-light)",
                          border: `1px solid ${
                            file.storage_mode === "whole"
                              ? "var(--border-strong)"
                              : "var(--accent-cyan-solid)"
                          }`,
                        }}
                      >
                        {file.storage_mode === "whole" ? "WHOLE" : "XOR PARITY"}
                      </span>
                    </div>

                    <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
                      {file.storage_mode === "whole"
                        ? `${formatBytes(file.size)} • 1 object on ${chunks[0]?.drive_name || "drive"} • Uploaded ${formatDate(file.created_at)}`
                        : `${formatBytes(file.size)} • ${chunks.length} chunks (${Math.ceil(chunks.length / 3)} stripes) • Uploaded ${formatDate(file.created_at)}`}
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <button
                    className="btn-interactive"
                    onClick={() => onSelectFile(file)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "5px 9px",
                      backgroundColor: "var(--bg-base)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "500",
                      color: "var(--text-secondary)",
                    }}
                    aria-label={`View metadata and chunks for ${file.name}`}
                  >
                    <Info size={13} />
                    <span>Details</span>
                  </button>

                  <button
                    className="btn-interactive"
                    onClick={() => onPreviewFile(file)}
                    disabled={isUnavailable}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "5px 10px",
                      backgroundColor: "var(--bg-base)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: isUnavailable ? "var(--text-muted)" : "var(--accent-cyan-solid)",
                      opacity: isUnavailable ? 0.4 : 1,
                    }}
                    aria-label={`Preview file ${file.name}`}
                    title={isUnavailable ? "Cannot preview: drive is offline" : "Instant in-app preview"}
                  >
                    <Eye size={13} />
                    <span>Preview</span>
                  </button>

                  <button
                    className="btn-interactive"
                    onClick={() => onDownloadFile(file)}
                    disabled={isUnavailable}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "5px 11px",
                      backgroundColor: isUnavailable ? "var(--bg-base)" : "var(--accent-cyan-solid)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: isUnavailable ? "var(--text-muted)" : "#ffffff",
                      opacity: isUnavailable ? 0.4 : 1,
                    }}
                    aria-label={`Download file ${file.name}`}
                    title={isUnavailable ? "Cannot download: 2 or more drives in stripe are offline" : "Download & verify"}
                  >
                    <Download size={13} />
                    <span>Download</span>
                  </button>

                  <button
                    className="btn-interactive"
                    onClick={() => onDeleteFile(file)}
                    style={{
                      padding: "5px 7px",
                      color: "var(--text-muted)",
                      borderRadius: "var(--radius-sm)",
                    }}
                    aria-label={`Delete file ${file.name}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Chunk Map Row */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                  paddingTop: "8px",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ fontSize: "11px", color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
                  <span>
                    {file.storage_mode === "whole"
                      ? "Direct chunk placement:"
                      : "Stripe Chunk Map (hover to inspect):"}
                  </span>
                  <span>
                    {file.storage_mode === "whole" ? "No XOR Parity" : <strong>P = Parity Chunk</strong>}
                  </span>
                </div>

                {/* Striped Chunk squares */}
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "5px",
                    alignItems: "center",
                  }}
                >
                  {chunks.map((chunk) => (
                    <ChunkSquare key={chunk.id} chunk={chunk} drives={drives} />
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
