export interface DriveUsage {
  total: number;
  used: number;
  free: number;
  source: string;
  measured_used?: number;
  available?: boolean;
}

export interface Drive {
  id: string;
  display_name: string;
  path: string;
  provider_type?: "local" | "gdrive";
  status: "online" | "simulated_offline" | "unavailable";
  simulated_offline: boolean;
  available: boolean;
  usage: DriveUsage;
  chunk_count: number;
  chunks_total_bytes: number;
  shared_device?: boolean;
  shared_device_count?: number;
  shared_volume_name?: string;
  device_id?: string;
  volume_name?: string;
  created_at: string;
}

export interface Chunk {
  id: string;
  stripe_index: number;
  position: number;
  is_parity: boolean;
  drive_id: string;
  drive_name: string;
  chunk_id: string;
  sha256: string;
  size: number;
  drive_offline: boolean;
}

export interface StoredFile {
  id: string;
  name: string;
  folder: string;
  size: number;
  sha256: string;
  status: "uploading" | "complete" | "failed";
  health?: "Healthy" | "Rebuilt from parity" | "Unavailable";
  storage_mode?: "whole" | "chunked_parity";
  total_chunks?: number;
  chunks?: Chunk[];
  created_at: string;
  updated_at: string;
}

export interface UploadPreference {
  user_id: string;
  preferred_mode: "whole" | "chunked_parity" | null;
  updated_at?: string;
  threshold_bytes: number;
}

export interface PoolOverview {
  pooled_capacity: number;
  pooled_used: number;
  pooled_free: number;
  vault_chunks_bytes?: number;
  physical_disk_used?: number;
  physical_disk_capacity?: number;
  physical_disk_free?: number;
  capacity_source: string;
  drives_count: number;
  drives_online: number;
  drives_ratio: string;
  files_count: number;
  files_total_bytes: number;
  vault_unlocked: boolean;
}

export interface ActivityItem {
  id: number;
  operation: string;
  details: string;
  status: string;
  created_at: string;
}

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}
