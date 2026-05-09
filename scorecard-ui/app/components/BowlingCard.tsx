import type { BowlerEntry } from "../lib/types";

interface Props {
  bowlers: BowlerEntry[];
  title: string;
  compact?: boolean;
  teamScore?: number;
}

export default function BowlingCard({ bowlers, title, teamScore }: Props) {
  if (!bowlers || !bowlers.length) {
    return (
      <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
        <div className="px-3 py-2 border-b border-[#30363D]">
          <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
            {title}
          </span>
        </div>
        <div className="px-3 py-4 text-xs text-[#484F58] italic text-center">
          Awaiting bowling data…
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
      <div className="px-3 py-2 border-b border-[#30363D]">
        <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
          {title}
        </span>
      </div>

      <div className="grid grid-cols-[1fr_40px_30px_40px_30px_50px] px-3 py-1.5 text-xs text-[#8B949E] border-b border-[#30363D]/50">
        <span>Bowler</span>
        <span className="text-right">O</span>
        <span className="text-right">M</span>
        <span className="text-right">R</span>
        <span className="text-right">W</span>
        <span className="text-right">Econ</span>
      </div>

      {bowlers.map((b) => {
        const overs = parseFloat(b.overs || "0");
        const displayRuns = Math.min(
          b.runs || 0,
          teamScore != null ? teamScore : 999
        );
        const economy =
          overs > 0 && b.runs != null
            ? Math.round((displayRuns / overs) * 10) / 10
            : null;
        const hasNotBowled = b.overs == null;

        // Economy color: gray if < 1 over (too early to judge)
        const econColor =
          economy == null || overs < 1.0
            ? "text-[#8B949E]"
            : economy < 6
              ? "text-[#3FB950]"
              : economy > 10
                ? "text-[#F85149]"
                : "text-[#8B949E]";

        return (
          <div
            key={b.name}
            className={`grid grid-cols-[1fr_40px_30px_40px_30px_50px] px-3 py-2 border-b border-[#30363D]/30 last:border-0 ${
              b.is_current
                ? "bg-[#161B22]"
                : hasNotBowled
                  ? "opacity-40"
                  : "opacity-70"
            }`}
          >
            <div>
              <span
                className={`text-sm ${b.is_current ? "text-white" : "text-[#8B949E]"}`}
              >
                {b.is_current && (
                  <span className="text-[#58A6FF] mr-1">●</span>
                )}
                {b.name.split(" ").pop()}
              </span>
              {b.bowling_style &&
                b.bowling_style !== "unknown" &&
                b.bowling_style !== "None" && (
                  <div
                    className="text-[9px] font-mono text-[#8B949E] tracking-tight mt-0.5 truncate"
                    title={`Bowling style: ${b.bowling_style}`}
                  >
                    {b.bowling_style}
                  </div>
                )}
            </div>
            <span className="text-sm text-right font-mono text-[#E6EDF3]">
              {b.overs ?? "-"}
            </span>
            <span className="text-sm text-right font-mono text-[#8B949E]">
              {b.maidens || "-"}
            </span>
            <span className="text-sm text-right font-mono text-[#E6EDF3]">
              {b.overs != null ? displayRuns : "-"}
            </span>
            <span
              className={`text-sm text-right font-mono font-bold ${
                (b.wickets || 0) >= 3
                  ? "text-[#D29922]"
                  : (b.wickets || 0) > 0
                    ? "text-[#3FB950]"
                    : "text-[#E6EDF3]"
              }`}
            >
              {b.wickets ?? "-"}
            </span>
            <span className={`text-sm text-right font-mono ${econColor}`}>
              {economy != null && overs >= 1.0 ? economy.toFixed(1) : "-"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
