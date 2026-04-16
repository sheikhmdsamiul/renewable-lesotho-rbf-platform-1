import React, { useEffect, useMemo, useRef, useState } from "react";

import { fetchMapInstallations } from "../api";
import { MapInstallationsResponse } from "../types";

declare global {
  interface Window {
    L?: any;
  }
}

type DraftFilters = {
  technology: string;
  district: string;
  household_type: string;
  date_from: string;
  date_to: string;
};

const LEAFLET_CSS_ID = "leaflet-cdn-css";
const LEAFLET_JS_ID = "leaflet-cdn-js";

function ensureLeafletAssets(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window !== "undefined" && window.L) {
      resolve();
      return;
    }

    if (!document.getElementById(LEAFLET_CSS_ID)) {
      const link = document.createElement("link");
      link.id = LEAFLET_CSS_ID;
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    const existingScript = document.getElementById(LEAFLET_JS_ID) as HTMLScriptElement | null;
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Failed to load Leaflet.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = LEAFLET_JS_ID;
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Leaflet."));
    document.head.appendChild(script);
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTitleCase(value?: string): string {
  if (!value) return "N/A";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatInstalledDate(value?: string): string {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function formatUptime(value?: number): string {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${Number(value).toFixed(1)}%`;
}

function statusLabelFromGisStatus(value?: string): string {
  if (value === "green") return "Verified";
  if (value === "red") return "Flagged";
  return "Pending";
}

export function GisInstallationsMap({
  projectId,
  showFilters = true,
  height = "500px",
  emptyStateMessage,
}: {
  projectId?: string;
  showFilters?: boolean;
  height?: string;
  emptyStateMessage?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const boundaryLayerRef = useRef<any>(null);
  const layerControlRef = useRef<any>(null);
  const markerLayersRef = useRef<Record<string, { remove: () => void }> | null>(null);

  const [leafletReady, setLeafletReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapData, setMapData] = useState<MapInstallationsResponse>({
    installations: [],
    summary: { total: 0, verified: 0, pending: 0, flagged: 0 },
    truncated: false,
  });
  const [draftFilters, setDraftFilters] = useState<DraftFilters>({
    technology: "",
    district: "",
    household_type: "",
    date_from: "",
    date_to: "",
  });
  const [appliedFilters, setAppliedFilters] = useState<DraftFilters>({
    technology: "",
    district: "",
    household_type: "",
    date_from: "",
    date_to: "",
  });

  useEffect(() => {
    let active = true;
    ensureLeafletAssets()
      .then(() => {
        if (active) setLeafletReady(true);
      })
      .catch((err) => {
        if (active) setError(String(err?.message || "Could not load map assets."));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!leafletReady || !containerRef.current || mapRef.current) return;
    const L = window.L;
    const map = L.map(containerRef.current, {
      zoomControl: true,
    }).setView([-29.6, 28.2], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 50);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [leafletReady]);

  useEffect(() => {
    if (!leafletReady || !mapRef.current || boundaryLayerRef.current) return;
    let cancelled = false;
    fetch("/public/geojson/lesotho.geojson")
      .then((response) => {
        if (!response.ok) throw new Error("Boundary file not found.");
        return response.json();
      })
      .then((feature) => {
        if (cancelled || !mapRef.current) return;
        boundaryLayerRef.current = window.L.geoJSON(feature, {
          style: {
            fillColor: "transparent",
            color: "#1D9E75",
            weight: 2,
            opacity: 0.8,
          },
        }).addTo(mapRef.current);
      })
      .catch(() => {
        // Boundary overlay is optional at runtime; map still works without it.
      });
    return () => {
      cancelled = true;
    };
  }, [leafletReady]);

  const loadInstallations = async (filters: DraftFilters) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchMapInstallations({
        project_id: projectId,
        technology: filters.technology || undefined,
        district: filters.district || undefined,
        household_type: filters.household_type || undefined,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
      });
      setMapData(response);
    } catch (err: any) {
      setError(String(err?.message || "Could not load map data."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadInstallations(appliedFilters);
  }, [projectId, appliedFilters]);

  useEffect(() => {
    if (!leafletReady || !mapRef.current) return;
    const L = window.L;

    if (markerLayersRef.current) {
      (Object.values(markerLayersRef.current) as Array<{ remove: () => void }>).forEach((layer) => layer.remove());
      markerLayersRef.current = null;
    }
    if (layerControlRef.current) {
      layerControlRef.current.remove();
      layerControlRef.current = null;
    }

    const verifiedLayer = L.layerGroup().addTo(mapRef.current);
    const pendingLayer = L.layerGroup().addTo(mapRef.current);
    const flaggedLayer = L.layerGroup().addTo(mapRef.current);
    markerLayersRef.current = {
      verified: verifiedLayer,
      pending: pendingLayer,
      flagged: flaggedLayer,
    };

    const bounds: [number, number][] = [];
    mapData.installations.forEach((installation) => {
      const fillColor =
        installation.gisStatus === "green" ? "#1D9E75" :
        installation.gisStatus === "red" ? "#A32D2D" :
        "#BA7517";
      const targetLayer =
        installation.gisStatus === "green" ? verifiedLayer :
        installation.gisStatus === "red" ? flaggedLayer :
        pendingLayer;
      const marker = L.circleMarker([installation.latitude, installation.longitude], {
        radius: 8,
        fillOpacity: 0.85,
        weight: 1.5,
        color: "white",
        fillColor,
      });
      marker.bindPopup(`
        <div style="min-width:220px;font-family:inherit;">
          <div style="font-weight:700;margin-bottom:8px;">${escapeHtml(installation.serialNumber || `INS-${String(installation.id).padStart(3, "0")}`)}</div>
          <div style="font-size:12px;line-height:1.5;">
            <div><strong>Beneficiary:</strong> ${escapeHtml(installation.beneficiaryName || "N/A")}</div>
            <div><strong>Household:</strong> ${escapeHtml(formatTitleCase(installation.householdType))}</div>
            <div><strong>Technology:</strong> ${escapeHtml(formatTitleCase(installation.technologyType))}</div>
            <div><strong>Status:</strong> ${escapeHtml(statusLabelFromGisStatus(installation.gisStatus))}</div>
            <div><strong>Verification:</strong> ${escapeHtml(formatTitleCase(installation.verificationStatus))}</div>
            <div><strong>Vendor:</strong> ${escapeHtml(installation.vendorName || "N/A")}</div>
            <div><strong>District:</strong> ${escapeHtml(installation.district || "N/A")}</div>
            <div><strong>Installed:</strong> ${escapeHtml(formatInstalledDate(installation.installationDate))}</div>
            <div><strong>Uptime:</strong> ${escapeHtml(formatUptime(installation.uptimePct))}</div>
          </div>
          <div style="margin-top:10px;">
            <a href="/api/projects/installations/${encodeURIComponent(installation.id)}/" target="_blank" rel="noreferrer">View Details</a>
          </div>
        </div>
      `);
      marker.addTo(targetLayer);
      bounds.push([installation.latitude, installation.longitude]);
    });

    layerControlRef.current = L.control.layers(
      {},
      {
        [`✅ Verified (${mapData.summary.verified})`]: verifiedLayer,
        [`✅ Pending (${mapData.summary.pending})`]: pendingLayer,
        [`✅ Flagged (${mapData.summary.flagged})`]: flaggedLayer,
      },
      { collapsed: false, position: "topright" },
    ).addTo(mapRef.current);

    if (bounds.length > 0) {
      mapRef.current.fitBounds(bounds, { padding: [24, 24] });
    } else {
      mapRef.current.setView([-29.6, 28.2], 8);
    }
  }, [leafletReady, mapData]);

  const technologyOptions = useMemo(
    () => Array.from(new Set(mapData.installations.map((item) => item.technologyType).filter(Boolean))).sort(),
    [mapData.installations],
  );
  const districtOptions = useMemo(
    () => Array.from(new Set(mapData.installations.map((item) => item.district).filter(Boolean))).sort(),
    [mapData.installations],
  );
  const householdOptions = useMemo(
    () => Array.from(new Set(mapData.installations.map((item) => item.householdType || "").filter(Boolean))).sort(),
    [mapData.installations],
  );

  return (
    <div className="space-y-4">
      {showFilters && (
        <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <select
              className="input-field"
              value={draftFilters.technology}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, technology: e.target.value }))}
            >
              <option value="">All Technologies</option>
              {technologyOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <select
              className="input-field"
              value={draftFilters.district}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, district: e.target.value }))}
            >
              <option value="">All Districts</option>
              {districtOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <select
              className="input-field"
              value={draftFilters.household_type}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, household_type: e.target.value }))}
            >
              <option value="">All Household Types</option>
              {householdOptions.map((option) => (
                <option key={option} value={option}>{formatTitleCase(option)}</option>
              ))}
            </select>
            <input
              type="date"
              className="input-field"
              value={draftFilters.date_from}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, date_from: e.target.value }))}
            />
            <input
              type="date"
              className="input-field"
              value={draftFilters.date_to}
              onChange={(e) => setDraftFilters((prev) => ({ ...prev, date_to: e.target.value }))}
            />
            <div className="flex gap-2">
              <button className="btn-primary flex-1" onClick={() => setAppliedFilters(draftFilters)}>Apply Filters</button>
              <button
                className="btn-secondary"
                onClick={() => {
                  const reset = { technology: "", district: "", household_type: "", date_from: "", date_to: "" };
                  setDraftFilters(reset);
                  setAppliedFilters(reset);
                }}
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div>
          <p className="font-semibold text-slate-900">Showing {mapData.summary.total} installations</p>
          <p className="text-slate-500">
            <span className="font-semibold text-[#1D9E75]">🟢 {mapData.summary.verified} Verified</span>
            {"  "}
            <span className="font-semibold text-[#BA7517]">🟡 {mapData.summary.pending} Pending</span>
            {"  "}
            <span className="font-semibold text-[#A32D2D]">🔴 {mapData.summary.flagged} Flagged</span>
          </p>
        </div>
        {mapData.truncated && (
          <p className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
            Showing first 1000 records
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          Could not load map data.{" "}
          <button className="font-semibold underline" onClick={() => void loadInstallations(appliedFilters)}>
            Retry
          </button>
        </div>
      )}

      <div className="relative overflow-hidden rounded-[28px] border border-slate-200 bg-slate-100" style={{ height }}>
        <div ref={containerRef} className="h-full w-full" />

        {loading && (
          <div className="absolute inset-0 z-[500] flex items-center justify-center bg-white/70 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3 rounded-2xl bg-white px-6 py-5 shadow-xl">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600" />
              <p className="text-sm font-medium text-slate-700">Loading installations...</p>
            </div>
          </div>
        )}

        {!loading && !error && mapData.installations.length === 0 && (
          <div className="absolute inset-0 z-[400] flex items-center justify-center bg-white/55">
            <div className="rounded-2xl bg-white px-6 py-4 text-center shadow-lg">
              <p className="text-base font-semibold text-slate-900">No installations found</p>
              <p className="text-sm text-slate-500">
                {emptyStateMessage || (projectId
                  ? "No installations submitted yet for this project. Submit your first installation to see it on the map."
                  : "No installations found for the selected filters.")}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default GisInstallationsMap;
