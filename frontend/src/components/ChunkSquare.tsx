import React from "react";
import { Chunk, Drive } from "../types";
import { getDriveColor } from "../utils/format";

interface ChunkSquareProps {
  chunk: Chunk;
  drives: Drive[];
}

export const ChunkSquare: React.FC<ChunkSquareProps> = ({ chunk, drives }) => {
  // Find drive index for stable color mapping
  const driveIdx = drives.findIndex((d) => d.id === chunk.drive_id);
  const color = driveIdx >= 0 ? getDriveColor(driveIdx) : getDriveColor(chunk.drive_id);

  const isOffline = chunk.drive_offline;
  const isParity = chunk.is_parity;

  const tooltip = `Stripe ${chunk.stripe_index}, Slot ${chunk.position} (${
    isParity ? "Parity P" : "Data"
  }) • Drive: ${chunk.drive_name || chunk.drive_id.slice(0, 8)} ${
    isOffline ? "[OFFLINE]" : "[ONLINE]"
  } • Hash: ${chunk.sha256.slice(0, 10)}...`;

  return (
    <div
      title={tooltip}
      aria-label={tooltip}
      className="chunk-interactive"
      style={{
        width: "22px",
        height: "22px",
        borderRadius: "4px",
        backgroundColor: isOffline ? "var(--border-strong)" : color,
        border: `1px solid ${isOffline ? "var(--border-subtle)" : "rgba(0, 0, 0, 0.2)"}`,
        color: isOffline ? "var(--text-muted)" : "#ffffff",
        fontSize: "11px",
        fontWeight: "800",
        fontFamily: "var(--font-mono)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "help",
        opacity: isOffline ? 0.35 : 1,
        boxShadow: isOffline ? "none" : "var(--shadow-sm)",
        userSelect: "none",
      }}
    >
      {isParity ? "P" : ""}
    </div>
  );
};
