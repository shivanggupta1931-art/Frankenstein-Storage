import React, { useState, useEffect, useRef } from "react";
import {
  HardDrive,
  Power,
  Trash2,
  Plus,
  AlertCircle,
  Cloud,
  Folder,
  ExternalLink,
  Zap,
  CheckCircle2,
  FolderPlus,
  Compass,
  RefreshCw,
  AlertTriangle,
  Usb,
  Eject,
  Loader2,
  Database,
} from "lucide-react";
import { Drive, ExternalUsbDrive } from "../types";
import { formatBytes, getDriveColor } from "../utils/format";
import { api } from "../services/api";

interface DrivesPanelProps {
  drives: Drive[];
  loading: boolean;
  onToggleOffline: (driveId: string, currentOffline: boolean) => void;
  onDeleteDrive: (driveId: string) => void;
  onAddDrive: (
    path: string,
    displayName: string,
    providerType?: "local" | "gdrive" | "s3" | "r2" | "minio" | "b2" | "icloud" | "onedrive" | "dropbox",
    config?: Record<string, any>
  ) => Promise<void>;
  onEjectDrive?: (driveId: string) => Promise<void>;
}

interface MacosLocation {
  name: string;
  path: string;
  total: number;
  free: number;
  used: number;
  is_external: boolean;
  is_removable?: boolean;
  is_cloud_synced?: boolean;
  description: string;
}

