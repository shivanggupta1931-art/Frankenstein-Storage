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

  const rawCap = overview?.raw_capacity || overview?.pooled_capacity || 0;
  const usableCap = overview?.usable_capacity || 0;
  const freeUsable = overview?.free_usable_space ?? overview?.pooled_free ?? 0;
  const vaultUsed = overview?.vault_chunks_bytes ?? overview?.pooled_used ?? 0;
  const usedPct = usableCap > 0 ? Math.min(100, Math.round((vaultUsed / usableCap) * 100)) : 0;
  const drivesOnline = overview?.drives_online || 0;
  const drivesTotal = overview?.drives_count || 0;
  const drivesEligible = overview?.drives_eligible ?? drivesOnline;
  
  const redundancyMode = overview?.redundancy_mode || (drivesOnline >= 3 ? "parity" : drivesOnline === 2 ? "mirrored" : "unprotected");
  const redundancyLabel = overview?.redundancy_label || (redundancyMode === "parity" ? "Parity-protected" : redundancyMode === "mirrored" ? "Mirrored" : "Unprotected");
  
  const isHealthy = drivesTotal >= 2 && drivesOnline === drivesTotal && drivesEligible >= 2;
  const isDegraded = drivesTotal >= 2 && drivesOnline < drivesTotal && drivesOnline >= (redundancyMode === "parity" ? 2 : 1);

  return (
    <section
      aria-label="Storage Pool Overview"
      className="animate-slide-up"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
        gap: "14px",
        padding: "20px 28px 12px",
      }}
    >
      {/* 1. Usable Capacity Card (Honest Figure 1) */}
      <div
        className="card-interactive"
        title={overview?.usable_capacity_description || "Actual usable capacity available for encrypted files after redundancy overhead and reserves."}
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          boxShadow: "var(--shadow-sm)",
          position: "relative",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Usable Capacity
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: "rgba(16, 185, 129, 0.12)",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              borderRadius: "var(--radius-full)",
              color: "#10b981",
            }}
          >
            Honest Pool
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(usableCap)}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {redundancyLabel} (after reserves & overhead)
        </div>
      </div>

      {/* 2. Free Usable Space Card (Honest Figure 2) */}
      <div
        className="card-interactive"
        title={overview?.free_usable_space_description || "Real free space available for file uploads after 2 GiB/5% reserve and redundancy overhead."}
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
          <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Free Usable Space
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
            Available
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(freeUsable)}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          Raw physical free: <span style={{ color: "var(--text-secondary)", fontWeight: "500" }}>{formatBytes(overview?.raw_free ?? overview?.pooled_free ?? 0)}</span>
        </div>
      </div>

      {/* 3. Raw Capacity Card (Honest Figure 3) */}
      <div
        className="card-interactive"
        title={overview?.raw_capacity_description || "Total physical storage across all registered drives (de-duplicated across shared Mac volumes)."}
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
          <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Raw Physical Disk
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-full)",
              color: "var(--text-muted)",
            }}
          >
            De-duplicated
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(rawCap)}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {drivesTotal} drives registered ({drivesEligible} placement-eligible)
        </div>
      </div>

      {/* 4. Drives & Protection Status Card */}
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
          <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Pool Protection
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
            {isHealthy ? "Protected" : isDegraded ? "Degraded" : "At Risk"}
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {redundancyLabel}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {drivesOnline} of {drivesTotal} online ({drivesEligible} eligible above reserve)
        </div>
      </div>

      {/* 5. Objects & Vault Chunks Card */}
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
          <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Vault Storage
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: "600",
              padding: "2px 8px",
              backgroundColor: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius-full)",
              color: "var(--accent-cyan-solid)",
            }}
          >
            {usedPct}% used
          </span>
        </div>
        <div style={{ fontSize: "24px", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {formatBytes(vaultUsed)}
        </div>
        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {overview?.files_count || 0} encrypted file(s) ({formatBytes(overview?.files_total_bytes || 0)} payload)
        </div>
      </div>
    </section>
  );
};
