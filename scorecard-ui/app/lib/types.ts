export interface BatterEntry {
  name: string;
  status: string;
  runs: number | null;
  balls: number | null;
  fours: number;
  sixes: number;
  sr: number;
  dismissal: string | null;
  is_striker: boolean;
  position: number;
  // Populated once pre-match by the squad-enrichment LLM pass. Free-text.
  // e.g. "RHB" / "LHB" / "unknown", "Right-arm fast" / "None" / "unknown".
  batting_style?: string;
  bowling_style?: string;
}

export interface BowlerEntry {
  name: string;
  overs: string | null;
  maidens: number;
  runs: number | null;
  wickets: number | null;
  economy: number | null;
  is_current: boolean;
  batting_style?: string;
  bowling_style?: string;
}

export interface Scorecard {
  score?: number | null;
  wickets?: number | null;
  overs?: string | null;
  run_rate?: number | null;
  batting_team?: string;
  bowling_team?: string;
  striker?: string | null;
  non_striker?: string | null;
  current_bowler?: string | null;
}

export interface MatchInfo {
  team_a?: string;
  team_b?: string;
  innings?: number;
  target?: number | null;
  toss?: {
    winner?: string | null;
    decision?: string | null;
  };
  phase?: string;
  match_phase?: string;
}

export interface Partnership {
  batters?: string[];
  runs: number;
  balls: number;
  ended?: boolean;
}

/** Archived innings snapshot from backend ``innings_history`` (WS). */
export interface InningsHistoryEntry {
  innings: number;
  score?: number | null;
  wickets?: number | null;
  overs?: number | string | null;
  batting_team?: string | null;
  bowling_team?: string | null;
  batting_card?: BatterEntry[];
  bowling_card?: BowlerEntry[];
  fow_list?: unknown[];
  fall_of_wickets?: FallOfWicket[];
  partnerships?: { current?: Partnership | null };
  extras?: Extras;
}

export interface MatchSituation {
  runs_needed?: number;
  balls_remaining?: number;
  required_rate?: number;
  phase?: string;
  run_rate?: number;
  balls_bowled?: number;
  wickets_in_hand?: number;
  target?: number;
}

export interface Extras {
  wides?: number;
  no_balls?: number;
  byes?: number;
  leg_byes?: number;
  penalties?: number;
  total?: number;
  this_over?: number;
}

export interface FieldPosition {
  name: string;
  x: number;
  y: number;
  type: "wk" | "bowler" | "bat" | "close" | "in" | "out";
  confidence: number;
}

export interface FieldData {
  positions: FieldPosition[];
  formation?: string;
  inside_count?: number;
  outside_count?: number;
  phase?: string;
  confidence?: string;
}

export interface FallOfWicket {
  wicket: number;
  batter: string | null;
  score: number | null;
  overs: string | null;
  bowler?: string | null;
  how?: string | null;
  _unwitnessed?: boolean;
}

export interface OverEntry {
  balls?: string[];
  broadcast_balls?: string[];
  bowler?: string;
  bowler_figures?: { overs?: string; runs?: number; wickets?: number };
}

export interface Layer2FieldDiag {
  owner: string;
  committed: boolean;
  owner_value: string | number | boolean | null;
  owner_conf: number;
  other_value: string | number | boolean | null;
  other_conf: number;
  agree: boolean;
}

export interface DeliveryInfo {
  length?: string;
  line?: string;
  bowling_angle?: string;
  pitch_position?: string;
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

  // Layer 2 — Qwen + Gemini routed spatial classifier
  batsman_handed?: string;
  bowling_arm?: string;
  bowling_type?: string;
  contact_quality?: string;
  narrative?: string;
  _gemini_confidence?: string;
  _gemini_model?: string;
  _qwen_model?: string;
  _gemini_ms?: number;
  _qwen_ms?: number;
  _l2_ms?: number;
  _layer2_routed?: Record<string, string | number | boolean | null>;
  _layer2_conf?: Record<string, number>;
  _layer2_diag?: Record<string, Layer2FieldDiag>;
  _layer2_committed?: number;
  _layer2_agreements?: number;

  // Freshness metadata — which delivery these details describe.
  _over_number?: number | null;
  _delivery_num?: number | null;
  _innings?: number | null;
  _event_type?: string | null;
  _pending?: boolean;
  _wall_ms?: number;
  runs?: number | null;
}

export interface MatchState {
  type: string;
  session_id?: string;
  timestamp: number;
  frame: number;
  scorecard?: Scorecard;
  batting_card?: BatterEntry[];
  bowling_card?: BowlerEntry[];
  match?: MatchInfo;
  this_over?: string[];
  match_situation?: MatchSituation;
  extras?: Extras;
  partnerships?: { current?: Partnership | null };
  over_history?: Record<string, OverEntry | string[]>;
  field?: FieldData;
  speed_kph?: number | null;
  venue?: string | null;
  match_info?: string | null;
  delivery_info?: DeliveryInfo | null;
  fall_of_wickets?: FallOfWicket[];
  full_batting_squad?: BatterEntry[];
  full_bowling_squad?: BowlerEntry[];
  innings_history?: InningsHistoryEntry[];
}
