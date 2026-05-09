"use client";
import { useState, useRef, useEffect } from "react";
import { useMatchSocket } from "./hooks/useMatchSocket";
import { useCommentarySocket } from "./hooks/useCommentarySocket";
import type { BatterEntry, BowlerEntry, FallOfWicket } from "./lib/types";
import ScoreStrip from "./components/ScoreStrip";
import BattingCard from "./components/BattingCard";
import BowlingCard from "./components/BowlingCard";
import ThisOver from "./components/ThisOver";
import FieldMap from "./components/FieldMap";
import CommentaryFeed from "./components/CommentaryFeed";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8765";
const COMMENTARY_WS =
  process.env.NEXT_PUBLIC_COMMENTARY_WS || "ws://localhost:8766";

type Tab = "live" | "scorecard" | "field" | "commentary";

function shortName(name: string) {
  return name.split(" ").pop() || name;
}

const TEAM_ABBREV: Record<string, string> = {
  "New Zealand": "NZ",
  England: "ENG",
  India: "IND",
  Australia: "AUS",
  "South Africa": "SA",
  "West Indies": "WI",
  Pakistan: "PAK",
  "Sri Lanka": "SL",
  Bangladesh: "BAN",
  Afghanistan: "AFG",
  Zimbabwe: "ZIM",
  Ireland: "IRE",
  Netherlands: "NED",
  Scotland: "SCO",
  "Kolkata Knight Riders": "KKR",
  "Punjab Kings": "PBKS",
  "Mumbai Indians": "MI",
  "Chennai Super Kings": "CSK",
  "Royal Challengers Bengaluru": "RCB",
  "Delhi Capitals": "DC",
  "Sunrisers Hyderabad": "SRH",
  "Rajasthan Royals": "RR",
  "Lucknow Super Giants": "LSG",
  "Gujarat Titans": "GT",
};

function teamAbbrev(name?: string): string {
  if (!name) return "";
  return TEAM_ABBREV[name] || name;
}

function bowlingSquadToPlaceholderBatters(
  squad: BowlerEntry[] | undefined,
): BatterEntry[] {
  if (!squad?.length) return [];
  return squad.map((p, i) => ({
    name: p.name,
    status: "yet_to_bat",
    runs: null,
    balls: null,
    fours: 0,
    sixes: 0,
    sr: 0,
    dismissal: null,
    is_striker: false,
    position: i + 1,
    batting_style: p.batting_style,
    bowling_style: p.bowling_style,
  }));
}

function battingSquadToPlaceholderBowlers(
  squad: BatterEntry[] | undefined,
): BowlerEntry[] {
  if (!squad?.length) return [];
  return squad.map((p) => ({
    name: p.name,
    overs: null,
    maidens: 0,
    runs: null,
    wickets: null,
    economy: null,
    is_current: false,
    batting_style: p.batting_style,
    bowling_style: p.bowling_style,
  }));
}

interface OverEntry {
  balls?: string[];
  broadcast_balls?: string[];
  bowler?: string;
  bowler_figures?: { overs?: string; runs?: number; wickets?: number };
}

function fmtTag(v: unknown): string {
  if (v === null || v === undefined) return "—";
  const s = String(v).trim();
  if (!s || s.toLowerCase() === "unknown" || s.toLowerCase() === "not_visible")
    return "—";
  return s.replace(/_/g, " ");
}

function isKnown(v: unknown): boolean {
  return fmtTag(v) !== "—";
}

interface Layer2FieldDiagLike {
  owner: string;
  committed: boolean;
  owner_value: string | number | boolean | null;
  owner_conf: number;
  other_value: string | number | boolean | null;
  other_conf: number;
  agree: boolean;
}

interface DeliveryInfoLike {
  length?: string;
  line?: string;
  bowling_angle?: string;
  bounce?: string;
  shot_type?: string;
  shot_action?: string;
  shot_intent?: string;
  shot_elevation?: string;
  shot_direction?: { side?: string; zone?: string; confidence?: string };
  swing_or_seam?: string;
  ball_speed_kph_vlm?: number | null;
  detections?: number;
  detection_rate?: number;
  commentary_line?: string;
  _method?: string;
  _vlm_confidence?: string;
  _vlm_ms?: number;
  batsman_handed?: string;
  bowling_arm?: string;
  bowling_type?: string;
  contact_quality?: string;
  narrative?: string;
  _gemini_confidence?: string;
  _qwen_ms?: number;
  _gemini_ms?: number;
  _l2_ms?: number;
  _layer2_diag?: Record<string, Layer2FieldDiagLike>;
  _layer2_committed?: number;
  _layer2_agreements?: number;
  _over_number?: number | null;
  _delivery_num?: number | null;
  _innings?: number | null;
  _event_type?: string | null;
  _pending?: boolean;
  runs?: number | null;
}

