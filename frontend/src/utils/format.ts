export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  if (i < 0) return `${bytes} B`;
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i] || "B"}`;
}

export function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export function truncateHash(hash: string, chars = 8): string {
  if (!hash || hash.length <= chars * 2) return hash;
  return `${hash.slice(0, chars)}...${hash.slice(-chars)}`;
}

// Deterministic drive color helper
const DRIVE_PALETTE = [
  "#06b6d4", // cyan
  "#f59e0b", // amber
  "#a855f7", // purple
  "#10b981", // emerald
  "#f43f5e", // rose
  "#3b82f6", // blue
  "#84cc16", // lime
];

export function getDriveColor(driveIndexOrId: string | number): string {
  if (typeof driveIndexOrId === "number") {
    return DRIVE_PALETTE[driveIndexOrId % DRIVE_PALETTE.length];
  }
  let hash = 0;
  for (let i = 0; i < driveIndexOrId.length; i++) {
    hash = (hash << 5) - hash + driveIndexOrId.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % DRIVE_PALETTE.length;
  return DRIVE_PALETTE[idx];
}
