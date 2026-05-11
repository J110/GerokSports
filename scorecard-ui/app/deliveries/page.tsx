"use client";
import { useEffect, useState, useCallback } from "react";

type Delivery = {
  anchor_int: number;
  clip_url: string;
  meta_url: string;
  size_bytes: number;
  mtime_ms: number;
  anchor_t?: number;
  clip_start?: number;
  clip_end?: number;
  clip_duration?: number;
  cluster_start_t?: number;
  cluster_end_t?: number;
  note?: string;
};

type ApiResp = {
  count: number;
  deliveries: Delivery[];
  error?: string;
};

function fmt(n: number | undefined, digits = 2): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function timeAgo(ms: number): string {
  const diff = Date.now() - ms;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export default function DeliveriesPage() {
  const [data, setData] = useState<ApiResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/deliveries", { cache: "no-store" });
      const j: ApiResp = await r.json();
      setData(j);
      if (j.error) setErr(j.error);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const deliveries = data?.deliveries ?? [];

  return (
    <main className="min-h-screen bg-black text-white p-4 md:p-8">
      <header className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">Deliveries</h1>
          <p className="text-sm text-gray-400">
            Track 2 clip verification —{" "}
            {data ? `${data.count} clips` : "loading..."}
            {loading && " · refreshing..."}
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-blue-500"
            />
            Auto-refresh (30s)
          </label>
          <button
            onClick={load}
            className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-sm border border-gray-700"
          >
            Refresh
          </button>
          <a
            href="/"
            className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-sm border border-gray-700"
          >
            ← Match view
          </a>
        </div>
      </header>

      {err && (
        <div className="mb-4 p-3 bg-red-900/40 border border-red-800 rounded text-sm">
          Error: {err}
        </div>
      )}

      {deliveries.length === 0 && !loading && !err && (
        <div className="p-6 text-center text-gray-500 border border-gray-800 rounded">
          No clips yet. They will appear once the pipeline detects deliveries.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {deliveries
          .slice()
          .reverse()
          .map((d) => (
            <div
              key={d.anchor_int}
              className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden"
            >
              <video
                src={d.clip_url}
                controls
                preload="metadata"
                className="w-full aspect-video bg-black"
              />
              <div className="p-3 text-sm space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="font-mono text-base">
                    anchor @ {fmt(d.anchor_t, 1)}s
                  </span>
                  <span className="text-xs text-gray-500">
                    {timeAgo(d.mtime_ms)}
                  </span>
                </div>
                <div className="text-gray-400 font-mono text-xs">
                  clip [{fmt(d.clip_start, 1)} → {fmt(d.clip_end, 1)}] ·{" "}
                  {fmt(d.clip_duration, 1)}s · {bytes(d.size_bytes)}
                </div>
                <div className="text-gray-500 font-mono text-xs">
                  cluster [{fmt(d.cluster_start_t, 1)} →{" "}
                  {fmt(d.cluster_end_t, 1)}]
                </div>
                {d.note && (
                  <div className="text-amber-400/80 text-xs">{d.note}</div>
                )}
                <div className="pt-1 flex gap-2 text-xs">
                  <a
                    href={d.clip_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:underline"
                  >
                    open clip
                  </a>
                  <a
                    href={d.meta_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:underline"
                  >
                    metadata
                  </a>
                </div>
              </div>
            </div>
          ))}
      </div>
    </main>
  );
}
