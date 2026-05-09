import type { Scorecard, MatchInfo } from "../lib/types";

const TEAM_ABBREV: Record<string, string> = {
  "New Zealand": "NZ", England: "ENG", India: "IND", Australia: "AUS",
  "South Africa": "SA", "West Indies": "WI", Pakistan: "PAK",
  "Sri Lanka": "SL", Bangladesh: "BAN", Afghanistan: "AFG",
  "Kolkata Knight Riders": "KKR", "Punjab Kings": "PBKS",
  "Mumbai Indians": "MI", "Chennai Super Kings": "CSK",
  "Royal Challengers Bengaluru": "RCB", "Delhi Capitals": "DC",
  "Sunrisers Hyderabad": "SRH", "Rajasthan Royals": "RR",
  "Lucknow Super Giants": "LSG", "Gujarat Titans": "GT",
};
function teamAbbrev(name?: string) {
  if (!name) return "";
  return TEAM_ABBREV[name] || name;
}

interface Props {
  scorecard: Scorecard;
  match?: MatchInfo;
  connected: boolean;
  lastUpdate: number;
  venue?: string | null;
  matchInfo?: string | null;
}

export default function ScoreStrip({
  scorecard,
  match,
  connected,
  lastUpdate,
  venue,
  matchInfo,
}: Props) {
  const score = scorecard?.score ?? "-";
  const wickets = scorecard?.wickets ?? "-";
  const overs = scorecard?.overs ?? "-";
  const innings = match?.innings ?? 0;
  const target = match?.target;
  const isChasing = innings === 2 && target != null && target > 0;

  const runsNeeded =
    isChasing && scorecard?.score != null
      ? target! - scorecard.score
      : null;

  const oversFloat = parseFloat(String(overs)) || 0;
  const completedOvers = Math.floor(oversFloat);
  const partialBalls = Math.round((oversFloat % 1) * 10);
  const ballsBowled = completedOvers * 6 + partialBalls;
  const ballsRemaining = 120 - ballsBowled;

  const ago = lastUpdate ? Math.round((Date.now() - lastUpdate) / 1000) : null;

  return (
    <div className="bg-[#161B22] border-b border-[#30363D] px-4 py-3">
      {(venue || matchInfo) && (
        <div className="text-[10px] text-[#8B949E] mb-0.5 truncate">
          {matchInfo && <span>{matchInfo}</span>}
          {matchInfo && venue && <span> • </span>}
          {venue && <span>{venue}</span>}
        </div>
      )}
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-[#8B949E]">
          {teamAbbrev(match?.team_a) || "?"} vs {teamAbbrev(match?.team_b) || "?"}
          {innings > 0 && ` \u2022 Inn ${innings}`}
        </span>
        <div className="flex items-center gap-1.5">
          {ago !== null && ago < 30 && (
            <span className="text-[10px] text-[#8B949E]">{ago}s ago</span>
          )}
          <div
            className={`w-2 h-2 rounded-full ${connected ? "bg-[#3FB950] animate-pulse" : "bg-[#F85149]"}`}
          />
          <span className="text-xs text-[#8B949E]">
            {connected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </div>

      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-lg font-bold text-white">
            {scorecard?.batting_team
              ? teamAbbrev(scorecard.batting_team)
              : "\u2014"}
          </span>
          <span className="text-2xl font-mono font-bold text-white ml-2">
            {score}/{wickets}
          </span>
          <span className="text-sm text-[#8B949E] ml-2">({overs} ov)</span>
        </div>
        {scorecard?.run_rate != null && Number(scorecard.run_rate) > 0 && (
          <span className="text-sm text-[#8B949E]">
            CRR {Number(scorecard.run_rate).toFixed(2)}
          </span>
        )}
      </div>

      {isChasing && runsNeeded != null && runsNeeded > 0 && (
        <div className="text-sm text-[#D29922] mt-1">
          Need {runsNeeded} from {ballsRemaining} balls
        </div>
      )}

      <div className="flex gap-4 mt-2 text-xs text-[#8B949E]">
        {scorecard?.striker ? (
          <span>
            <span className="text-[#3FB950]">{"\u25CF"}</span>{" "}
            {scorecard.striker.split(" ").pop()}
          </span>
        ) : (
          <span className="text-[#484F58]">— batter</span>
        )}
        {scorecard?.non_striker &&
          scorecard.non_striker !== scorecard.striker ? (
            <span>{scorecard.non_striker.split(" ").pop()}</span>
          ) : (
            <span className="text-[#484F58]">—</span>
          )}
        {scorecard?.current_bowler ? (
          <span className="ml-auto">
            {scorecard.current_bowler.split(" ").pop()}
          </span>
        ) : (
          <span className="ml-auto text-[#484F58]">— bowler</span>
        )}
      </div>
    </div>
  );
}
