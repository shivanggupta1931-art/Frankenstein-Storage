import React, { useState, useEffect, useCallback } from "react";
import { TopBar } from "../components/TopBar";
import { PoolOverview } from "../components/PoolOverview";
import { DrivesPanel } from "../components/DrivesPanel";
import { FilesPanel } from "../components/FilesPanel";
import { FileDetailsDrawer } from "../components/FileDetailsDrawer";
import { FilePreviewModal } from "../components/FilePreviewModal";
import { UnlockModal } from "../components/UnlockModal";
import { SettingsModal } from "../components/SettingsModal";
import { ActivityModal } from "../components/ActivityModal";
import { UploadDecisionModal, StorageMode } from "../components/UploadDecisionModal";
import { Toasts } from "../components/Toasts";
import { api } from "../services/api";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Drive, StoredFile, PoolOverview as PoolOverviewType, ToastMessage, UploadPreference } from "../types";

export const Dashboard: React.FC = () => {
  // State
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    return (localStorage.getItem("frankenstein_theme") as "dark" | "light") || "dark";
  });
  const [unlocked, setUnlocked] = useState(false);
  const [healthOk, setHealthOk] = useState(true);
  const [overview, setOverview] = useState<PoolOverviewType | null>(null);
  const [drives, setDrives] = useState<Drive[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [healing, setHealing] = useState(false);
  const [healProgress, setHealProgress] = useState<number | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("frankenstein_theme", theme);
  }, [theme]);

  const handleToggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    addToast("info", `Switched to ${nextTheme} theme`);
  };

  // Modals & drawers
  const [showUnlockModal, setShowUnlockModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showActivityModal, setShowActivityModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<StoredFile | null>(null);
  const [previewFile, setPreviewFile] = useState<StoredFile | null>(null);
  const [preference, setPreference] = useState<UploadPreference | null>(null);
  const [pendingUpload, setPendingUpload] = useState<{ file: File; overwrite: boolean } | null>(null);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: "success" | "error" | "info", message: string) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Main data fetching
  const refreshData = useCallback(async () => {
    try {
      const health = await api.getHealth();
      setHealthOk(true);
      setUnlocked(health.unlocked);

      if (!health.unlocked) {
        // Vault is locked: load overview only if possible, or show unlock modal
        try {
          const ov = await api.getOverview();
          setOverview(ov);
          const dr = await api.getDrives();
          setDrives(dr);
        } catch {
          // unauthed or locked
        }
        return;
      }

      // Vault is unlocked: fetch all data concurrently
      const [ov, dr, fl, pref] = await Promise.all([
        api.getOverview(),
        api.getDrives(),
        api.getFiles(),
        api.getUploadPreference().catch(() => null),
      ]);

      setOverview(ov);
      setDrives(dr);
      setFiles(fl);
      if (pref) setPreference(pref);

      // If drawer is open, keep selected file refreshed
      if (selectedFile) {
        const found = fl.find((f) => f.id === selectedFile.id);
        if (found) setSelectedFile(found);
      }
    } catch (err: any) {
      if (err.status === 401) {
        addToast("error", "Unauthorized: Please configure your Session Token in Token Settings");
        setShowSettingsModal(true);
      } else {
        setHealthOk(false);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedFile]);

  // Initial load
  useEffect(() => {
    refreshData();
    // Prompt unlock on initial mount if locked
    api.getHealth()
      .then((h) => {
        if (!h.unlocked) setShowUnlockModal(true);
      })
      .catch(() => {});

    // Polling interval for drive and pool sync
    const interval = setInterval(refreshData, 10000);
    return () => clearInterval(interval);
  }, []);

  // Handlers
  const handleUnlock = async (password: string) => {
    await api.unlock(password);
    setUnlocked(true);
    addToast("success", "Storage vault unlocked successfully");
    await refreshData();
  };

  const handleLock = async () => {
    await api.lock();
    setUnlocked(false);
    addToast("info", "Storage vault locked");
    await refreshData();
  };

  const handleToggleOffline = async (driveId: string, currentOffline: boolean) => {
    try {
      const updated = await api.patchDrive(driveId, !currentOffline);
      addToast(
        "info",
        `Drive ${updated.display_name} set to ${updated.simulated_offline ? "Simulated offline" : "Online"}`
      );
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Failed to toggle drive status");
    }
  };

  const handleDeleteDrive = async (driveId: string) => {
    try {
      await api.deleteDrive(driveId);
      addToast("success", "Drive removed successfully");
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Cannot delete drive");
    }
  };

  const handleEjectDrive = async (driveId: string) => {
    try {
      const res = await api.ejectDrive(driveId);
      addToast(
        "success",
        res.message || `USB Drive '${res.volume_name}' safely unmounted. You can now physically unplug your pendrive.`
      );
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Failed to safely eject USB drive");
    }
  };

  const handleAddDrive = async (
    path: string,
    displayName: string,
    providerType: "local" | "gdrive" | "s3" | "r2" | "minio" | "b2" | "icloud" | "onedrive" | "dropbox" = "local",
    config?: Record<string, any>
  ) => {
    await api.addDrive(path, displayName, providerType, config);
    const typeLabel =
      providerType === "gdrive"
        ? "Google Drive"
        : providerType === "icloud"
        ? "Apple iCloud Drive"
        : providerType === "r2"
        ? "Cloudflare R2"
        : providerType === "s3"
        ? "AWS S3"
        : providerType === "onedrive"
        ? "Microsoft OneDrive"
        : providerType === "dropbox"
        ? "Dropbox"
        : "Local";
    addToast(
      "success",
      `Drive '${displayName}' registered (${typeLabel})`
    );
    await refreshData();
  };

  const onlineDrivesCount = drives.filter((d) => d.status === "online" && !d.simulated_offline).length;

  const executeUpload = async (file: File, overwrite: boolean, mode: StorageMode | "auto") => {
    try {
      setUploadProgress(0);
      await api.uploadFile(file, overwrite, mode as any, (pct) => setUploadProgress(pct));
      const modeDesc =
        mode === "whole"
          ? "as whole encrypted object"
          : mode === "mirrored"
          ? "mirrored across 2 drives"
          : mode === "chunked_parity"
          ? "chunked & striped with XOR parity"
          : "with automatic pool redundancy";
      addToast("success", `File '${file.name}' uploaded ${modeDesc}`);
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Upload failed");
    } finally {
      setUploadProgress(null);
    }
  };

  const handleUploadFile = async (file: File, overwrite: boolean) => {
    const savedMode = preference?.preferred_mode;
    if (savedMode) {
      await executeUpload(file, overwrite, savedMode);
    } else {
      await executeUpload(file, overwrite, "auto");
    }
  };

  const handleReprotectFile = async (fileId: string) => {
    try {
      addToast("info", "Re-protecting file across pool...");
      const res = await api.reprotectFile(fileId);
      addToast(
        "success",
        `File '${res.name}' re-protected (${res.new_mode === "chunked_parity" ? "XOR Parity" : "Mirrored 2x"})`
      );
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Re-protection failed");
    }
  };

  const handleReprotectAll = async () => {
    try {
      addToast("info", "Re-protecting all unprotected files...");
      const res = await api.reprotectAllFiles();
      addToast(
        "success",
        `Re-protection complete: ${res.reprotected} file(s) upgraded, ${res.skipped} skipped, ${res.failed} failed`
      );
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Bulk re-protection failed");
    }
  };

  const handleConfirmDecision = async (mode: StorageMode, remember: boolean) => {
    const pending = pendingUpload;
    setPendingUpload(null);
    if (!pending) return;

    if (remember) {
      try {
        const updated = await api.setUploadPreference(mode);
        setPreference(updated);
        addToast("info", `Preference saved: ${mode === "whole" ? "Whole Object" : "Chunked + Parity"}`);
      } catch (err: any) {
        // preference save failed but upload can still proceed
      }
    }

    await executeUpload(pending.file, pending.overwrite, mode);
  };

  const handleCancelDecision = () => {
    setPendingUpload(null);
    addToast("info", "Upload cancelled");
  };

  const handleDownloadFile = async (file: StoredFile) => {
    try {
      addToast("info", `Reassembling & verifying '${file.name}'...`);
      const res = await api.downloadFile(file.id, file.name);
      const rebuiltNote = res?.wasRebuilt ? " • Rebuilt on-the-fly from Parity/Mirror" : "";
      addToast(
        "success",
        `Downloaded '${file.name}' • Verified SHA-256 [${res?.sha256?.slice(0, 8)}...]${rebuiltNote}`
      );
    } catch (err: any) {
      addToast("error", err.message || "Download failed");
    }
  };

  const handleHealPool = async () => {
    setHealing(true);
    setHealProgress(25);
    try {
      addToast("info", "Rebuilding missing chunks from parity and mirror replicas...");
      setHealProgress(50);
      const res = await api.healPool();
      setHealProgress(100);
      if (res.status === "healed") {
        addToast(
          "success",
          `Storage Pool Healed: ${res.files_healed} file(s) restored, ${res.chunks_rebuilt} chunk(s) regenerated`
        );
      } else if (res.status === "healthy") {
        addToast(
          "success",
          `Storage Pool Healthy: All ${res.files_checked} file(s) already verified healthy`
        );
      } else {
        addToast(
          "error",
          `Heal Incomplete: ${res.unrecoverable_files?.length || 0} file(s) unrecoverable due to multiple drive failures`
        );
      }
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Heal failed");
    } finally {
      setTimeout(() => setHealProgress(null), 800);
      setHealing(false);
    }
  };

  const handleDeleteFile = async (file: StoredFile) => {
    if (!window.confirm(`Delete file '${file.name}' from storage pool?`)) return;
    try {
      await api.deleteFile(file.id);
      if (selectedFile?.id === file.id) setSelectedFile(null);
      addToast("success", `File '${file.name}' deleted`);
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Failed to delete file");
    }
  };

  const handleVerifyIntegrity = async () => {
    setVerifying(true);
    try {
      const res = await api.verifyIntegrity();
      if (res.status === "healthy") {
        addToast("success", `All ${res.chunks_checked} chunks verified healthy across ${res.files_checked} files`);
      } else if (res.status === "degraded") {
        addToast("info", `System degraded: ${res.corrupted_chunks} chunk(s) offline/corrupt but fully rebuildable via parity`);
      } else {
        addToast("error", `System corrupt: ${res.corrupted_chunks} chunk(s) unrecoverable`);
      }
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Integrity verification failed");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top Bar */}
      <TopBar
        unlocked={unlocked}
        healthOk={healthOk}
        theme={theme}
        onToggleTheme={handleToggleTheme}
        onOpenUnlock={() => setShowUnlockModal(true)}
        onLock={handleLock}
        onOpenSettings={() => setShowSettingsModal(true)}
        onOpenActivity={() => setShowActivityModal(true)}
        onVerifyIntegrity={handleVerifyIntegrity}
        verifying={verifying}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Pool Overview (Panel 1) */}
        <PoolOverview overview={overview} loading={loading} />

        {/* Degraded Mode Banner */}
        {unlocked &&
          (drives.some((d) => d.simulated_offline || !d.available) ||
            files.some((f) => f.health?.includes("Degraded"))) && (
            <div
              className="animate-slide-up"
              style={{
                margin: "0 28px 20px",
                padding: "14px 20px",
                backgroundColor: "rgba(245, 158, 11, 0.12)",
                border: "1px solid rgba(245, 158, 11, 0.4)",
                borderRadius: "var(--radius-md)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: "14px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <AlertTriangle size={22} color="#f59e0b" style={{ flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: "13px", fontWeight: "700", color: "#f59e0b" }}>
                    Storage Pool Degraded (Drive Disconnected / Offline)
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
                    Redundancy is reduced, but files remain downloadable and previewable by reconstructing missing chunks from XOR parity or mirror replicas.
                  </div>
                </div>
              </div>

              <button
                className="btn-interactive"
                onClick={handleHealPool}
                disabled={healing}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 18px",
                  backgroundColor: "#f59e0b",
                  color: "#ffffff",
                  fontWeight: "700",
                  fontSize: "12px",
                  borderRadius: "var(--radius-sm)",
                  border: "none",
                  cursor: healing ? "not-allowed" : "pointer",
                  opacity: healing ? 0.7 : 1,
                  boxShadow: "0 2px 4px rgba(245, 158, 11, 0.3)",
                }}
                title="Regenerate missing chunks on returned or replaced drives"
              >
                <RefreshCw size={13} className={healing ? "spin" : ""} />
                <span>{healing ? "Rebuilding Chunks..." : "Rebuild / Heal Pool"}</span>
              </button>
            </div>
          )}

        {/* Heal Progress Bar */}
        {healProgress !== null && (
          <div style={{ margin: "0 28px 16px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "11px",
                color: "var(--text-muted)",
                marginBottom: "4px",
              }}
            >
              <span>Rebuilding and restoring chunk redundancy across pool...</span>
              <span>{healProgress}%</span>
            </div>
            <div
              style={{
                width: "100%",
                height: "4px",
                backgroundColor: "var(--bg-surface-elevated)",
                borderRadius: "var(--radius-full)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${healProgress}%`,
                  height: "100%",
                  backgroundColor: "#f59e0b",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>
        )}

        {/* 2-Column Responsive Panel (Drives & Files) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
            gap: "24px",
            padding: "0 28px 48px",
          }}
        >
          {/* Drives Panel (Panel 2) */}
          <DrivesPanel
            drives={drives}
            loading={loading}
            onToggleOffline={handleToggleOffline}
            onDeleteDrive={handleDeleteDrive}
            onAddDrive={handleAddDrive}
            onEjectDrive={handleEjectDrive}
          />

          {/* Files Panel (Panel 3) */}
          <FilesPanel
            files={files}
            drives={drives}
            loading={loading}
            unlocked={unlocked}
            onUploadFile={handleUploadFile}
            onDownloadFile={handleDownloadFile}
            onDeleteFile={handleDeleteFile}
            onSelectFile={(f) => setSelectedFile(f)}
            onPreviewFile={(f) => setPreviewFile(f)}
            onReprotectFile={handleReprotectFile}
            onReprotectAll={handleReprotectAll}
            uploadProgress={uploadProgress}
          />
        </div>
      </main>

      {/* Modals & Drawers */}
      <UnlockModal
        isOpen={showUnlockModal}
        onClose={() => setShowUnlockModal(false)}
        onUnlock={handleUnlock}
      />

      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onSaved={refreshData}
      />

      <ActivityModal
        isOpen={showActivityModal}
        onClose={() => setShowActivityModal(false)}
      />

      <FileDetailsDrawer
        file={selectedFile}
        drives={drives}
        onClose={() => setSelectedFile(null)}
        onDownload={handleDownloadFile}
        onDelete={handleDeleteFile}
        onPreview={(f) => setPreviewFile(f)}
      />

      {/* In-App File Preview Modal */}
      <FilePreviewModal
        file={previewFile}
        onClose={() => setPreviewFile(null)}
        onDownload={handleDownloadFile}
      />

      {/* Smart Upload Decision Modal */}
      <UploadDecisionModal
        isOpen={pendingUpload !== null}
        file={pendingUpload?.file || null}
        onlineDrivesCount={onlineDrivesCount}
        thresholdBytes={preference?.threshold_bytes || 1048576}
        onConfirm={handleConfirmDecision}
        onCancel={handleCancelDecision}
      />

      {/* Toast Notifications */}
      <Toasts toasts={toasts} onDismiss={removeToast} />
    </div>
  );
};
