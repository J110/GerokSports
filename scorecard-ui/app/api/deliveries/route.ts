import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const CLIPS_DIR =
  process.env.LIVE_CLIPS_DIR ||
  "/mnt/data/sportscomm/files/logs/live_clips";

type DeliveryEntry = {
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

export async function GET() {
  try {
    const entries = await fs.readdir(CLIPS_DIR);
    const clips = entries
      .filter((f) => /^clip_anchor\d+\.mp4$/.test(f))
      .sort();

    const out: DeliveryEntry[] = [];
    for (const clip of clips) {
      const m = clip.match(/^clip_anchor(\d+)\.mp4$/);
      if (!m) continue;
      const anchor_int = parseInt(m[1], 10);
      const clipPath = path.join(CLIPS_DIR, clip);
      const metaName = `clip_anchor${m[1]}.json`;
      const metaPath = path.join(CLIPS_DIR, metaName);

      let stat: import("fs").Stats;
      try {
        stat = await fs.stat(clipPath);
      } catch {
        continue;
      }

      let meta: Partial<DeliveryEntry> = {};
      try {
        const raw = await fs.readFile(metaPath, "utf8");
        const parsed = JSON.parse(raw);
        meta = {
          anchor_t: parsed.anchor_t,
          clip_start: parsed.clip_start,
          clip_end: parsed.clip_end,
          clip_duration: parsed.clip_duration,
          cluster_start_t: parsed.cluster_start_t,
          cluster_end_t: parsed.cluster_end_t,
          note: parsed.note,
        };
      } catch {
        // metadata sidecar may not exist yet
      }

      out.push({
        anchor_int,
        clip_url: `/clips/${clip}`,
        meta_url: `/clips/${metaName}`,
        size_bytes: stat.size,
        mtime_ms: stat.mtimeMs,
        ...meta,
      });
    }

    out.sort((a, b) => a.anchor_int - b.anchor_int);
    return NextResponse.json({ count: out.length, deliveries: out });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: msg, clips_dir: CLIPS_DIR, count: 0, deliveries: [] },
      { status: 500 },
    );
  }
}
