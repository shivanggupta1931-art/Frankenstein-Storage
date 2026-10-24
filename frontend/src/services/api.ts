import { Drive, StoredFile, PoolOverview, Chunk, ActivityItem, UploadPreference } from "../types";

const DEFAULT_BASE_URL = "http://127.0.0.1:8765/api/v1";

class ApiService {
  private baseUrl: string;
  private token: string;

  constructor() {
    this.baseUrl = localStorage.getItem("frankenstein_api_url") || DEFAULT_BASE_URL;
    this.token = localStorage.getItem("frankenstein_token") || "frankenstein-demo-token";
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  setBaseUrl(url: string): void {
    this.baseUrl = url.replace(/\/$/, "");
    localStorage.setItem("frankenstein_api_url", this.baseUrl);
  }

  getToken(): string {
    return this.token;
  }

  setToken(token: string): void {
    this.token = token.trim();
    localStorage.setItem("frankenstein_token", this.token);
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: { code: `HTTP_${response.status}`, message: response.statusText } };
      }
      const err = new Error(errorData.error?.message || `Request failed with ${response.status}`);
      (err as any).code = errorData.error?.code || "UNKNOWN_ERROR";
      (err as any).details = errorData.error?.details;
      (err as any).status = response.status;
      throw err;
    }

    return response.json();
  }

  async getHealth(): Promise<{ status: string; unlocked: boolean }> {
    return this.request<{ status: string; unlocked: boolean }>("/health");
  }

  async unlock(password: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>("/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
  }

  async lock(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>("/lock", {
      method: "POST",
    });
  }

  async getOverview(): Promise<PoolOverview> {
    return this.request<PoolOverview>("/overview");
  }

  async getDrives(): Promise<Drive[]> {
    return this.request<Drive[]>("/drives");
  }

  async addDrive(
    path: string,
    displayName: string,
    providerType: "local" | "gdrive" = "local",
    config?: Record<string, any>
  ): Promise<Drive> {
    return this.request<Drive>("/drives", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path,
        display_name: displayName,
        provider_type: providerType,
        config,
      }),
    });
  }

  async patchDrive(id: string, simulatedOffline?: boolean, displayName?: string): Promise<Drive> {
    return this.request<Drive>(`/drives/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulated_offline: simulatedOffline, display_name: displayName }),
    });
  }

  async getMacosStorageLocations(): Promise<{
    locations: Array<{
      name: string;
      path: string;
      total: number;
      free: number;
      used: number;
      is_external: boolean;
      is_cloud_synced?: boolean;
      description: string;
    }>;
  }> {
    return this.request("/system/macos-storage");
  }

  async setupRealDrives(): Promise<{ status: string; drives_created: Drive[] }> {
    return this.request("/system/setup-real-drives", {
      method: "POST",
    });
  }

  async deleteDrive(id: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/drives/${id}`, {
      method: "DELETE",
    });
  }

  async getFiles(sortBy?: string, order?: string): Promise<StoredFile[]> {
    const params = new URLSearchParams();
    if (sortBy) params.append("sort_by", sortBy);
    if (order) params.append("order", order);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return this.request<StoredFile[]>(`/files${qs}`);
  }

  async uploadFile(
    file: File,
    overwrite = false,
    mode?: "whole" | "chunked_parity",
    onProgress?: (pct: number) => void
  ): Promise<StoredFile> {
    const encodedName = encodeURIComponent(file.name);
    const modeParam = mode ? `&mode=${encodeURIComponent(mode)}` : "";
    const url = `${this.baseUrl}/files/upload?name=${encodedName}&overwrite=${overwrite}${modeParam}`;

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);

      if (this.token) {
        xhr.setRequestHeader("Authorization", `Bearer ${this.token}`);
      }
      xhr.setRequestHeader("Content-Type", "application/octet-stream");

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            onProgress(pct);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch (e) {
            reject(new Error("Invalid JSON response from server"));
          }
        } else {
          try {
            const errJson = JSON.parse(xhr.responseText);
            const err = new Error(errJson.error?.message || `Upload failed with status ${xhr.status}`);
            (err as any).code = errJson.error?.code || "UPLOAD_FAILED";
            (err as any).status = xhr.status;
            reject(err);
          } catch {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => reject(new Error("Network connection error during upload"));
      xhr.send(file);
    });
  }

  async downloadFile(
    fileId: string,
    filename: string
  ): Promise<{ verified: boolean; sha256: string; wasRebuilt: boolean }> {
    const url = `${this.baseUrl}/files/${fileId}/download`;
    const headers: Record<string, string> = {};
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const res = await fetch(url, { headers });
    if (!res.ok) {
      let errMsg = `Download failed with status ${res.status}`;
      try {
        const errJson = await res.json();
        errMsg = errJson.error?.message || errMsg;
      } catch {}
      throw new Error(errMsg);
    }

    const expectedSha = res.headers.get("X-File-SHA256") || res.headers.get("x-file-sha256");
    const wasRebuilt =
      (res.headers.get("X-Rebuilt-From-Parity") || res.headers.get("x-rebuilt-from-parity")) === "true";

    const blob = await res.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const calculatedSha = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");

    if (expectedSha && calculatedSha.toLowerCase() !== expectedSha.toLowerCase()) {
      throw new Error(
        `SHA-256 Integrity Verification Failed! Expected ${expectedSha.slice(0, 10)}... but got ${calculatedSha.slice(0, 10)}...`
      );
    }

    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(downloadUrl);

    return {
      verified: true,
      sha256: calculatedSha,
      wasRebuilt,
    };
  }

  async healPool(): Promise<any> {
    return this.request("/heal", {
      method: "POST",
    });
  }

  getPreviewUrl(fileId: string): string {
    const tokenParam = this.token ? `?token=${encodeURIComponent(this.token)}` : "";
    return `${this.baseUrl}/files/${fileId}/preview${tokenParam}`;
  }

  async fetchPreviewBlob(fileId: string): Promise<{ blob: Blob; mimeType: string }> {
    const url = `${this.baseUrl}/files/${fileId}/preview`;
    const headers: Record<string, string> = {};
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    const res = await fetch(url, { headers });
    if (!res.ok) {
      let errMsg = `Failed to preview file (Status ${res.status})`;
      try {
        const errJson = await res.json();
        errMsg = errJson.error?.message || errMsg;
      } catch {}
      throw new Error(errMsg);
    }
    const blob = await res.blob();
    const mimeType = res.headers.get("content-type") || blob.type || "application/octet-stream";
    return { blob, mimeType };
  }

  async fetchPreviewText(fileId: string): Promise<string> {
    const url = `${this.baseUrl}/files/${fileId}/preview`;
    const headers: Record<string, string> = {};
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    const res = await fetch(url, { headers });
    if (!res.ok) {
      let errMsg = `Failed to preview file (Status ${res.status})`;
      try {
        const errJson = await res.json();
        errMsg = errJson.error?.message || errMsg;
      } catch {}
      throw new Error(errMsg);
    }
    return res.text();
  }

  async getFileChunks(fileId: string): Promise<Chunk[]> {
    return this.request<Chunk[]>(`/files/${fileId}/chunks`);
  }

  async deleteFile(fileId: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/files/${fileId}`, {
      method: "DELETE",
    });
  }

  async verifyIntegrity(fileId?: string): Promise<any> {
    return this.request("/integrity/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: fileId, all: !fileId }),
    });
  }

  async getActivity(): Promise<ActivityItem[]> {
    return this.request<ActivityItem[]>("/activity");
  }

  async getUploadPreference(): Promise<UploadPreference> {
    return this.request<UploadPreference>("/settings/preferences");
  }

  async setUploadPreference(preferredMode: "whole" | "chunked_parity" | "mirrored" | null): Promise<UploadPreference> {
    return this.request<UploadPreference>("/settings/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferred_mode: preferredMode }),
    });
  }

  async reprotectFile(fileId: string): Promise<any> {
    return this.request(`/files/${fileId}/reprotect`, {
      method: "POST",
    });
  }

  async reprotectAllFiles(): Promise<any> {
    return this.request("/files/reprotect-all", {
      method: "POST",
    });
  }
}

export const api = new ApiService();