function fmtVal(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  return fmtTag(v);
}

// 2026-04-20: simplified L2 display. The user does not want model
// names, confidence numbers, or agree/disagree markers on the tiles —
// just the raw primary and secondary values so they can eyeball which
// of the two models said what. Primary = the value Layer2 committed
// for this field (from the owner model). Secondary = the other model's
// raw answer for the same field. Both come straight from
// `_layer2_diag[<field>]` in the pipeline payload.
interface TileSpec {
  label: string;
  // L2 diag key; when present we show primary + secondary.
  diagKey?: string;
  // Fallback scalar for single-model / legacy payloads.
  legacy?: string | number | boolean | null | undefined;
}

// Handedness and bowling arm moved out of per-delivery detection —
// they now live on the batter/bowler cards (sourced from the squad
// enrichment LLM pass at setup). See player_enrichment.py.
const L2_TILES: TileSpec[] = [
  { label: "Length", diagKey: "length" },
  { label: "Line", diagKey: "line" },
  { label: "Angle", diagKey: "bowling_angle" },
  { label: "Bounce", diagKey: "bounce" },
  { label: "Shot", diagKey: "shot_type" },
  { label: "Elev.", diagKey: "elevation" },
  { label: "Side", diagKey: "shot_side" },
  { label: "Zone", diagKey: "shot_angle" },
  { label: "Type", diagKey: "bowling_type" },
  { label: "Contact", diagKey: "contact_quality" },
];

function DeliveryTile({
  label,
  primary,
  secondary,
  primaryKnown,
  dualModel,
}: {
  label: string;
  primary: string;
  secondary?: string;
  primaryKnown: boolean;
  dualModel: boolean;
}) {
  const secondaryDiffers =
    dualModel && secondary !== undefined && secondary !== primary;
  return (
    <div
      className={`rounded px-1.5 py-1 border min-w-0 ${
        primaryKnown
          ? "bg-[#0D1117] border-[#30363D]"
          : "bg-[#0D1117]/40 border-[#30363D]/40"
      }`}
    >
      <div className="text-[9px] uppercase tracking-wider text-[#8B949E] truncate">
        {label}
      </div>
      <div
        className={`text-[11px] font-mono truncate ${
          primaryKnown ? "text-[#E6EDF3]" : "text-[#484F58]"
        }`}
        title={primary}
      >
        {primary}
      </div>
      {dualModel && (
        <div
          className={`text-[10px] font-mono truncate ${
            secondaryDiffers ? "text-[#D29922]/80" : "text-[#484F58]"
          }`}
          title={secondary ?? "—"}
        >
          · {secondary ?? "—"}
        </div>
      )}
    </div>
  );
}

function fmtOverLabel(overNum: number | null | undefined): string {
  // `_over_number` from the pipeline is a cricket-over float like
  // 17.3 (= 17 overs, 3 balls). Show as-is so it lines up with the
  // top score strip (which renders the same string).
  if (overNum == null || Number.isNaN(overNum)) return "—";
  // Normalise a nicer 1-decimal display (17.30000001 → 17.3).
  const whole = Math.floor(overNum);
  const ball = Math.round((overNum - whole) * 10);
  return `${whole}.${ball}`;
}

function fmtRunsLabel(
  runs: number | null | undefined,
  eventType: string | null | undefined,
): string {
  const et = (eventType || "").toUpperCase();
  if (et === "WICKET") return "W";
  if (et === "WIDE") return `wd${runs && runs > 1 ? `+${runs - 1}` : ""}`;
  if (et === "NO_BALL") return `nb${runs && runs > 1 ? `+${runs - 1}` : ""}`;
  if (runs == null) return "—";
  if (runs === 0) return "dot";
  return `${runs} run${runs === 1 ? "" : "s"}`;
}

