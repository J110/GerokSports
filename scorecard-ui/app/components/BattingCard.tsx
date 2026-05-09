import type { BatterEntry, Extras } from "../lib/types";

interface Props {
  batters: BatterEntry[];
  title: string;
  compact?: boolean;
  extras?: Extras;
  total?: {
    score: number | null;
    wickets: number | null;
    overs: string | null;
  };
  teamScore?: number;
}

export default function BattingCard({
  batters,
  title,
  extras,
  total,
  teamScore,
}: Props) {
  if (!batters || !batters.length) {
    return (
      <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
        <div className="px-3 py-2 border-b border-[#30363D]">
          <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
            {title}
          </span>
        </div>
        <div className="px-3 py-4 text-xs text-[#484F58] italic text-center">
          Awaiting batting data…
        </div>
      </div>
    );
  }

  const sorted = [...batters].sort(
    (a, b) => (a.position || 99) - (b.position || 99)
  );

  return (
    <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
      <div className="px-3 py-2 border-b border-[#30363D]">
        <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
          {title}
        </span>
      </div>

      <div className="grid grid-cols-[1fr_40px_40px_40px_40px_50px] px-3 py-1.5 text-xs text-[#8B949E] border-b border-[#30363D]/50">
        <span>Batter</span>
        <span className="text-right">R</span>
        <span className="text-right">B</span>
        <span className="text-right">4s</span>
        <span className="text-right">6s</span>
        <span className="text-right">SR</span>
      </div>

      {sorted.map((b) => {
        const sr = b.sr ?? 0;
        return (
          <div
            key={b.name}
            className={`grid grid-cols-[1fr_40px_40px_40px_40px_50px] px-3 py-2 border-b border-[#30363D]/30 last:border-0 ${
              b.status === "batting"
                ? "bg-[#161B22]"
                : b.status === "yet_to_bat"
                  ? "opacity-40"
                  : "opacity-70"
            }`}
          >
            <div>
              <span
                className={`text-sm ${b.status === "batting" ? "text-white" : "text-[#8B949E]"}`}
              >
                {b.is_striker && (
                  <span className="text-[#3FB950] mr-1">{"\u25CF"}</span>
                )}
                {b.name?.split(" ").pop() || b.name}
                {b.batting_style && b.batting_style !== "unknown" && (
                  <span
                    className="ml-1.5 text-[9px] font-mono uppercase tracking-wider text-[#8B949E] align-middle"
                    title={`Batting style: ${b.batting_style}`}
                  >
                    {b.batting_style}
                  </span>
                )}
              </span>
              {b.dismissal && (
                <div className="text-xs text-[#F85149] mt-0.5 truncate">
                  {typeof b.dismissal === "string"
                    ? b.dismissal
                    : typeof b.dismissal === "object" && b.dismissal !== null
                      ? (b.dismissal as Record<string, string>).how || "out"
                      : "out"}
                </div>
              )}
              {b.status === "out" && !b.dismissal && b.runs == null && (
                <div className="text-xs text-[#8B949E] mt-0.5">out (before join)</div>
              )}
              {b.status === "yet_to_bat" && (
                <div className="text-xs text-[#30363D] mt-0.5">yet to bat</div>
              )}
            </div>
            <span
              className={`text-sm text-right font-mono ${
                b.status === "batting"
                  ? "text-white font-bold"
                  : "text-[#E6EDF3]"
              }`}
            >
              {b.runs ?? "-"}
            </span>
            <span className="text-sm text-right font-mono text-[#8B949E]">
              {b.balls ?? "-"}
            </span>
            <span className={`text-sm text-right font-mono ${(b.fours ?? 0) > 0 ? "text-[#58A6FF]" : "text-[#8B949E]"}`}>
              {b.status === "yet_to_bat" ? "-" : (b.fours ?? 0)}
            </span>
            <span className={`text-sm text-right font-mono ${(b.sixes ?? 0) > 0 ? "text-[#D29922]" : "text-[#8B949E]"}`}>
              {b.status === "yet_to_bat" ? "-" : (b.sixes ?? 0)}
            </span>
            <span
              className={`text-sm text-right font-mono ${
                sr > 150
                  ? "text-[#3FB950]"
                  : sr > 0 && sr < 80
                    ? "text-[#F85149]"
                    : "text-[#8B949E]"
              }`}
            >
              {sr > 0 ? sr.toFixed(1) : "-"}
            </span>
          </div>
        );
      })}

      {extras && (extras.total ?? 0) > 0 && (
        <div className="px-3 py-1.5 text-xs text-[#8B949E] border-t border-[#30363D]/50">
          Extras: {extras.total}
          {" ("}
          {(extras.wides ?? 0) > 0 && `w${extras.wides} `}
          {(extras.no_balls ?? 0) > 0 && `nb${extras.no_balls} `}
          {(extras.byes ?? 0) > 0 && `b${extras.byes} `}
          {(extras.leg_byes ?? 0) > 0 && `lb${extras.leg_byes}`}
          {")"}
        </div>
      )}

      {total && total.score != null && (
        <div className="px-3 py-2 border-t border-[#30363D] bg-[#0D1117] flex justify-between items-center">
          <span className="text-sm font-medium">Total</span>
          <span className="text-sm font-mono font-bold">
            {total.score}/{total.wickets ?? 0} ({total.overs ?? "0"} ov)
          </span>
        </div>
      )}
    </div>
  );
}
