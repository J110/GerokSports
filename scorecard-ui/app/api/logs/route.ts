import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const LOG_DIR = process.env.SERVER_LOG_DIR || "/var/log/sportscomm";

const FILES: Record<string, { label: string; track: 1 | 2 }> = {
  "pipeline.log": { label: "Pipeline (Track 1)", track: 1 },
  "pipeline-err.log": { label: "Pipeline errors (Track 1)", track: 1 },
  "recorder.log": { label: "Recorder (Track 2)", track: 2 },
  "recorder-err.log": { label: "Recorder errors (Track 2)", track: 2 },
  "live-clips.log": { label: "Live clips (Track 2)", track: 2 },
  "live-clips-err.log": { label: "Live clips errors (Track 2)", track: 2 },
  "ui.log": { label: "UI", track: 1 },
  "ui-err.log": { label: "UI errors", track: 1 },
};

async function tailFile(absPath: string, lines: number): Promise<string> {
  try {
    const buf = await fs.readFile(absPath, "utf8");
    const arr = buf.split("\n");
    return arr.slice(-lines).join("\n");
  } catch (e) {
    return `[error reading ${absPath}: ${e instanceof Error ? e.message : String(e)}]`;
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const lines = Math.min(parseInt(url.searchParams.get("lines") || "200", 10), 5000);
  const file = url.searchParams.get("file");

  if (file) {
    if (!Object.prototype.hasOwnProperty.call(FILES, file)) {
      return NextResponse.json({ error: "unknown file" }, { status: 400 });
    }
    const abs = path.join(LOG_DIR, file);
    const content = await tailFile(abs, lines);
    return new NextResponse(content, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const out: Record<string, { label: string; track: number; tail: string; size_bytes: number; mtime_ms: number }> = {};
  for (const [name, meta] of Object.entries(FILES)) {
    const abs = path.join(LOG_DIR, name);
    let size_bytes = 0;
    let mtime_ms = 0;
    try {
      const st = await fs.stat(abs);
      size_bytes = st.size;
      mtime_ms = st.mtimeMs;
    } catch {
      // file may not exist yet
    }
    out[name] = {
      label: meta.label,
      track: meta.track,
      tail: await tailFile(abs, lines),
      size_bytes,
      mtime_ms,
    };
  }
  return NextResponse.json({ log_dir: LOG_DIR, lines, files: out });
}
