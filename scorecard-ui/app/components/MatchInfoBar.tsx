import type { MatchSituation, MatchInfo } from "../lib/types";

interface Props {
  situation: MatchSituation;
  match: MatchInfo;
}

export default function MatchInfoBar({ situation, match }: Props) {
  const balls = situation?.balls_bowled ?? 0;
  const rr = situation?.run_rate ?? 0;
  const wkts = situation?.wickets_in_hand ?? 10;
  const isChasing = match?.innings === 2 && match?.target != null;

  return (
    <div className="bg-[#161B22] rounded-lg border border-[#30363D] p-3 mt-2">
      <div className="flex justify-between items-center text-xs">
        <div className="flex gap-3">
          <span>
            <span className="text-[#8B949E]">CRR </span>
            <span className="font-mono text-[#E6EDF3]">
              {rr > 0 ? rr.toFixed(2) : "—"}
            </span>
          </span>
          <span>
            <span className="text-[#8B949E]">Balls </span>
            <span className="font-mono text-[#E6EDF3]">
              {balls > 0 ? `${balls}/120` : "—"}
            </span>
          </span>
        </div>
        <span className="text-[#8B949E]">
          {wkts} wkts in hand
        </span>
      </div>

      {isChasing &&
        situation?.runs_needed != null &&
        situation.runs_needed > 0 && (
          <div className="mt-2 pt-2 border-t border-[#30363D]/50 text-sm text-[#D29922]">
            Need{" "}
            <span className="font-mono font-bold">{situation.runs_needed}</span>{" "}
            from{" "}
            <span className="font-mono font-bold">
              {situation.balls_remaining}
            </span>{" "}
            balls
            {situation.required_rate != null && (
              <span className="text-xs ml-2 text-[#8B949E]">
                RRR {situation.required_rate.toFixed(2)}
              </span>
            )}
          </div>
        )}
    </div>
  );
}
