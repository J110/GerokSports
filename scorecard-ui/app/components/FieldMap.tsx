import type { FieldData, FieldPosition } from "../lib/types";

interface Props {
  field: FieldData;
}

const TYPE_COLORS: Record<string, string> = {
  wk: "#D29922",
  bowler: "#8B949E",
  bat: "#F85149",
  close: "#58A6FF",
  in: "#58A6FF",
  out: "#E6EDF3",
};

const TYPE_RADIUS: Record<string, number> = {
  bat: 2.2,
  wk: 1.8,
  bowler: 1.6,
  close: 1.4,
  in: 1.4,
  out: 1.4,
};

function formatLabel(name: string): string {
  return name.replace(/_/g, " ");
}

export default function FieldMap({ field }: Props) {
  if (!field || !field.positions?.length) return null;

  const formation = field.formation?.replace(/_/g, " ") || "";

  return (
    <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
      <div className="px-3 py-2 border-b border-[#30363D] flex justify-between items-center">
        <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
          Field
        </span>
        <div className="flex items-center gap-2 text-[10px] text-[#8B949E]">
          {formation && (
            <span className="px-1.5 py-0.5 bg-[#0D1117] rounded">
              {formation}
            </span>
          )}
          {field.phase && (
            <span className="px-1.5 py-0.5 bg-[#0D1117] rounded capitalize">
              {field.phase}
            </span>
          )}
          <span>
            {field.inside_count ?? 0}in / {field.outside_count ?? 0}out
          </span>
        </div>
      </div>

      <div className="relative w-full max-w-[320px] mx-auto p-2">
        <svg viewBox="0 0 100 100" className="w-full" xmlns="http://www.w3.org/2000/svg">
          {/* Field background */}
          <circle cx="50" cy="50" r="48" fill="#1A3A1A" stroke="#2D5A2D" strokeWidth="0.5" />

          {/* 30-yard circle */}
          <circle
            cx="50" cy="50" r="22"
            fill="none" stroke="#3D7A3D" strokeWidth="0.4"
            strokeDasharray="2 1.5" opacity="0.6"
          />

          {/* Pitch */}
          <rect
            x="48.5" y="40" width="3" height="20" rx="0.5"
            fill="#C4A265" opacity="0.3"
          />
          {/* Crease lines */}
          <line x1="47" y1="43" x2="53" y2="43" stroke="#C4A265" strokeWidth="0.3" opacity="0.4" />
          <line x1="47" y1="57" x2="53" y2="57" stroke="#C4A265" strokeWidth="0.3" opacity="0.4" />

          {/* Player positions */}
          {field.positions.map((p: FieldPosition, i: number) => {
            const cx = p.x * 100;
            const cy = p.y * 100;
            const color = TYPE_COLORS[p.type] || "#8B949E";
            const r = TYPE_RADIUS[p.type] || 1.4;
            const opacity = Math.max(0.4, p.confidence);

            return (
              <g key={`${p.name}-${i}`} opacity={opacity}>
                <circle
                  cx={cx} cy={cy} r={r}
                  fill={color}
                  stroke={color} strokeWidth="0.3" strokeOpacity="0.4"
                />
                <title>{formatLabel(p.name)}</title>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="px-3 pb-2 flex justify-center gap-4 text-[9px] text-[#8B949E]">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#58A6FF] inline-block" /> in
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#E6EDF3] inline-block" /> out
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#D29922] inline-block" /> wk
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#8B949E] inline-block" /> bowler
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#F85149] inline-block" /> bat
        </span>
      </div>

      {field.confidence === "low" && (
        <div className="px-3 py-1.5 text-[10px] text-[#D29922] border-t border-[#30363D]/50">
          Field positions approximate
        </div>
      )}
    </div>
  );
}