export const DrivesPanel: React.FC<DrivesPanelProps> = ({
  drives,
  loading,
  onToggleOffline,
  onDeleteDrive,
  onAddDrive,
  onEjectDrive,
}) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [providerType, setProviderType] = useState<"local" | "gdrive" | "s3">("local");
  const [path, setPath] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [selectedProviderHint, setSelectedProviderHint] = useState<string | null>(null);

  // S3 / Cloudflare R2 / AWS S3 state
  const [s3Endpoint, setS3Endpoint] = useState("");
  const [s3Bucket, setS3Bucket] = useState("frankenstein-vault");
  const [s3AccessKey, setS3AccessKey] = useState("");
  const [s3SecretKey, setS3SecretKey] = useState("");
  const [s3Region, setS3Region] = useState("auto");
  const [s3Prefix, setS3Prefix] = useState("chunks/");
  const [s3Subtype, setS3Subtype] = useState<"r2" | "s3" | "minio" | "b2">("r2");

  // Eject state for external USB drives
  const [ejectingIds, setEjectingIds] = useState<Record<string, boolean>>({});

  const handleEjectDrive = async (driveId: string) => {
    setEjectingIds((prev) => ({ ...prev, [driveId]: true }));
    try {
      if (onEjectDrive) {
        await onEjectDrive(driveId);
      } else {
        await api.ejectDrive(driveId);
      }
    } finally {
      setEjectingIds((prev) => ({ ...prev, [driveId]: false }));
    }
  };

  // External USB drives detection
  const [externalDrives, setExternalDrives] = useState<ExternalUsbDrive[]>([]);

  // Google Drive tab state
  const [gdriveLink, setGdriveLink] = useState("");
  const [gdriveAuthType, setGdriveAuthType] = useState<"demo_mock" | "access_token">("demo_mock");
  const [gdriveToken, setGdriveToken] = useState("");
  const [gdriveFolderId, setGdriveFolderId] = useState<string | null>(null);

  // macOS system storage locations
  const [macosLocations, setMacosLocations] = useState<MacosLocation[]>([]);
  const [loadingLocations, setLoadingLocations] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAutoSettingUp, setIsAutoSettingUp] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const nativeFolderInputRef = useRef<HTMLInputElement>(null);

  const fetchMacosLocations = () => {
    setLoadingLocations(true);
    api.getMacosStorageLocations()
      .then((res) => {
        setMacosLocations(res.locations || []);
      })
      .catch(() => {})
      .finally(() => setLoadingLocations(false));
  };

  // Load detected macOS storage locations
  useEffect(() => {
    if (showAddForm) {
      fetchMacosLocations();
    }
  }, [showAddForm]);

  // Poll connected external USB devices for auto-detection and hot-plug prompt
  useEffect(() => {
    let active = true;
    const fetchUsb = () => {
      api.getExternalDrives()
        .then((res) => {
          if (active) {
            setExternalDrives(res.external_drives || []);
          }
        })
        .catch(() => {});
    };
    fetchUsb();
    const timer = setInterval(fetchUsb, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  // Automatically extract Google Drive folder ID when link is entered
  const handleGdriveLinkChange = (val: string) => {
    setGdriveLink(val);
    const match = val.match(/\/folders\/([a-zA-Z0-9_-]+)/);
    if (match) {
      setGdriveFolderId(match[1]);
      if (!displayName) {
        setDisplayName(`Google Drive (${match[1].slice(0, 8)})`);
      }
    } else {
      setGdriveFolderId(null);
    }
  };

  // Directory picker with macOS permission
  const handleOpenNativeDirectoryPicker = async () => {
    try {
      if ("showDirectoryPicker" in window) {
        const handle = await (window as any).showDirectoryPicker();
        if (handle && handle.name) {
          setDisplayName(handle.name);
          setPath(`~/Documents/${handle.name}`);
        }
      } else {
        nativeFolderInputRef.current?.click();
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        nativeFolderInputRef.current?.click();
      }
    }
  };

  const handleNativeFolderSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      const relPath = file.webkitRelativePath;
      const folderName = relPath ? relPath.split("/")[0] : "macOS Folder";
      setDisplayName(folderName);
      setPath(`~/Documents/${folderName}`);
    }
  };

  const handleSelectPreset = (loc: MacosLocation) => {
    setPath(loc.path);
    setDisplayName(loc.name);
    setAddError(null);
    if (loc.name.toLowerCase().includes("icloud")) {
      setSelectedProviderHint("icloud");
    } else if (loc.name.toLowerCase().includes("onedrive")) {
      setSelectedProviderHint("onedrive");
    } else if (loc.name.toLowerCase().includes("dropbox")) {
      setSelectedProviderHint("dropbox");
    } else {
      setSelectedProviderHint("local");
    }
  };

  // Quick 1-click auto-setup of 3 real macOS storage units
  const handleAutoSetupRealDrives = async () => {
    setIsAutoSettingUp(true);
    setAddError(null);
    try {
      await api.setupRealDrives();
      window.location.reload();
    } catch (err: any) {
      setAddError(err.message || "Failed to auto-setup macOS storage");
    } finally {
      setIsAutoSettingUp(false);
    }
  };

  const handleApplyS3Preset = (type: "r2" | "s3" | "b2" | "minio") => {
    setS3Subtype(type);
    if (type === "r2") {
      setDisplayName("Cloudflare R2 Vault");
      setS3Endpoint("https://<account_id>.r2.cloudflarestorage.com");
      setS3Bucket("frankenstein-vault");
      setS3Region("auto");
    } else if (type === "s3") {
      setDisplayName("AWS S3 Vault");
      setS3Endpoint("https://s3.us-east-1.amazonaws.com");
      setS3Bucket("frankenstein-vault");
      setS3Region("us-east-1");
    } else if (type === "b2") {
      setDisplayName("Backblaze B2 Vault");
      setS3Endpoint("https://s3.us-west-004.backblazeb2.com");
      setS3Bucket("frankenstein-vault");
      setS3Region("us-west-004");
    } else if (type === "minio") {
      setDisplayName("MinIO Object Storage");
      setS3Endpoint("http://127.0.0.1:9000");
      setS3Bucket("frankenstein-vault");
      setS3Region("us-east-1");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // S3-compatible cloud storage submission
    if (providerType === "s3") {
      if (!s3Bucket.trim()) {
        setAddError("S3 / R2 Bucket name is required");
        return;
      }
      const finalName = displayName.trim() || `${s3Subtype.toUpperCase()} Bucket (${s3Bucket.trim()})`;
      const cleanPrefix = s3Prefix.trim() || "chunks/";
      const cleanPath = `s3://${s3Bucket.trim()}/${cleanPrefix}`.replace(/\/+/g, "/").replace("s3:/", "s3://");

      setIsSubmitting(true);
      setAddError(null);
      try {
        await onAddDrive(
          cleanPath,
          finalName,
          s3Subtype,
          {
            endpoint_url: s3Endpoint.trim(),
            bucket: s3Bucket.trim(),
            access_key_id: s3AccessKey.trim(),
            secret_access_key: s3SecretKey.trim(),
            region: s3Region.trim() || "auto",
            prefix: cleanPrefix,
          }
        );
        setS3Bucket("frankenstein-vault");
        setS3Endpoint("");
        setS3AccessKey("");
        setS3SecretKey("");
        setDisplayName("");
        setShowAddForm(false);
      } catch (err: any) {
        setAddError(err.message || "Failed to connect S3 bucket");
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Check if user entered a Google Drive link
    const targetLink = providerType === "gdrive" ? gdriveLink.trim() : path.trim();
    const isGoogleDriveLink =
      targetLink.includes("drive.google.com") ||
      targetLink.startsWith("http://") ||
      targetLink.startsWith("https://") ||
      providerType === "gdrive";

    if (isGoogleDriveLink) {
      if (!targetLink) {
        setAddError("Please paste your Google Drive folder link");
        return;
      }
      const finalName = displayName.trim() || "Google Drive (Cloud)";
      const match = targetLink.match(/\/folders\/([a-zA-Z0-9_-]+)/);
      const folderId = match ? match[1] : gdriveFolderId || "gdrive_folder";

      setIsSubmitting(true);
      setAddError(null);
      try {
        await onAddDrive(
          targetLink,
          finalName,
          "gdrive",
          {
            folder_url: targetLink,
            folder_id: folderId,
            auth_type: gdriveAuthType,
            folder_name: finalName,
            access_token: gdriveAuthType === "access_token" ? gdriveToken.trim() : undefined,
          }
        );
        setGdriveLink("");
        setDisplayName("");
        setPath("");
        setShowAddForm(false);
      } catch (err: any) {
        setAddError(err.message || "Failed to connect Google Drive link");
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Local macOS storage, iCloud, OneDrive, Dropbox
    if (!displayName.trim()) {
      setAddError("Display name is required");
      return;
    }

    if (!path.trim()) {
      setAddError("Folder path is required. Pick a macOS folder or select a preset below.");
      return;
    }

    let effProvider: "local" | "icloud" | "onedrive" | "dropbox" = "local";
    if (path.includes("Mobile Documents") || path.includes("com~apple~CloudDocs") || displayName.toLowerCase().includes("icloud")) {
      effProvider = "icloud";
    } else if (path.toLowerCase().includes("onedrive") || displayName.toLowerCase().includes("onedrive")) {
      effProvider = "onedrive";
    } else if (path.toLowerCase().includes("dropbox") || displayName.toLowerCase().includes("dropbox")) {
      effProvider = "dropbox";
    } else if (selectedProviderHint && ["icloud", "onedrive", "dropbox"].includes(selectedProviderHint)) {
      effProvider = selectedProviderHint as any;
    }

    setAddError(null);
    setIsSubmitting(true);
    try {
      await onAddDrive(path.trim(), displayName.trim(), effProvider);
      setPath("");
      setDisplayName("");
      setSelectedProviderHint(null);
      setShowAddForm(false);
    } catch (err: any) {
      setAddError(err.message || "Failed to add storage drive");
    } finally {
      setIsSubmitting(false);
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
      {/* Hidden input for native folder picking */}
      <input
        ref={nativeFolderInputRef}
        type="file"
        // @ts-ignore
        webkitdirectory="true"
        // @ts-ignore
        directory="true"
        multiple
        onChange={handleNativeFolderSelected}
        style={{ display: "none" }}
      />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
        <div>
          <h2 style={{ fontSize: "15px", fontWeight: "700", color: "var(--text-primary)" }}>
            Storage Drives ({drives.length})
          </h2>
          <p style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            Real macOS volumes, external SSDs, and Google Drive in a unified fault-tolerant pool
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {drives.length === 0 && (
            <button
              type="button"
              className="btn-interactive"
              onClick={handleAutoSetupRealDrives}
              disabled={isAutoSettingUp}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                backgroundColor: "rgba(16, 185, 129, 0.15)",
                color: "var(--status-online)",
                border: "1px solid var(--status-online)",
                fontWeight: "600",
                fontSize: "12px",
                borderRadius: "var(--radius-md)",
                cursor: isAutoSettingUp ? "not-allowed" : "pointer",
              }}
              title="Automatically initializes 3 real storage units on your Mac"
            >
              <Zap size={14} />
              <span>{isAutoSettingUp ? "Initializing..." : "⚡ Quick Real macOS Storage (3 Units)"}</span>
            </button>
          )}

          <button
            className="btn-interactive"
            onClick={() => {
              setShowAddForm(!showAddForm);
              setAddError(null);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 14px",
              backgroundColor: showAddForm ? "var(--bg-surface-elevated)" : "var(--accent-cyan-solid)",
              color: showAddForm ? "var(--text-secondary)" : "#ffffff",
              fontWeight: "600",
              fontSize: "12px",
              borderRadius: "var(--radius-md)",
              border: showAddForm ? "1px solid var(--border-strong)" : "none",
              boxShadow: showAddForm ? "none" : "var(--shadow-sm)",
            }}
            aria-label={showAddForm ? "Cancel adding drive" : "Add storage drive"}
          >
            <Plus size={15} />
            <span>{showAddForm ? "Cancel" : "Add Drive"}</span>
          </button>
        </div>
      </div>

      {/* Add drive form inline panel */}
      {showAddForm && (
        <form
          onSubmit={handleSubmit}
          className="animate-slide-up"
          style={{
            backgroundColor: "var(--bg-surface-elevated)",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-md)",
            padding: "18px",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
          }}
        >
          {/* Provider Type Tabs */}
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn-interactive"
              onClick={() => {
                setProviderType("local");
                setAddError(null);
              }}
              style={{
                flex: 1,
                minWidth: "160px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                padding: "10px",
                borderRadius: "var(--radius-sm)",
                fontSize: "12px",
                fontWeight: "600",
                backgroundColor: providerType === "local" ? "var(--accent-cyan-solid)" : "var(--bg-base)",
                color: providerType === "local" ? "#ffffff" : "var(--text-secondary)",
                border: `1px solid ${providerType === "local" ? "var(--accent-cyan-solid)" : "var(--border-strong)"}`,
              }}
            >
              <Folder size={15} />
              <span>macOS & Cloud Sync (iCloud/USB)</span>
            </button>

            <button
              type="button"
              className="btn-interactive"
              onClick={() => {
                setProviderType("gdrive");
                setAddError(null);
                if (!displayName) setDisplayName("Google Drive (Cloud)");
              }}
              style={{
                flex: 1,
                minWidth: "160px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                padding: "10px",
                borderRadius: "var(--radius-sm)",
                fontSize: "12px",
                fontWeight: "600",
                backgroundColor: providerType === "gdrive" ? "var(--accent-cyan-solid)" : "var(--bg-base)",
                color: providerType === "gdrive" ? "#ffffff" : "var(--text-secondary)",
                border: `1px solid ${providerType === "gdrive" ? "var(--accent-cyan-solid)" : "var(--border-strong)"}`,
              }}
            >
              <Cloud size={15} />
              <span>Google Drive Link</span>
            </button>

            <button
              type="button"
              className="btn-interactive"
              onClick={() => {
                setProviderType("s3");
                setAddError(null);
                if (!displayName) setDisplayName("Cloudflare R2 Vault");
                if (!s3Bucket) setS3Bucket("frankenstein-vault");
              }}
              style={{
                flex: 1,
                minWidth: "160px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                padding: "10px",
                borderRadius: "var(--radius-sm)",
                fontSize: "12px",
                fontWeight: "600",
                backgroundColor: providerType === "s3" ? "var(--accent-cyan-solid)" : "var(--bg-base)",
                color: providerType === "s3" ? "#ffffff" : "var(--text-secondary)",
                border: `1px solid ${providerType === "s3" ? "var(--accent-cyan-solid)" : "var(--border-strong)"}`,
              }}
            >
              <Database size={15} />
              <span>S3 / Cloudflare R2 / AWS S3</span>
            </button>
          </div>

          {addError && (
            <div
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
              <span>{addError}</span>
            </div>
          )}

          {/* Form Fields for Local macOS Storage */}
          {providerType === "local" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {/* Google Drive Desktop auto-sync helper banner */}
              <div
                style={{
                  padding: "12px 14px",
                  backgroundColor: "rgba(0, 229, 255, 0.05)",
                  border: "1px solid var(--accent-cyan-solid)",
                  borderRadius: "var(--radius-sm)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "10px",
                }}
              >
                <Cloud size={18} color="var(--accent-cyan-solid)" style={{ flexShrink: 0, marginTop: "2px" }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "12px", fontWeight: "700", color: "var(--text-primary)" }}>
                    Google Drive Desktop Live Auto-Sync
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginTop: "2px", lineHeight: "1.4" }}>
                    The official installer (<strong>GoogleDrive.dmg</strong>) has been opened for you on macOS. Once installed and signed in, select your synced folder (e.g. <code>sample</code> inside <code>~/Library/CloudStorage/GoogleDrive-...</code>). Chunks stored here will appear in your Google Drive cloud folder automatically!
                  </div>
                  <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                    <button
                      type="button"
                      onClick={fetchMacosLocations}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "11px",
                        fontWeight: "600",
                        padding: "4px 8px",
                        backgroundColor: "var(--accent-cyan-solid)",
                        color: "#fff",
                        border: "none",
                        borderRadius: "var(--radius-xs)",
                        cursor: "pointer",
                      }}
                    >
                      <RefreshCw size={11} className={loadingLocations ? "animate-spin" : ""} />
                      <span>{loadingLocations ? "Scanning..." : "Rescan for Synced Folders"}</span>
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "12px" }}>
                <div>
                  <label
                    htmlFor="drive-name"
                    style={{
                      display: "block",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: "var(--text-secondary)",
                      marginBottom: "4px",
                    }}
                  >
                    STORAGE UNIT NAME
                  </label>
                  <input
                    id="drive-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="e.g. Macintosh HD (Documents)"
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
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <label
                      htmlFor="drive-path"
                      style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)" }}
                    >
                      MACOS FOLDER PATH
                    </label>
                    <button
                      type="button"
                      onClick={handleOpenNativeDirectoryPicker}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "11px",
                        color: "var(--accent-cyan-solid)",
                        backgroundColor: "transparent",
                        border: "none",
                        cursor: "pointer",
                        fontWeight: "600",
                        padding: 0,
                      }}
                    >
                      <FolderPlus size={13} />
                      <span>Browse macOS Folder...</span>
                    </button>
                  </div>
                  <input
                    id="drive-path"
                    type="text"
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                    placeholder="e.g. /Users/shivanggupta/Documents/FrankensteinStorage or /Volumes/USB"
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
              </div>

              {/* Detected macOS Presets */}
              {macosLocations.length > 0 && (
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: "var(--text-muted)",
                      marginBottom: "6px",
                    }}
                  >
                    <Compass size={13} />
                    <span>
                      QUICK-SELECT DETECTED MACOS STORAGE TARGETS
                      {loadingLocations ? " (Scanning macOS disks...)" : ":"}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "8px" }}>
                    {macosLocations.map((loc, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => handleSelectPreset(loc)}
                        style={{
                          textAlign: "left",
                          padding: "10px 12px",
                          backgroundColor: path === loc.path ? "var(--accent-cyan-glow)" : "var(--bg-base)",
                          border: `1px solid ${path === loc.path ? "var(--accent-cyan-solid)" : loc.is_cloud_synced ? "var(--accent-cyan-solid)" : "var(--border-subtle)"}`,
                          borderRadius: "var(--radius-sm)",
                          cursor: "pointer",
                          display: "flex",
                          flexDirection: "column",
                          gap: "4px",
                          boxShadow: loc.is_cloud_synced ? "0 0 8px rgba(0, 229, 255, 0.15)" : "none",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" }}>
                          <span style={{ fontSize: "12px", fontWeight: "600", color: "var(--text-primary)" }}>
                            {loc.name}
                          </span>
                          {loc.is_cloud_synced ? (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                backgroundColor: "var(--accent-cyan-solid)",
                                color: "#ffffff",
                                borderRadius: "var(--radius-xs)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Cloud size={10} />
                              <span>AUTO-SYNC</span>
                            </span>
                          ) : (loc.is_external || loc.is_removable) ? (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                backgroundColor: "rgba(6, 182, 212, 0.2)",
                                color: "#38bdf8",
                                border: "1px solid rgba(56, 189, 248, 0.4)",
                                borderRadius: "var(--radius-xs)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Usb size={10} />
                              <span>USB DRIVE</span>
                            </span>
                          ) : null}
                        </div>
                        <div style={{ fontSize: "10px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                          Free: {formatBytes(loc.free)} • {loc.is_cloud_synced ? "Live Google Drive Sync" : loc.is_external ? "External USB/SSD" : "Internal SSD"}
                        </div>
                        {loc.description && (
                          <div style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "2px" }}>
                            {loc.description}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : providerType === "gdrive" ? (
            /* Form Fields for Google Drive Link */
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div>
                <label
                  htmlFor="gdrive-link-input"
                  style={{
                    display: "block",
                    fontSize: "11px",
                    fontWeight: "600",
                    color: "var(--text-secondary)",
                    marginBottom: "4px",
                  }}
                >
                  GOOGLE DRIVE FOLDER LINK
                </label>
                <input
                  id="gdrive-link-input"
                  type="text"
                  value={gdriveLink}
                  onChange={(e) => handleGdriveLinkChange(e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/1znENWSkjEl2CalOwup5uBSSh8UDgUrnk?usp=drive_link"
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    backgroundColor: "var(--bg-base)",
                    border: "1px solid var(--border-strong)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "13px",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-primary)",
                  }}
                />
                {gdriveFolderId ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--status-online)", marginTop: "4px" }}>
                    <CheckCircle2 size={13} />
                    <span>Detected Folder ID: <strong>{gdriveFolderId}</strong></span>
                  </div>
                ) : (
                  <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
                    Paste any Google Drive folder sharing link. Frankenstein Storage connects directly to this cloud destination.
                  </div>
                )}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label
                    htmlFor="gdrive-name"
                    style={{
                      display: "block",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: "var(--text-secondary)",
                      marginBottom: "4px",
                    }}
                  >
                    DISPLAY NAME
                  </label>
                  <input
                    id="gdrive-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="e.g. My Google Drive (Cloud)"
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
                </div>

                <div>
                  <label
                    style={{
                      display: "block",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: "var(--text-secondary)",
                      marginBottom: "4px",
                    }}
                  >
                    CONNECTION MODE
                  </label>
                  <select
                    value={gdriveAuthType}
                    onChange={(e) => setGdriveAuthType(e.target.value as any)}
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      backgroundColor: "var(--bg-base)",
                      border: "1px solid var(--border-strong)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "12px",
                      color: "var(--text-primary)",
                    }}
                  >
                    <option value="demo_mock">Direct Link / 15 GiB Cloud (0-config instant test)</option>
                    <option value="access_token">Live Google OAuth2 Token</option>
                  </select>
                </div>
              </div>

              {gdriveAuthType === "access_token" && (
                <div>
                  <input
                    type="password"
                    value={gdriveToken}
                    onChange={(e) => setGdriveToken(e.target.value)}
                    placeholder="Paste Google OAuth2 Access Token (ya29...)"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      backgroundColor: "var(--bg-base)",
                      border: "1px solid var(--border-strong)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "12px",
                      fontFamily: "var(--font-mono)",
                      color: "var(--text-primary)",
                    }}
                  />
                </div>
              )}
            </div>
          ) : providerType === "s3" ? (
            /* S3-Compatible Storage Form */
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {/* Presets Bar */}
              <div>
                <div style={{ fontSize: "11px", fontWeight: "600", color: "var(--text-muted)", marginBottom: "6px" }}>
                  QUICK PRESETS:
                </div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => handleApplyS3Preset("r2")}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      backgroundColor: s3Subtype === "r2" ? "rgba(249, 115, 22, 0.2)" : "var(--bg-base)",
                      color: s3Subtype === "r2" ? "#f97316" : "var(--text-secondary)",
                      border: `1px solid ${s3Subtype === "r2" ? "#f97316" : "var(--border-strong)"}`,
                      cursor: "pointer",
                    }}
                  >
                    Cloudflare R2 (10 GiB Free)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyS3Preset("s3")}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      backgroundColor: s3Subtype === "s3" ? "rgba(234, 179, 8, 0.2)" : "var(--bg-base)",
                      color: s3Subtype === "s3" ? "#eab308" : "var(--text-secondary)",
                      border: `1px solid ${s3Subtype === "s3" ? "#eab308" : "var(--border-strong)"}`,
                      cursor: "pointer",
                    }}
                  >
                    AWS S3 (US-East-1)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyS3Preset("b2")}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      backgroundColor: s3Subtype === "b2" ? "rgba(59, 130, 246, 0.2)" : "var(--bg-base)",
                      color: s3Subtype === "b2" ? "#3b82f6" : "var(--text-secondary)",
                      border: `1px solid ${s3Subtype === "b2" ? "#3b82f6" : "var(--border-strong)"}`,
                      cursor: "pointer",
                    }}
                  >
                    Backblaze B2 (10 GiB Free)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyS3Preset("minio")}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      backgroundColor: s3Subtype === "minio" ? "rgba(168, 85, 247, 0.2)" : "var(--bg-base)",
                      color: s3Subtype === "minio" ? "#a855f7" : "var(--text-secondary)",
                      border: `1px solid ${s3Subtype === "minio" ? "#a855f7" : "var(--border-strong)"}`,
                      cursor: "pointer",
                    }}
                  >
                    MinIO / Local S3
                  </button>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    STORAGE UNIT NAME
                  </label>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="e.g. Cloudflare R2 Secondary"
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
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    S3 BUCKET NAME *
                  </label>
                  <input
                    type="text"
                    value={s3Bucket}
                    onChange={(e) => setS3Bucket(e.target.value)}
                    placeholder="frankenstein-vault"
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
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                  ENDPOINT URL
                </label>
                <input
                  type="text"
                  value={s3Endpoint}
                  onChange={(e) => setS3Endpoint(e.target.value)}
                  placeholder="e.g. https://<account_id>.r2.cloudflarestorage.com or https://s3.amazonaws.com"
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

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    ACCESS KEY ID (Optional for Mock)
                  </label>
                  <input
                    type="text"
                    value={s3AccessKey}
                    onChange={(e) => setS3AccessKey(e.target.value)}
                    placeholder="Leave empty or use test key for mock"
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
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    SECRET ACCESS KEY
                  </label>
                  <input
                    type="password"
                    value={s3SecretKey}
                    onChange={(e) => setS3SecretKey(e.target.value)}
                    placeholder="Secret Key"
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
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    REGION (Defaults to auto)
                  </label>
                  <input
                    type="text"
                    value={s3Region}
                    onChange={(e) => setS3Region(e.target.value)}
                    placeholder="auto"
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
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "11px", fontWeight: "600", color: "var(--text-secondary)", marginBottom: "4px" }}>
                    CHUNK SUBFOLDER PREFIX
                  </label>
                  <input
                    type="text"
                    value={s3Prefix}
                    onChange={(e) => setS3Prefix(e.target.value)}
                    placeholder="chunks/"
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
                </div>
              </div>

              <div
                style={{
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  lineHeight: "1.4",
                  padding: "8px 12px",
                  backgroundColor: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                Zero external AWS SDK dependencies. Authenticates directly with S3 API via AWS Signature Version 4. If credentials are left blank or test keys are used, safe local mock storage is used automatically.
              </div>
            </div>
          ) : null}

          {/* Form Actions */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "4px" }}>
            <button
              type="button"
              className="btn-interactive"
              onClick={() => {
                setShowAddForm(false);
                setAddError(null);
              }}
              style={{
                padding: "8px 14px",
                fontSize: "12px",
                color: "var(--text-secondary)",
                backgroundColor: "transparent",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-interactive"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 18px",
                backgroundColor: "var(--accent-cyan-solid)",
                color: "#ffffff",
                fontWeight: "600",
                fontSize: "12px",
                borderRadius: "var(--radius-sm)",
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting
                ? "Connecting..."
                : providerType === "gdrive"
                ? "Connect Google Drive Link"
                : providerType === "s3"
                ? "Connect S3 / Cloudflare R2"
                : "Register Storage"}
            </button>
          </div>
        </form>
      )}

      {/* Drives list */}
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {drives.length === 0 && !loading && (
          <div
            style={{
              padding: "36px 24px",
              textAlign: "center",
              color: "var(--text-muted)",
              border: "1px dashed var(--border-strong)",
              borderRadius: "var(--radius-md)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <HardDrive size={34} style={{ opacity: 0.4 }} />
            <div>
              <div style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-secondary)" }}>
                No storage drives connected to pool
              </div>
              <div style={{ fontSize: "12px", marginTop: "4px", maxWidth: "420px" }}>
                Add your real macOS storage folders or Google Drive link above to create your fault-tolerant storage pool.
              </div>
            </div>

            <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
              <button
                type="button"
                className="btn-interactive"
                onClick={handleAutoSetupRealDrives}
                disabled={isAutoSettingUp}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 16px",
                  backgroundColor: "var(--accent-cyan-solid)",
                  color: "#ffffff",
                  fontWeight: "600",
                  fontSize: "12px",
                  borderRadius: "var(--radius-sm)",
                  cursor: isAutoSettingUp ? "not-allowed" : "pointer",
                }}
              >
                <Zap size={14} />
                <span>{isAutoSettingUp ? "Initializing..." : "Auto-Setup Real macOS Storage (3 Units)"}</span>
              </button>

              <button
                type="button"
                className="btn-interactive"
                onClick={() => {
                  setShowAddForm(true);
                  setProviderType("gdrive");
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 14px",
                  backgroundColor: "var(--bg-surface-elevated)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-strong)",
                  fontSize: "12px",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <Cloud size={14} />
                <span>Add Google Drive Link</span>
              </button>
            </div>
          </div>
        )}

        {/* Unmounted Detected USB Pendrives Banner */}
        {(() => {
          const unmountedUsbs = externalDrives.filter(
            (usb) => !drives.some((d) => d.path === usb.path || d.path.startsWith(usb.path.replace("/FrankensteinStorage", "")))
          );
          if (unmountedUsbs.length === 0) return null;
          return unmountedUsbs.map((usb) => (
            <div
              key={usb.path}
              style={{
                background: "linear-gradient(135deg, rgba(6, 182, 212, 0.12), rgba(59, 130, 246, 0.12))",
                border: "1px solid rgba(6, 182, 212, 0.45)",
                borderRadius: "var(--radius-md, 10px)",
                padding: "14px 18px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: "12px",
                boxShadow: "0 4px 16px rgba(6, 182, 212, 0.1)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
                <div
                  style={{
                    width: "38px",
                    height: "38px",
                    borderRadius: "8px",
                    background: "rgba(6, 182, 212, 0.2)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--accent-cyan-solid, #06b6d4)",
                    flexShrink: 0,
                  }}
                >
                  <Usb size={20} />
                </div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--text-primary)" }}>
                      External USB Drive Detected
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        padding: "1px 6px",
                        borderRadius: "4px",
                        background: "rgba(6, 182, 212, 0.25)",
                        color: "#38bdf8",
                        border: "1px solid rgba(56, 189, 248, 0.4)",
                      }}
                    >
                      HOT-PLUG READY
                    </span>
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                    <strong>{usb.volume_name}</strong> • {formatBytes(usb.free)} free of {formatBytes(usb.total)} • Mount: <code style={{ fontSize: "11px", color: "var(--text-muted)" }}>{usb.path}</code>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onAddDrive(usb.path, usb.name, "local")}
                className="btn-interactive"
                style={{
                  background: "var(--accent-cyan-solid, #06b6d4)",
                  color: "#ffffff",
                  border: "none",
                  padding: "8px 16px",
                  borderRadius: "var(--radius-sm, 6px)",
                  fontWeight: 600,
                  fontSize: "12px",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  boxShadow: "0 2px 10px rgba(6, 182, 212, 0.25)",
                }}
              >
                <Usb size={15} />
                <span>Connect Detected USB Drive: {usb.volume_name}</span>
              </button>
            </div>
          ));
        })()}

        {drives.map((drive, idx) => {
          const driveColor = getDriveColor(idx);
          const isSimulated = drive.simulated_offline;
          const isEjected = drive.status === "ejected";
          const isOnline = drive.status === "online" && !isSimulated && !isEjected;
          const isGdrive =
            drive.provider_type === "gdrive" ||
            drive.path.startsWith("gdrive://") ||
            drive.path.includes("drive.google.com") ||
            drive.path.includes("GoogleDrive") ||
            drive.path.includes("CloudStorage") ||
            drive.display_name.toLowerCase().includes("google drive") ||
            Boolean(drive.usage?.source?.includes("Google Drive"));

          const isUsb = Boolean(
            drive.is_external ||
            drive.is_removable ||
            drive.path.startsWith("/Volumes/") ||
            drive.display_name.toLowerCase().includes("usb") ||
            drive.usage?.source?.toLowerCase().includes("usb") ||
            drive.volume_name?.toLowerCase().includes("usb")
          );

          const total = drive.usage?.total || 0;
          const used = drive.usage?.used || 0;
          const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;

          return (
            <div
              key={drive.id}
              className="card-interactive"
              style={{
                backgroundColor: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "14px 16px",
                display: "flex",
                flexDirection: "column",
                gap: "10px",
                opacity: isOnline ? 1 : 0.85,
              }}
            >
              {/* Drive header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                  {/* Solid drive color indicator */}
                  <span
                    style={{
                      width: "10px",
                      height: "10px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: driveColor,
                      boxShadow: "var(--shadow-sm)",
                      flexShrink: 0,
                    }}
                    title={`Drive accent color: ${drive.display_name}`}
                  />

                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-primary)" }}>
                        {drive.display_name}
                      </span>
                      {(() => {
                        const isICloud = Boolean(
                          drive.provider_type === "icloud" ||
                          drive.path.includes("Mobile Documents") ||
                          drive.path.includes("com~apple~CloudDocs") ||
                          drive.display_name.toLowerCase().includes("icloud") ||
                          drive.usage?.source?.toLowerCase().includes("icloud")
                        );

                        const isOneDrive = Boolean(
                          drive.provider_type === "onedrive" ||
                          drive.path.toLowerCase().includes("onedrive") ||
                          drive.display_name.toLowerCase().includes("onedrive") ||
                          drive.usage?.source?.toLowerCase().includes("onedrive")
                        );

                        const isDropbox = Boolean(
                          drive.provider_type === "dropbox" ||
                          drive.path.toLowerCase().includes("dropbox") ||
                          drive.display_name.toLowerCase().includes("dropbox") ||
                          drive.usage?.source?.toLowerCase().includes("dropbox")
                        );

                        const isR2 = Boolean(
                          drive.provider_type === "r2" ||
                          drive.path.toLowerCase().includes("r2") ||
                          drive.display_name.toLowerCase().includes("r2") ||
                          drive.usage?.source?.toLowerCase().includes("r2")
                        );

                        const isS3 = Boolean(
                          drive.provider_type === "s3" ||
                          drive.provider_type === "minio" ||
                          drive.provider_type === "b2" ||
                          drive.path.startsWith("s3://") ||
                          drive.display_name.toLowerCase().includes("s3") ||
                          drive.usage?.source?.toLowerCase().includes("s3")
                        );

                        if (isICloud) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(56, 189, 248, 0.15)",
                                color: "#38bdf8",
                                border: "1px solid rgba(56, 189, 248, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Cloud size={10} />
                              <span>ICLOUD DRIVE</span>
                            </span>
                          );
                        }

                        if (isR2) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(249, 115, 22, 0.15)",
                                color: "#f97316",
                                border: "1px solid rgba(249, 115, 22, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Database size={10} />
                              <span>CLOUDFLARE R2</span>
                            </span>
                          );
                        }

                        if (isS3) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(234, 179, 8, 0.15)",
                                color: "#eab308",
                                border: "1px solid rgba(234, 179, 8, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Database size={10} />
                              <span>AWS S3 / OBJECT</span>
                            </span>
                          );
                        }

                        if (isOneDrive) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(37, 99, 235, 0.15)",
                                color: "#3b82f6",
                                border: "1px solid rgba(37, 99, 235, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Cloud size={10} />
                              <span>ONEDRIVE</span>
                            </span>
                          );
                        }

                        if (isDropbox) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(99, 102, 241, 0.15)",
                                color: "#818cf8",
                                border: "1px solid rgba(99, 102, 241, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Cloud size={10} />
                              <span>DROPBOX</span>
                            </span>
                          );
                        }

                        if (isGdrive) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "var(--bg-base)",
                                color: "var(--accent-cyan-solid)",
                                border: "1px solid var(--accent-cyan-solid)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Cloud size={10} />
                              <span>GOOGLE DRIVE</span>
                            </span>
                          );
                        }

                        if (isUsb) {
                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                fontWeight: "700",
                                padding: "1px 6px",
                                backgroundColor: "rgba(6, 182, 212, 0.15)",
                                color: "var(--accent-cyan-solid, #06b6d4)",
                                border: "1px solid rgba(6, 182, 212, 0.4)",
                                borderRadius: "var(--radius-sm)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <Usb size={10} />
                              <span>EXTERNAL USB</span>
                            </span>
                          );
                        }

                        return (
                          <span
                            style={{
                              fontSize: "9px",
                              fontWeight: "700",
                              padding: "1px 6px",
                              backgroundColor: "var(--bg-base)",
                              color: "var(--text-muted)",
                              border: "1px solid var(--border-strong)",
                              borderRadius: "var(--radius-sm)",
                            }}
                          >
                            MACOS LOCAL
                          </span>
                        );
                      })()}
                      {drive.shared_device && (
                        <span
                          style={{
                            fontSize: "9px",
                            fontWeight: "700",
                            padding: "1px 6px",
                            backgroundColor: "rgba(255, 170, 0, 0.12)",
                            color: "var(--accent-orange, #f59e0b)",
                            border: "1px solid rgba(255, 170, 0, 0.35)",
                            borderRadius: "var(--radius-sm)",
                          }}
                          title={`Shares underlying physical storage volume (${drive.shared_volume_name || 'Physical APFS Volume'}) with ${drive.shared_device_count} drives`}
                        >
                          SHARED VOLUME ({drive.shared_device_count})
                        </span>
                      )}
                      {drive.exclusion_reason && (
                        <span
                          style={{
                            fontSize: "9px",
                            fontWeight: "700",
                            padding: "1px 6px",
                            backgroundColor: "rgba(239, 68, 68, 0.12)",
                            color: "#ef4444",
                            border: "1px solid rgba(239, 68, 68, 0.35)",
                            borderRadius: "var(--radius-sm)",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "3px",
                          }}
                          title={`Excluded from placement: ${drive.exclusion_reason}`}
                        >
                          <AlertTriangle size={10} />
                          <span>{drive.exclusion_reason.includes("Low space") ? "LOW SPACE (EXCLUDED)" : drive.exclusion_reason.toUpperCase()}</span>
                        </span>
                      )}
                      {pct >= 90 && (
                        <span
                          style={{
                            fontSize: "9px",
                            fontWeight: "700",
                            padding: "1px 6px",
                            backgroundColor: "rgba(245, 158, 11, 0.12)",
                            color: "#f59e0b",
                            border: "1px solid rgba(245, 158, 11, 0.35)",
                            borderRadius: "var(--radius-sm)",
                          }}
                          title="Drive usage is above 90% threshold"
                        >
                          &gt;90% USED
                        </span>
                      )}
                    </div>

                    <div style={{ marginTop: "2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {drive.path.startsWith("http") ? (
                        <a
                          href={drive.path}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            color: "var(--accent-cyan-solid)",
                            fontSize: "11px",
                            textDecoration: "none",
                          }}
                          title={drive.path}
                        >
                          <span>{drive.path.length > 56 ? drive.path.slice(0, 54) + "..." : drive.path}</span>
                          <ExternalLink size={11} />
                        </a>
                      ) : (
                        <span
                          style={{
                            fontSize: "11px",
                            color: "var(--text-muted)",
                            fontFamily: "var(--font-mono)",
                          }}
                          title={drive.path}
                        >
                          {drive.path}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Status chip & Controls */}
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  {/* Status chip */}
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                      padding: "3px 8px",
                      borderRadius: "var(--radius-full)",
                      fontSize: "10px",
                      fontWeight: "700",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      backgroundColor: isOnline
                        ? "var(--status-online-bg)"
                        : isEjected
                        ? "rgba(245, 158, 11, 0.12)"
                        : isSimulated
                        ? "var(--status-simulated-bg)"
                        : isUsb
                        ? "rgba(239, 68, 68, 0.15)"
                        : "var(--status-offline-bg)",
                      border: `1px solid ${
                        isOnline
                          ? "var(--status-online)"
                          : isEjected
                          ? "#f59e0b"
                          : isSimulated
                          ? "var(--status-simulated)"
                          : isUsb
                          ? "#ef4444"
                          : "var(--status-offline)"
                      }`,
                      color: isOnline
                        ? "var(--status-online-text)"
                        : isEjected
                        ? "#f59e0b"
                        : isSimulated
                        ? "var(--status-simulated-text)"
                        : isUsb
                        ? "#ef4444"
                        : "var(--status-offline-text)",
                    }}
                  >
                    <span
                      style={{
                        width: "5px",
                        height: "5px",
                        borderRadius: "50%",
                        backgroundColor: isOnline
                          ? "var(--status-online)"
                          : isEjected
                          ? "#f59e0b"
                          : isSimulated
                          ? "var(--status-simulated)"
                          : isUsb
                          ? "#ef4444"
                          : "var(--status-offline)",
                      }}
                    />
                    <span>
                      {isOnline
                        ? isUsb
                          ? "Online (USB)"
                          : "Online"
                        : isEjected
                        ? "Ejected / Unplugged"
                        : isSimulated
                        ? "Simulated offline"
                        : isUsb
                        ? "Unplugged / Offline"
                        : "Unavailable"}
                    </span>
                  </span>

                  {/* Safe Eject button for external USB pendrives */}
                  {isUsb && (
                    <button
                      className="btn-interactive"
                      onClick={() => handleEjectDrive(drive.id)}
                      disabled={Boolean(ejectingIds[drive.id]) || isEjected}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "5px",
                        padding: "4px 8px",
                        backgroundColor: isEjected ? "rgba(245, 158, 11, 0.05)" : "rgba(245, 158, 11, 0.12)",
                        border: `1px solid ${isEjected ? "rgba(245, 158, 11, 0.25)" : "rgba(245, 158, 11, 0.45)"}`,
                        borderRadius: "var(--radius-sm)",
                        fontSize: "11px",
                        fontWeight: "600",
                        color: isEjected ? "rgba(245, 158, 11, 0.6)" : "#f59e0b",
                        cursor: ejectingIds[drive.id] || isEjected ? "not-allowed" : "pointer",
                      }}
                      aria-label={`Safely unmount and eject ${drive.display_name}`}
                      title={isEjected ? "Pendrive already ejected" : "Safely unmount and eject USB pendrive"}
                    >
                      {ejectingIds[drive.id] ? (
                        <>
                          <Loader2 size={12} className="spin" />
                          <span>Ejecting...</span>
                        </>
                      ) : (
                        <>
                          <Eject size={12} />
                          <span>{isEjected ? "Ejected" : "Eject"}</span>
                        </>
                      )}
                    </button>
                  )}

                  {/* Toggle simulated offline button */}
                  <button
                    className="btn-interactive"
                    onClick={() => onToggleOffline(drive.id, drive.simulated_offline)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                      padding: "4px 8px",
                      backgroundColor: isSimulated ? "var(--status-online-bg)" : "var(--status-simulated-bg)",
                      border: `1px solid ${isSimulated ? "var(--status-online)" : "var(--status-simulated)"}`,
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      fontWeight: "600",
                      color: isSimulated ? "var(--status-online-text)" : "var(--status-simulated-text)",
                    }}
                    aria-label={isSimulated ? `Bring ${drive.display_name} online` : `Simulate ${drive.display_name} offline`}
                    title={isSimulated ? "Re-enable drive" : "Take drive offline for parity demonstration"}
                  >
                    <Power size={12} />
                    <span>{isSimulated ? "Bring Online" : "Take Offline"}</span>
                  </button>

                  {/* Delete drive button */}
                  <button
                    className="btn-interactive"
                    onClick={() => onDeleteDrive(drive.id)}
                    style={{
                      padding: "4px 6px",
                      color: "var(--text-muted)",
                      borderRadius: "var(--radius-sm)",
                    }}
                    aria-label={`Remove drive ${drive.display_name}`}
                    title="Remove drive"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Capacity usage bar & chunk counts */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "4px" }}>
                  <span style={{ color: "var(--text-secondary)" }}>
                    Usage: <strong style={{ color: "var(--text-primary)" }}>{formatBytes(used)}</strong> / {formatBytes(total)} ({pct}%)
                  </span>
                  <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
                    <strong style={{ color: "var(--text-secondary)" }}>{drive.chunk_count}</strong> chunks ({formatBytes(drive.chunks_total_bytes)}) • {drive.usage?.source || (isGdrive ? "Google Drive Cloud (15 GiB)" : "macOS Storage")}
                  </span>
                </div>

                <div
                  style={{
                    height: "4px",
                    backgroundColor: "var(--bg-base)",
                    borderRadius: "var(--radius-full)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${pct}%`,
                      backgroundColor: isOnline ? driveColor : "var(--text-muted)",
                      borderRadius: "var(--radius-full)",
                      transition: "width 300ms ease",
                    }}
                  />
                </div>
              </div>

              {isEjected ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "8px 12px",
                    backgroundColor: "rgba(245, 158, 11, 0.08)",
                    border: "1px solid rgba(245, 158, 11, 0.25)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    color: "#f59e0b",
                  }}
                >
                  <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                  <span>Pendrive ejected. Re-insert USB drive to reconnect to the storage pool.</span>
                </div>
              ) : isUsb && !isOnline && !isSimulated ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "8px 12px",
                    backgroundColor: "rgba(239, 68, 68, 0.08)",
                    border: "1px solid rgba(239, 68, 68, 0.25)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "12px",
                    color: "#f87171",
                  }}
                >
                  <AlertCircle size={15} style={{ flexShrink: 0 }} />
                  <span>Pendrive disconnected. Plug back in or rebuild from parity.</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};
