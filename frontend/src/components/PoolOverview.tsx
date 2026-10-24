import React from "react";
import { PoolOverview as PoolOverviewType } from "../types";
import { formatBytes } from "../utils/format";

interface PoolOverviewProps {
  overview: PoolOverviewType | null;
  loading: boolean;
}

export const PoolOverview: React.FC<PoolOverviewProps> = ({ overview, loading }) => {
  if (loading && !overview) {
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "16px",
          padding: "24px 28px",
        }}
      >
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            style={{
              height: "105px",
              backgroundColor: "var(--bg-surface)",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border-subtle)",
              opacity: 0.6,
            }}
          />
        ))}
      </div>
    );
  }

  const cap = overview?.pooled_capacity || 0;
  const used = overview?.pooled_used || 0;
  const free = overview?.pooled_free || 0;
  const usedPct = cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  const drivesOnline = overview?.drives_online || 0;
  const drivesTotal = overview?.drives_count || 0;
  const isHealthy = drivesTotal >= 3 && drivesOnline === drivesTotal;
  const isDegraded = drivesTotal >= 3 && drivesOnline === drivesTotal - 1;

  return (
    <section
      aria-label="Storage Pool Overview"
      className="animate-slide-up"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
        gap: "16px",
        padding: "20px 28px 12px",
      }}
    >
      {/* 1. Pooled Capacity Card */}
      <div
        className="card-interactive"
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Total Capacity
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-full)",
              color: "var(--text-secondary)",
            }}
          >
            Unified Pool
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(cap)}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          <span style={{ color: "var(--text-secondary)", fontWeight: "500" }}>{formatBytes(free)}</span> free across {drivesTotal} drives (De-duplicated)
        </div>
      </div>

      {/* 2. Pool Space Used Card */}
      <div
        className="card-interactive"
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Vault Storage Used
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              fontFamily: "var(--font-mono)",
              padding: "2px 8px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-full)",
              color: "var(--accent-cyan-solid)",
            }}
          >
            {usedPct}%
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(overview?.vault_chunks_bytes ?? used)}
        </div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          {overview?.physical_disk_used ? (
            <span>Host disk used: {formatBytes(overview.physical_disk_used)}</span>
          ) : (
            <span>Actual encrypted vault chunks stored</span>
          )}
        </div>
        {/* Crisp solid progress bar */}
        <div
          style={{
            height: "5px",
            backgroundColor: "var(--bg-surface-elevated)",
            borderRadius: "var(--radius-full)",
            overflow: "hidden",
            marginTop: "6px",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${usedPct}%`,
              backgroundColor: "var(--accent-cyan-solid)",
              borderRadius: "var(--radius-full)",
              transition: "width 400ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
        </div>
      </div>

      {/* 3. Drives Online Card */}
      <div
        className="card-interactive"
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Drives Status
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: isHealthy
                ? "var(--status-online-bg)"
                : isDegraded
                ? "var(--status-warning-bg)"
                : "var(--status-offline-bg)",
              border: `1px solid ${isHealthy ? "var(--status-online)" : isDegraded ? "var(--status-warning)" : "var(--status-offline)"}`,
              borderRadius: "var(--radius-full)",
              color: isHealthy ? "var(--status-online-text)" : isDegraded ? "var(--status-warning-text)" : "var(--status-offline-text)",
            }}
          >
            {isHealthy ? "Healthy" : isDegraded ? "Degraded" : "At Risk"}
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {overview?.drives_ratio || "0 of 0"}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {drivesOnline >= 3 ? "XOR parity active across online drives" : "Requires 3+ drives for XOR parity"}
        </div>
      </div>

      {/* 4. Files Stored Card */}
      <div
        className="card-interactive"
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Objects
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-full)",
              color: "var(--text-secondary)",
            }}
          >
            AES-256-GCM
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {overview?.files_count || 0}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          Payload: <span style={{ color: "var(--text-secondary)", fontWeight: "500" }}>{formatBytes(overview?.files_total_bytes || 0)}</span>
        </div>
      </div>
    </section>
  );
};
