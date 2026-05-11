"use client";
import { useEffect, useState, useCallback, useMemo } from "react";

type FileEntry = {
  label: string;
  track: number;
  tail: string;
  size_bytes: number;
  mtime_ms: number;
};

type ApiResp = {
  log_dir: string;
  lines: number;
  files: Record<string, FileEntry>;
};

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function timeAgo(ms: number): string {
  if (!ms) return "—";
  const diff = Date.now() - ms;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export default function LogsPage() {
  const [data, setData] = useState<ApiResp | null>(null);
  const [lines, setLines] = useState(300);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filter, setFilter] = useState("");
  const [activeTrack, setActiveTrack] = useState<"all" | "1" | "2">("all");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/logs?lines=${lines}`, { cache: "no-store" });
      const j: ApiResp = await r.json();
      setData(j);
    } catch (e) {
      console.error(e);
    }
  }, [lines]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const filtered = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.files)
      .filter(([, f]) => activeTrack === "all" || String(f.track) === activeTrack)
      .sort((a, b) => a[1].track - b[1].track || a[0].localeCompare(b[0]));
  }, [data, activeTrack]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // fallback no-op
    }
  };

  const applyFilter = (s: string) => {
    if (!filter.trim()) return s;
    const needle = filter.toLowerCase();
    return s
      .split("\n")
      .filter((line) => line.toLowerCase().includes(needle))
      .join("\n");
  };

  return (
    <main className="min-h-screen bg-black text-white p-4 md:p-6">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl md:text-2xl font-bold">Match Logs</h1>
          <p className="text-xs text-gray-400">
            {data ? `tail ${data.lines} lines from ${data.log_dir}` : "loading..."}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs flex-wrap">
          <select
            value={activeTrack}
            onChange={(e) => setActiveTrack(e.target.value as "all" | "1" | "2")}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
          >
            <option value="all">All tracks</option>
            <option value="1">Track 1 (state)</option>
            <option value="2">Track 2 (clips)</option>
          </select>
          <select
            value={lines}
            onChange={(e) => setLines(parseInt(e.target.value, 10))}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1"
          >
            <option value={100}>100 lines</option>
            <option value={300}>300 lines</option>
            <option value={1000}>1000 lines</option>
            <option value={3000}>3000 lines</option>
          </select>
          <input
            type="text"
            placeholder="filter (case-insensitive)"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 w-44"
          />
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-blue-500"
            />
            Auto-refresh 10s
          </label>
          <button
            onClick={load}
            className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700"
          >
            Refresh
          </button>
          <a
            href="/server-logs/"
            target="_blank"
            rel="noreferrer"
            className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700"
          >
            Browse raw
          </a>
          <a
            href="/"
            className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700"
          >
            ← Match
          </a>
        </div>
      </header>

      <div className="space-y-4">
        {filtered.map(([name, f]) => {
          const body = applyFilter(f.tail);
          const lineCount = body ? body.split("\n").length : 0;
          return (
            <section
              key={name}
              className="bg-gray-900 rounded-lg border border-gray-800"
            >
              <div className="flex items-baseline justify-between px-3 py-2 border-b border-gray-800 text-xs">
                <div>
                  <span className="font-mono text-sm">{name}</span>
                  <span className="ml-2 text-gray-400">{f.label}</span>
                </div>
                <div className="flex items-center gap-3 text-gray-500">
                  <span>{bytes(f.size_bytes)}</span>
                  <span>{timeAgo(f.mtime_ms)}</span>
                  <span>{lineCount} line{lineCount === 1 ? "" : "s"}</span>
                  <button
                    onClick={() => copy(body)}
                    className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700 text-gray-300"
                  >
                    Copy
                  </button>
                  <a
                    href={`/api/logs?file=${encodeURIComponent(name)}&lines=${lines}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 rounded border border-gray-700 text-gray-300"
                  >
                    Raw
                  </a>
                </div>
              </div>
              <pre className="overflow-x-auto text-[11px] leading-snug font-mono p-3 max-h-96">
                {body || "(empty)"}
              </pre>
            </section>
          );
        })}
      </div>
    </main>
  );
}
