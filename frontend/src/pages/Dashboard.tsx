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

  const handleAddDrive = async (
    path: string,
    displayName: string,
    providerType: "local" | "gdrive" = "local",
    config?: Record<string, any>
  ) => {
    await api.addDrive(path, displayName, providerType, config);
    addToast(
      "success",
      `Drive '${displayName}' registered (${providerType === "gdrive" ? "Google Drive" : "Local"})`
    );
    await refreshData();
  };

  const onlineDrivesCount = drives.filter((d) => d.status === "online" && !d.simulated_offline).length;

  const executeUpload = async (file: File, overwrite: boolean, mode: StorageMode) => {
    try {
      setUploadProgress(0);
      await api.uploadFile(file, overwrite, mode, (pct) => setUploadProgress(pct));
      const modeDesc =
        mode === "whole" ? "as whole encrypted object" : "chunked & striped with XOR parity";
      addToast("success", `File '${file.name}' uploaded ${modeDesc}`);
      await refreshData();
    } catch (err: any) {
      addToast("error", err.message || "Upload failed");
    } finally {
      setUploadProgress(null);
    }
  };

  const handleUploadFile = async (file: File, overwrite: boolean) => {
    // Check if user has a saved preference
    const savedMode = preference?.preferred_mode;

    if (savedMode) {
      // Validate mode against available online drives
      if (savedMode === "chunked_parity" && onlineDrivesCount < 3) {
        addToast(
          "error",
          `Default mode is Chunked + Parity, but only ${onlineDrivesCount} drive(s) are online (needs 3). Please choose storage mode.`
        );
        setPendingUpload({ file, overwrite });
        return;
      }
      // Preference exists and is valid: bypass dialog
      await executeUpload(file, overwrite, savedMode);
    } else {
      // No saved preference: prompt with Smart Upload Decision dialog
      setPendingUpload({ file, overwrite });
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
      addToast("info", `Reassembling & downloading '${file.name}'...`);
      await api.downloadFile(file.id, file.name);
      addToast("success", `Downloaded '${file.name}' successfully`);
    } catch (err: any) {
      addToast("error", err.message || "Download failed");
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