function DeliveryInfoPanel({ di }: { di?: DeliveryInfoLike | null }) {
  const diag = di?._layer2_diag;
  const isL2 = di?._method === "layer2" && !!diag;
  const isPending = di?._pending === true;

  const tiles: {
    label: string;
    primary: string;
    secondary?: string;
    primaryKnown: boolean;
    dualModel: boolean;
  }[] = L2_TILES.map((t) => {
    const d = t.diagKey ? diag?.[t.diagKey] : undefined;
    if (isL2 && d) {
      const p = fmtVal(d.owner_value);
      const s = fmtVal(d.other_value);
      return {
        label: t.label,
        primary: p,
        secondary: s,
        primaryKnown: p !== "—" && p.toLowerCase() !== "unknown",
        dualModel: true,
      };
    }
    // Legacy / non-L2 fallback — best-effort mapping to legacy keys so
    // pre-L2 classifiers still render useful content.
    let legacy: unknown;
    switch (t.diagKey) {
      case "length": legacy = di?.length; break;
      case "line": legacy = di?.line; break;
      case "bowling_angle": legacy = di?.bowling_angle; break;
      case "bounce": legacy = di?.bounce; break;
      case "shot_type": legacy = di?.shot_action; break;
      case "elevation": legacy = di?.shot_elevation || di?.shot_type; break;
      case "shot_side": legacy = di?.shot_direction?.side; break;
      case "shot_angle": legacy = di?.shot_direction?.zone; break;
      case "bowling_type": legacy = di?.bowling_type; break;
      case "contact_quality": legacy = di?.contact_quality; break;
      default: legacy = undefined;
    }
    const p = fmtTag(legacy);
    return {
      label: t.label,
      primary: p,
      primaryKnown: p !== "—" && p.toLowerCase() !== "unknown",
      dualModel: false,
    };
  });

  const overLabel = fmtOverLabel(di?._over_number ?? null);
  const runsLabel = fmtRunsLabel(
    di?.runs ?? null,
    di?._event_type ?? null,
  );
  const dnum = di?._delivery_num ?? null;
  const l2Ms = di?._l2_ms;

  return (
    <div className="mt-2 pt-2 border-t border-[#30363D]/50">
      <div className="flex items-center justify-between mb-1.5 flex-wrap gap-y-1">
        <div className="text-[10px] uppercase tracking-wider text-[#8B949E] flex items-center gap-1.5">
          Last Delivery
          {di && overLabel !== "—" && (
            <span
              className="text-[10px] font-mono normal-case tracking-normal px-1.5 py-[1px] rounded bg-[#0D1117] border border-[#30363D] text-[#C9D1D9]"
              title="Over and runs that these details describe"
            >
              Ov {overLabel}
              {dnum != null && <span className="text-[#484F58]"> · #{dnum}</span>}
              <span className="text-[#484F58]"> · </span>
              <span className="text-[#E6EDF3]">{runsLabel}</span>
            </span>
          )}
          {isPending && (
            <span className="text-[9px] font-mono px-1 py-[1px] rounded border border-[#D29922]/40 bg-[#D29922]/10 text-[#D29922] animate-pulse">
              analyzing…
            </span>
          )}
        </div>
        <div className="text-[10px] font-mono text-[#484F58] flex gap-2 flex-wrap items-center">
          {!di && <span>awaiting first delivery</span>}
          {di && isL2 && l2Ms !== undefined && (
            <span>took {(l2Ms / 1000).toFixed(1)}s</span>
          )}
          {di && !isL2 && di._method && <span>{di._method}</span>}
        </div>
      </div>
      <div className="grid grid-cols-4 gap-1">
        {tiles.map((t) => (
          <DeliveryTile
            key={t.label}
            label={t.label}
            primary={t.primary}
            secondary={t.secondary}
            primaryKnown={t.primaryKnown}
            dualModel={t.dualModel}
          />
        ))}
      </div>
      {di?.commentary_line && (
        <div className="mt-1.5 text-[11px] italic text-[#8B949E] truncate">
          &ldquo;{di.commentary_line}&rdquo;
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const { state, connected, lastUpdate } = useMatchSocket(WS_URL);
  const { entries: commentaryEntries, connected: commConnected } =
    useCommentarySocket(COMMENTARY_WS);
  const [tab, setTab] = useState<Tab>("live");
  const [activePersonas, setActivePersonas] = useState(
    new Set(["wire", "storyteller", "analyst", "colour"]),
  );
  const lastSessionRef = useRef<string | null>(null);
  const [scorecardInningsTab, setScorecardInningsTab] = useState<1 | 2>(1);

  const togglePersona = (p: string) => {
    setActivePersonas((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  };

  // Session reset: if session_id changes, clear stale data
  useEffect(() => {
    if (!state) return;
    const sid = state.session_id;
    if (sid && lastSessionRef.current && sid !== lastSessionRef.current) {
      // Session changed — data will naturally refresh from new state
    }
    if (sid) lastSessionRef.current = sid;
  }, [state]);

  useEffect(() => {
    if (!state) return;
    const inn = state.match?.innings ?? 1;
    setScorecardInningsTab(inn >= 2 ? 2 : 1);
  }, [state?.match?.innings, state]);

  if (!state) {
    return (
      <div className="min-h-screen bg-[#0D1117] flex items-center justify-center">
        <div className="text-center">
          <div className="animate-pulse text-[#58A6FF] text-lg mb-2">
            {connected
              ? "Waiting for match data..."
              : "Connecting to pipeline..."}
          </div>
          <div className="text-xs text-[#8B949E]">
            {connected ? "Pipeline running, no data yet" : `Trying ${WS_URL}`}
          </div>
        </div>
      </div>
    );
  }

  const isPreMatch =
    state.match?.phase === "pre_match" && state.scorecard?.score == null;

  if (isPreMatch) {
    const toss = state.match?.toss;
    return (
      <div className="min-h-screen bg-[#0D1117] text-[#E6EDF3]">
        <div className="bg-[#161B22] border-b border-[#30363D] px-4 py-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-[#8B949E]">Pre-Match</span>
            <div className="flex items-center gap-1.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  connected
                    ? "bg-[#3FB950] animate-pulse"
                    : "bg-[#F85149]"
                }`}
              />
              <span className="text-xs text-[#8B949E]">
                {connected ? "CONNECTED" : "OFFLINE"}
              </span>
            </div>
          </div>
          <div className="text-center py-6">
            <div className="text-lg font-bold text-white mb-4">
              {teamAbbrev(state.match?.team_a) || "Team A"}
              <span className="text-[#8B949E] mx-3 text-sm font-normal">
                vs
              </span>
              {teamAbbrev(state.match?.team_b) || "Team B"}
            </div>
            {toss?.winner ? (
              <div className="bg-[#0D1117] rounded-lg p-4 inline-block border border-[#30363D]">
                <div className="text-xs text-[#8B949E] uppercase tracking-wider mb-1">
                  Toss
                </div>
                <div className="text-sm text-[#58A6FF] font-medium">
                  {toss.winner} won the toss
                </div>
                <div className="text-sm text-[#E6EDF3] mt-0.5">
                  elected to{" "}
                  <span className="font-bold text-[#D29922]">
                    {toss.decision}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-[#8B949E] animate-pulse">
                Waiting for toss...
              </div>
            )}
            <div className="mt-6 text-xs text-[#8B949E] animate-pulse">
              Waiting for play to start...
            </div>
          </div>
        </div>
      </div>
    );
  }

  const sc = state.scorecard || {};
  const sit = state.match_situation || {};
  const battingCard = state.batting_card || [];

  // Bug #17: derive CRR/Balls strictly from the canonical scorecard
  // (sc.score, sc.overs) instead of `state.match_situation`. The
  // situation dict is built on the backend from a separate state
  // snapshot and frequently drifts from the scorecard mid-frame —
  // producing nonsense like "CRR 590" when overs briefly read 0
  // while score was still mid-update. Single source of truth: the
  // same overs string the top score-strip displays.
  const overs_n =
    sc.overs != null && !isNaN(parseFloat(String(sc.overs)))
      ? parseFloat(String(sc.overs))
      : null;
  const score_n =
    sc.score != null && !isNaN(Number(sc.score)) ? Number(sc.score) : null;
  const ballsBowledDerived =
    overs_n != null && overs_n > 0
      ? Math.floor(overs_n) * 6 + Math.round((overs_n % 1) * 10)
      : 0;
  const crrDerived =
    score_n != null && ballsBowledDerived > 0
      ? Number(((score_n / ballsBowledDerived) * 6).toFixed(2))
      : null;
  const bowlingCard = state.bowling_card || [];
  const fow = Array.isArray(state.fall_of_wickets)
    ? state.fall_of_wickets
    : [];
  const overHistory: Record<string, OverEntry | string[]> =
    state.over_history || {};
  const teamScore = sc.score ?? 0;
  const teamWickets = sc.wickets ?? 0;
  const currentOverNum = Math.floor(parseFloat(sc.overs || "0"));

  // FIX 6: This-over — hide if sum exceeds team score (stale data)
  let thisOver = Array.isArray(state.this_over) ? state.this_over : [];
  const thisOverRuns = thisOver.reduce((sum: number, b: string) => {
    if (b === "W" || b === ".") return sum;
    if (b === "wd" || b === "nb") return sum + 1;
    return sum + (parseInt(b) || 0);
  }, 0);
  if (thisOverRuns > teamScore && teamScore > 0) {
    thisOver = [];
  }

  // FIX 5: Recent overs — only show overs <= current over
  const validOverEntries = Object.entries(overHistory)
    .filter(([ovNum]) => parseInt(ovNum) <= currentOverNum)
    .sort(([a], [b]) => parseInt(b) - parseInt(a))
    .slice(0, 5);

  // FIX 1: Derive wickets_in_hand from scorecard.wickets (single source of truth)
  const wicketsInHand =
    teamWickets != null ? 10 - Number(teamWickets) : undefined;

  // FIX 3: Partnership — only show if runs <= team score
  const partnership = state.partnerships?.current;
  const showPartnership =
    partnership &&
    partnership.runs > 0 &&
    partnership.runs <= (teamScore || 999);

  return (
    <div className="min-h-screen bg-[#0D1117] text-[#E6EDF3]">
      <ScoreStrip
        scorecard={sc}
        match={state.match}
        connected={connected}
        lastUpdate={lastUpdate}
        venue={state.venue}
        matchInfo={state.match_info}
      />
      {state.match?.match_phase === "strategic_timeout" && (
        <div className="bg-[#3F2A12] border-y border-[#FFA657]/40 text-[#FFA657] text-sm font-medium text-center py-2">
          STRATEGIC TIMEOUT — broadcast on ad break, polling backed off
        </div>
      )}

      <div className="flex border-b border-[#30363D] bg-[#0D1117] sticky top-0 z-10">
        {(["live", "scorecard", "field", "commentary"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-3 text-sm font-medium capitalize transition-colors ${
              tab === t
                ? "text-[#58A6FF] border-b-2 border-[#58A6FF]"
                : "text-[#8B949E] hover:text-[#E6EDF3]"
            }`}
          >
            {t === "commentary" ? "Comm" : t}
          </button>
        ))}
      </div>

      <div className="max-w-lg mx-auto px-3 py-2 pb-8">
        {/* ========== LIVE TAB ========== */}
        {tab === "live" && (
          <>
            <div className="bg-[#161B22] rounded-lg border border-[#30363D] p-3 mt-2">
              <div className="flex justify-between items-center">
                <div className="flex gap-4 text-xs">
                  <span>
                    <span className="text-[#8B949E]">CRR </span>
                    <span className="font-mono text-[#E6EDF3]">
                      {crrDerived != null && crrDerived > 0
                        ? crrDerived.toFixed(2)
                        : "—"}
                    </span>
                  </span>
                  <span>
                    <span className="text-[#8B949E]">Balls </span>
                    <span className="font-mono text-[#E6EDF3]">
                      {ballsBowledDerived > 0
                        ? `${ballsBowledDerived}/120`
                        : "—"}
                    </span>
                  </span>
                  <span>
                    <span className="text-[#8B949E]">Wkts left </span>
                    <span className="font-mono text-[#E6EDF3]">
                      {wicketsInHand ?? "—"}
                    </span>
                  </span>
                </div>
                <span
                  className={`text-xs font-mono min-w-[68px] text-right ${
                    state.speed_kph != null && Number(state.speed_kph) > 0
                      ? "text-[#D29922]"
                      : "text-[#484F58]"
                  }`}
                >
                  {state.speed_kph != null && Number(state.speed_kph) > 0
                    ? `${state.speed_kph} kph`
                    : "— kph"}
                </span>
              </div>
              <DeliveryInfoPanel di={state.delivery_info} />
              {state.match?.innings === 2 &&
                (() => {
                  // Always render the chase strip during innings 2 to
                  // avoid flicker. Prefer backend-computed values, but
                  // fall back to derivations from target/score/overs
                  // when the situation dict transiently goes null
                  // mid-frame. Show '—' placeholders if even the
                  // derivations aren't available yet, but never hide.
                  const target =
                    sit.target ??
                    (state.match?.target != null
                      ? Number(state.match.target)
                      : null);
                  const runsNeededDerived =
                    sit.runs_needed != null
                      ? Number(sit.runs_needed)
                      : target != null && score_n != null
                        ? Math.max(0, target - score_n)
                        : null;
                  const ballsRemainingDerived =
                    sit.balls_remaining != null
                      ? Number(sit.balls_remaining)
                      : ballsBowledDerived > 0
                        ? Math.max(0, 120 - ballsBowledDerived)
                        : null;
                  const rrr =
                    sit.required_rate != null
                      ? Number(sit.required_rate)
                      : runsNeededDerived != null &&
                          ballsRemainingDerived != null &&
                          ballsRemainingDerived > 0
                        ? Number(
                            (
                              (runsNeededDerived /
                                ballsRemainingDerived) *
                              6
                            ).toFixed(2),
                          )
                        : null;
                  return (
                    <div className="mt-2 pt-2 border-t border-[#30363D]/50 text-sm text-[#D29922]">
                      Need{" "}
                      <span className="font-mono font-bold">
                        {runsNeededDerived ?? "—"}
                      </span>{" "}
                      from{" "}
                      <span className="font-mono font-bold">
                        {ballsRemainingDerived ?? "—"}
                      </span>{" "}
                      balls
                      {rrr != null && (
                        <span className="text-xs ml-2 text-[#8B949E]">
                          RRR {rrr.toFixed(2)}
                        </span>
                      )}
                      {target != null && (
                        <span className="text-xs ml-2 text-[#8B949E]">
                          target {target}
                        </span>
                      )}
                    </div>
                  );
                })()}
            </div>

            <ThisOver balls={thisOver} />

            <BattingCard
              batters={battingCard.filter((b) => b.status === "batting")}
              title="At The Crease"
              compact
              teamScore={teamScore}
            />

            <BowlingCard
              bowlers={bowlingCard.filter((b) => b.is_current)}
              title="Bowling"
              compact
              teamScore={teamScore}
            />

            <div className="grid grid-cols-2 gap-2 mt-2">
              <div className="bg-[#161B22] rounded-lg p-3 border border-[#30363D]">
                <div className="text-xs text-[#8B949E]">Partnership</div>
                <div className="text-sm font-mono mt-1">
                  {showPartnership
                    ? `${partnership!.runs} runs (${partnership!.balls} balls)`
                    : <span className="text-[#484F58]">— runs (— balls)</span>
                  }
                </div>
              </div>
              <div className="bg-[#161B22] rounded-lg p-3 border border-[#30363D]">
                <div className="text-xs text-[#8B949E]">Extras</div>
                <div className="text-sm font-mono mt-1 flex items-baseline gap-1.5">
                  <span
                    className={
                      (state.extras?.total ?? 0) > 0
                        ? "text-[#E6EDF3] font-semibold"
                        : "text-[#484F58]"
                    }
                  >
                    {state.extras?.total ?? 0}
                  </span>
                  <span className="text-[10px] text-[#8B949E] tracking-tight">
                    wd{state.extras?.wides ?? 0} nb
                    {state.extras?.no_balls ?? 0} b{state.extras?.byes ?? 0} lb
                    {state.extras?.leg_byes ?? 0}
                    {(state.extras?.penalties ?? 0) > 0 &&
                      ` p${state.extras!.penalties}`}
                  </span>
                </div>
                <div
                  className={`text-xs mt-0.5 ${
                    (state.extras?.this_over ?? 0) > 0
                      ? "text-[#D29922]"
                      : "text-[#484F58]"
                  }`}
                >
                  {(state.extras?.this_over ?? 0) > 0
                    ? `+${state.extras!.this_over} this over`
                    : "— this over"}
                </div>
              </div>
            </div>

            {fow.length > 0 && (
              <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 p-3">
                <div className="text-xs text-[#8B949E] mb-1.5">
                  Fall of Wickets
                </div>
                <div className="flex flex-wrap gap-2">
                  {fow.map((w, i) => (
                    <div
                      key={i}
                      className={`text-xs font-mono px-2 py-1 rounded border ${
                        w._unwitnessed
                          ? "bg-[#0D1117]/50 border-[#30363D]/30 text-[#484F58] italic"
                          : "bg-[#0D1117] border-[#30363D]/50"
                      }`}
                    >
                      {w._unwitnessed ? (
                        <>
                          <span>W{w.wicket}</span>{" "}
                          <span>— details unavailable</span>
                        </>
                      ) : (
                        <>
                          <span className="text-[#F85149]">
                            {w.score}/{w.wicket}
                          </span>{" "}
                          <span className="text-[#8B949E]">
                            ({shortName(w.batter || "")}, {w.overs})
                          </span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent overs — only show valid overs */}
            {validOverEntries.length > 0 && (
              <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 p-3">
                <div className="text-xs text-[#8B949E] mb-1.5">
                  Recent Overs
                </div>
                {validOverEntries.map(([ov, entry]) => {
                  const balls: string[] = Array.isArray(entry)
                    ? entry
                    : Array.isArray(entry?.balls)
                      ? entry.balls
                      : Array.isArray(entry?.broadcast_balls)
                        ? entry.broadcast_balls
                        : [];
                  const bowler =
                    typeof entry === "object" &&
                    entry &&
                    !Array.isArray(entry)
                      ? entry.bowler
                      : null;
                  if (!balls.length && !bowler) return null;
                  return (
                    <div
                      key={ov}
                      className="flex items-center gap-2 mb-1 last:mb-0"
                    >
                      <span className="text-xs text-[#8B949E] w-10 shrink-0">
                        Ov {parseInt(ov) + 1}
                      </span>
                      {bowler && (
                        <span className="text-xs text-[#C9D1D9] w-16 truncate shrink-0">
                          {shortName(bowler)}
                        </span>
                      )}
                      {balls.length > 0 ? (
                        <div className="flex gap-1">
                          {balls.map((b, i) => (
                            <span
                              key={i}
                              className={`text-xs font-mono w-5 h-5 rounded-full flex items-center justify-center ${
                                b === "W"
                                  ? "bg-[#F85149]/20 text-[#F85149]"
                                  : b === "4"
                                    ? "bg-[#58A6FF]/20 text-[#58A6FF]"
                                    : b === "6"
                                      ? "bg-[#D29922]/20 text-[#D29922]"
                                      : "text-[#8B949E]"
                              }`}
                            >
                              {b}
                            </span>
                          ))}
                        </div>
                      ) : !bowler ? (
                        <span className="text-xs text-[#8B949E]">
                          no data
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ========== SCORECARD TAB ========== */}
        {tab === "scorecard" &&
          (() => {
            const curInn = state.match?.innings ?? 1;
            const innHist = state.innings_history ?? [];
            const frozen = innHist[0];
            const isFutureInn2 = scorecardInningsTab === 2 && curInn === 1;

            let battingTitle: string;
            let battingRows: BatterEntry[];
            let bowlingTitle: string;
            let bowlingRows: BowlerEntry[];
            let fowRows: FallOfWicket[];
            let tot: {
              score: number | null;
              wickets: number | null;
              overs: string | null;
            };
            let extrasEff: typeof state.extras;
            let teamScoreEff: number;

            if (isFutureInn2) {
              battingTitle = `${teamAbbrev(sc.bowling_team) || "Batting"} — Innings 2 (yet to bat)`;
              battingRows = bowlingSquadToPlaceholderBatters(
                state.full_bowling_squad,
              );
              bowlingTitle = `${teamAbbrev(sc.batting_team) || "Bowling"} — Innings 2 (bowling)`;
              bowlingRows = battingSquadToPlaceholderBowlers(
                state.full_batting_squad,
              );
              fowRows = [];
              tot = { score: null, wickets: null, overs: null };
              extrasEff = undefined;
              teamScoreEff = 0;
            } else if (scorecardInningsTab === 1 && curInn >= 2) {
              if (frozen) {
                battingTitle = `${teamAbbrev(frozen.batting_team ?? "") || "Batting"} — Innings 1`;
                battingRows = frozen.batting_card ?? [];
                bowlingTitle = `${teamAbbrev(frozen.bowling_team ?? "") || "Bowling"}`;
                bowlingRows = frozen.bowling_card ?? [];
                fowRows = (frozen.fall_of_wickets as FallOfWicket[]) ?? [];
                tot = {
                  score: frozen.score ?? null,
                  wickets: frozen.wickets ?? null,
                  overs:
                    frozen.overs != null && frozen.overs !== ""
                      ? String(frozen.overs)
                      : null,
                };
                extrasEff = frozen.extras;
                teamScoreEff = Number(frozen.score ?? 0);
              } else {
                battingTitle = "Innings 1 — archived scorecard unavailable";
                battingRows = [];
                bowlingTitle = "Bowling";
                bowlingRows = [];
                fowRows = [];
                tot = { score: null, wickets: null, overs: null };
                extrasEff = undefined;
                teamScoreEff = 0;
              }
            } else {
              battingTitle = `${teamAbbrev(sc.batting_team) || "Batting"} — Innings ${curInn}`;
              battingRows = state.full_batting_squad || battingCard;
              bowlingTitle = `${teamAbbrev(sc.bowling_team) || "Bowling"}`;
              bowlingRows = state.full_bowling_squad || bowlingCard;
              fowRows = fow;
              tot = {
                score: sc.score ?? null,
                wickets: sc.wickets ?? null,
                overs:
                  sc.overs != null && sc.overs !== ""
                    ? String(sc.overs)
                    : null,
              };
              extrasEff = state.extras;
              teamScoreEff = teamScore;
            }

            return (
              <>
                <div className="flex gap-2 mt-2">
                  {([1, 2] as const).map((inn) => (
                    <button
                      key={inn}
                      type="button"
                      onClick={() => setScorecardInningsTab(inn)}
                      className={`flex-1 rounded-full py-2 text-xs font-semibold transition-colors ${
                        scorecardInningsTab === inn
                          ? "bg-[#58A6FF] text-[#0D1117]"
                          : "bg-[#21262D] text-[#8B949E] border border-[#30363D] hover:border-[#484F58]"
                      }`}
                    >
                      Innings {inn}
                    </button>
                  ))}
                </div>

                <BattingCard
                  batters={battingRows}
                  title={battingTitle}
                  extras={extrasEff}
                  total={tot}
                  teamScore={teamScoreEff}
                />

                {fowRows.length > 0 && (
                  <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 overflow-hidden">
                    <div className="px-3 py-2 border-b border-[#30363D]">
                      <span className="text-xs font-medium text-[#8B949E] uppercase tracking-wide">
                        Fall of Wickets
                      </span>
                    </div>
                    {fowRows.map((w, i) => (
                      <div
                        key={i}
                        className={`flex justify-between px-3 py-1.5 border-b border-[#30363D]/30 last:border-0 text-sm ${
                          w._unwitnessed ? "italic opacity-60" : ""
                        }`}
                      >
                        <span className="text-[#8B949E]">
                          {w.wicket}.{" "}
                          {w._unwitnessed
                            ? "details unavailable"
                            : shortName(w.batter || "")}
                        </span>
                        <span className="font-mono">
                          {w._unwitnessed ? (
                            <span className="text-[#484F58]">—</span>
                          ) : (
                            <>
                              <span className="text-[#F85149]">{w.score}</span>
                              <span className="text-[#8B949E] ml-1">
                                ({w.overs})
                              </span>
                            </>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {bowlingRows.length > 0 ? (
                  <BowlingCard
                    bowlers={bowlingRows}
                    title={bowlingTitle}
                    teamScore={teamScoreEff}
                  />
                ) : (
                  <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 p-3 text-center text-[#8B949E] text-sm">
                    Bowling data not yet available
                  </div>
                )}
              </>
            );
          })()}

        {/* ========== FIELD TAB ========== */}
        {tab === "field" && (
          <>
            {state.field && state.field.positions?.length > 0 ? (
              <FieldMap field={state.field} />
            ) : (
              <div className="text-center text-sm text-[#8B949E] mt-8">
                No field data available yet
              </div>
            )}

            {bowlingCard.filter((b) => b.is_current).length > 0 && (
              <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 p-3">
                <div className="text-xs text-[#8B949E] mb-1">
                  Current Bowler
                </div>
                {bowlingCard
                  .filter((b) => b.is_current)
                  .map((b) => (
                    <div
                      key={b.name}
                      className="flex justify-between items-baseline"
                    >
                      <span className="text-sm font-medium text-white">
                        {b.name}
                      </span>
                      <span className="text-sm font-mono text-[#8B949E]">
                        {b.wickets}-{Math.min(b.runs || 0, teamScore || 999)} (
                        {b.overs})
                      </span>
                    </div>
                  ))}
              </div>
            )}

            {state.field?.phase && (
              <div className="bg-[#161B22] rounded-lg border border-[#30363D] mt-2 p-3">
                <div className="flex justify-between text-xs">
                  <span className="text-[#8B949E]">Phase</span>
                  <span className="text-[#E6EDF3] capitalize">{state.field.phase}</span>
                </div>
              </div>
            )}
          </>
        )}

        {/* ========== COMMENTARY TAB ========== */}
        {tab === "commentary" && (
          <CommentaryFeed
            entries={commentaryEntries}
            activePersonas={activePersonas}
            onTogglePersona={togglePersona}
            connected={commConnected}
          />
        )}
      </div>
    </div>
  );
}
