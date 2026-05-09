# Dual-broadcaster Path C audit — `this_over` and `partnership_*` (2026-04-29)

**Status (2026-04-29):** AUDIT ONLY. No `score_manager.py`, `eyes/scoreboard.py`, `eyes/this_over.py`, `eyes/commentary.py` (PartnershipTracker), or `test_pipeline.py` mutations in this task.

**Predecessors (cross-referenced throughout):**

- `dual_broadcaster_substrate_audit.md` (Item 5, **shipped 2026-04-29**) — inventoried 62 SM fields and 38 SB-relevant fields; classified the two surfaces audited here as **HIGH-risk**, "needs its own audit before migration".
- `dual_broadcaster_path_b_migration_contract.md` (Item 3, shipped 2026-04-29) — Path B LOW-risk batch (12 fields) and the property-backed read-through pattern with `[SM-FEEDER-SYNC]` telemetry. **This document references that pattern as PATH-B-FEEDER.**
- `build_full_payload_extraction_design.md` (shipped 2026-04-29) — extraction of the WS payload assembler into `_build_full_payload_from_state` plus byte-identity baseline (`files/path_a_ws_payload_baseline.txt`). **Path A WS-payload contract** referenced throughout as the read-side that any Path C migration must preserve.
- `get_broadcast_state_path_b_audit.md` (Lever 2, shipped 2026-04-29) — `get_broadcast_state` deprecated to a silent alias of `get_live_state`; Path A canonical projection runs in shadow + live.
- `sm_rotation_atomicity_design.md` (Lever 1 PR1+PR2, shipped 2026-04-29) — the `_set_slot_pair` helper + `_w8_non_striker_for_identified` migration. Documents the `[WS-SLOT-INVARIANT]` reduction model. **Disjoint surface from Path C** (Lever 1 is striker / non_striker only).
- `striker_path_b_read_audit.md` (Item 1, shipped 2026-04-29) — read-side audit pattern that produced "no migrable work" in some places; the same honest-assessment outcome is permitted here.
- `full_reset_fow_extras_verification.md` (2026-04-29) — established the **CORRECT** classification for `full_reset`'s wipe semantics; this audit checks whether `full_reset` covers the Path C surfaces.

**Out of scope (locked):**

- `_project_active_batters` (canonical; Lever 1 territory).
- `full_reset` (just shipped; Path C surfaces wiped at SM side, not at over_mgr/partnership_tracker — see §2.E).
- Lever 1 striker/non_striker writes (W1–W12) — disjoint.
- Path A WS-payload byte-identity sentinel (`files/path_a_ws_payload_baseline.txt` + `test_path_b_low_risk_batch_path_a_regression_signature_match`) — must remain unchanged through any recommended migration.
- Item 3 LOW-risk Path B batch (12 fields) — done, untouched.
- MEDIUM-risk pair (`SM.overs`, `SM.bat1_name/bat2_name`) — separate PRs per Item 5 §6.

---

## 0. Surface decomposition (locked, do not re-litigate)

The substrate audit (Item 5 §3 row #11–#12) called these two surfaces "**3 sources each**": `SM ↔ SB ↔ external manager`. **That count is wrong on the live path** — surfaced in this audit and corrected below. The corrected count drives the migration shape.

### 0.1 `this_over` surface — actual writers and readers (live path)

| Component | Field | Live writes? | Live reads? | Notes |
|---|---|:---:|:---:|---|
| `ScoreManager.this_over` (`score_manager.py:145`) | `list[str]` | **YES** — `_apply_event` (~L2363, L2375, L2388, L2391), `_clear_per_innings_sm_surface` (L743), `_accept_initial` (~L1378, L1387) | only by SM itself + SM `_build_payload` (L2799). **Not** read by Path A WS payload. | SM-internal mirror; never reaches the UI WS payload (see §2.A) |
| `ScoreManager.this_over_src` (`score_manager.py:146`) | `list[str]` | **YES** — paired with each `this_over` write | only by SM itself | parallel sources tracker (`"obs"` / `"bcast"`) |
| `ScoreManager.over_history` (`score_manager.py:147`) | `dict[int, list[str]]` | **YES** — `_apply_event` (~L2380), `_complete_over` (L2578), `_clear_per_innings_sm_surface` (L745) | SM `_build_payload` (L2800) + `set_innings_2` archive (L1750). **Not** read by Path A WS payload. | SM-internal mirror; same dead-end as `this_over` |
| `ScoreManager.completed_over` (`score_manager.py:148`) | `list[str] \| None` | **YES** — `_apply_event` (~L2377), `_complete_over` (L2575) | **Path A reads it as fallback** when `over_mgr.get_display(...)` is empty (`test_pipeline.py:4190-4192`) | only SM-side field that **does** reach the WS payload |
| `ScoreManager.completed_over_runs` (`score_manager.py:149`) | `int \| None` | **YES** — paired with `completed_over` | Path A reads it (`test_pipeline.py:4209-4212`) | paired emission with `completed_over` |
| `ThisOverManager.this_over` (`eyes/this_over.py:86`) | `list[str]` | **YES** — `on_ball_event`, `on_broadcast_override`, `check_over_change`, `pop_last_extra`, `reorder_wicket_to_ball`, `resync_to_over`, `reset` | **Path A reads via `over_mgr.get_display(overs)`** (`test_pipeline.py:4184`). Authoritative for the WS `this_over` field. | the *real* canonical writer |
| `ThisOverManager.this_over_sources` (`eyes/this_over.py:87`) | `list[str]` | **YES** — paired with each token append | by over_mgr internally; logged at `_after_this_over` DETAIL (`test_pipeline.py:7449-7452`) | over_mgr internal pairing |
| `ThisOverManager.over_history` (`eyes/this_over.py:88`) | `dict[int, dict]` | **YES** — `check_over_change` archive (~L1076), `_append_to_held_and_rearchive` (~L382) | **Path A reads it** as `over_history` map (`test_pipeline.py:4214-4216`) | dict-of-dict shape; differs from SM's dict-of-list shape |
| `ThisOverManager._pending_clear`, `_pending_clear_at`, `_pending_clear_over_int` | bool / float / int | **YES** — `check_over_change` (rollover), `_consume_pending_clear` | over_mgr internally (hold-window logic) | **transactional state** — see §2.B |
| `ThisOverManager._held_over_bowler`, `_current_over_bowler` | str / str | **YES** — `on_ball_event`, `check_over_change`, `_consume_pending_clear` | over_mgr internally (FIRST-WRITE-WINS bowler attribution) | bowler-attribution coupling |
| `ThisOverManager._last_over_int`, `_over_start_score`, `_last_ball_event` | int / int / dict | **YES** — `on_ball_event`, `check_over_change`, `resync_to_over` | over_mgr internally (cursor + reconcile) | cursor / reconcile state |
| `ThisOverManager._last_mutation_score`, `_last_mutation_overs` | int / str | **YES** — `on_ball_event` | over_mgr internally (SCORE-GATED MUTATION GUARD) | gating state on broadcast accepts |
| `ThisOverManager._rollover_defer_count` | int | **YES** — `check_over_change` | over_mgr internally (short-over rollover defer, `ROLLOVER_MAX_DEFER_FRAMES`) | rollover defer state |
| `Scoreboard.this_over` (`eyes/scoreboard.py:235`) | `list[str]` | **NO on the live path.** Initialized to `[]`, cleared in `_handle_innings_change` (L595) and `set_innings_2` (L3447). The methods that write it (`update_this_over`, `on_new_over`, `initialize_this_over`) are **only called by `test_offline.py:197`** — not by the live pipeline. | `Scoreboard.get_state` (L3628), `Scoreboard.format_*` snapshot (L3880), and `record_extra` log line (L3972). Never reaches Path A WS payload. | **DEAD on the live path** — see §2.A |
| `Scoreboard.over_history` (`eyes/scoreboard.py:236`) | `dict[int, list[str]]` | **NO on the live path.** Same writers as `Scoreboard.this_over` (only `test_offline.py`). | `Scoreboard.get_state` (L3628), snapshot (L3880). Not Path A. | **DEAD on the live path** |

**Corrected source count for the live `this_over` UI surface: TWO writers (over_mgr authoritative; SM internal mirror), not three.** The "third source" (`Scoreboard.this_over` / `Scoreboard.over_history`) is **dead code on the live path** — its methods are only invoked from `test_offline.py`. Item 5's claim of "3 sources" reflects the field declarations, not the live writers. **Path A reads exclusively from `over_mgr` for `this_over` and `over_history`.** SM contributes `completed_over` / `completed_over_runs` only.

### 0.2 `partnership_*` surface — actual writers and readers (live path)

| Component | Field | Live writes? | Live reads? | Notes |
|---|---|:---:|:---:|---|
| `ScoreManager.partnership_runs` (`score_manager.py:152`) | `int` | **YES** — `_apply_event` wicket reset (L2558), legal-ball accumulator (L2566), `_accept_initial` (L1392), `_clear_per_innings_sm_surface` (L749) | SM `_build_payload` (L2781). **Not** read by Path A WS payload. | SM-internal computation |
| `ScoreManager.partnership_balls` (`score_manager.py:153`) | `int` | **YES** — same sites as `partnership_runs` | SM `_build_payload` (L2783) | same |
| `ScoreManager.partnership_known` (`score_manager.py:154`) | `bool` | **YES** — `_apply_event` reset/legal (L2560, L2562, L2565), `_accept_initial` (L1394), `_clear_per_innings_sm_surface` (L751) | SM `_build_payload` gates `runs`/`balls` to `None` on `False` (L2782, L2784) | "is the partnership counter trustworthy?" gate; true after a wicket-reset, false during mid-innings recovery until first observed legal ball |
| `PartnershipTracker.current_pair` (`eyes/commentary.py:734`) | `set[str]` | **YES** — `update` (L771–L799), `reset` (L747), `override` (no, override only rebases anchor) | `_build_full_payload_from_state` reads via `partnership_tracker.current_pair` to decide whether to anchor (`test_pipeline.py:4018, 4047`) | live canonical pair |
| `PartnershipTracker.partnership_start_score` (`eyes/commentary.py:735`) | `int` | **YES** — `update` (L788/L791), `reset` (L748), `override` (L815) | `current()` (L827), Path A via `partnership_tracker.current(...)` (`test_pipeline.py:4048, 9679`) | anchor (back-datable via `initial_guess_runs`) |
| `PartnershipTracker.partnership_start_balls` (`eyes/commentary.py:736`) | `int` | **YES** — same | same | anchor balls |
| `PartnershipTracker.partnerships` (`eyes/commentary.py:737`) | `list[dict]` | **YES** — `update` appends (L779) when current pair changes; `reset` clears (L750) | end-of-match log (`test_pipeline.py:10067-10070`); not in WS payload | completed-partnership archive |
| `Scoreboard.current_partnership` (`eyes/scoreboard.py:213`) | `dict \| None` | **NO on the live path.** Only assigned to `None` at `__init__` (L213), `setup_innings` (L605), and `_handle_innings_change` (L3506). **Never written with actual partnership data anywhere in the codebase.** | Not read on the live path. | **DEAD field** — see §2.A |
| `Scoreboard.partnerships` (`eyes/scoreboard.py:212`) | `list[dict]` | **NO on the live path.** Same: only ever cleared. | end-of-match summary may iterate (`test_pipeline.py:10067` reads `partnership_tracker.partnerships`, **not** `scoreboard.partnerships`). | **DEAD field** |

**Corrected source count for the live `partnership` UI surface: TWO writers — `PartnershipTracker` (authoritative for the WS payload) and `ScoreManager` (internal mirror that never reaches the WS payload).** `Scoreboard.current_partnership` and `Scoreboard.partnerships` are **dead fields on the live path**. Item 5's claim of "3 sources" reflects the declared fields, not the live writers. **Path A reads partnership exclusively from `PartnershipTracker.current(...)`.**

### 0.3 The architectural pattern is the same for both surfaces

Both surfaces share the same shape, which is the most important structural observation in this audit:

```
┌─────────────────────────┐                     ┌─────────────────────────┐
│ external manager        │  AUTHORITATIVE      │ ScoreManager mirror     │
│ (over_mgr / PT)         │  for WS payload     │ (SM.this_over /         │
│ rich semantics:         │  via Path A         │  SM.partnership_*)      │
│ holds, late events,     │  ────────────────►  │ derived from event      │
│ FOW reorder, score-     │                     │ stream; ends in         │
│ gated mutation,         │                     │ SM._build_payload only  │
│ first-write-wins...     │                     │ (no WS consumer)        │
└─────────────────────────┘                     └─────────────────────────┘
            ▲                                              ▲
            │ writes from                                  │ writes from
            │ test_pipeline main loop                      │ score_mgr.on_frame
            │ (BED events, broadcast strip,                │ (event-derived in
            │  resync triggers, FOW upgrade)               │  _apply_event)
            │                                              │
            └────────────── Both consumed at ──────────────┘
                          test_pipeline.py main loop
                          for Path A WS payload assembly:
                          - this_over/over_history ← over_mgr.get_display() / over_mgr.over_history
                          - completed_over/runs    ← SM.completed_over / SM.completed_over_runs
                          - partnerships.current   ← PartnershipTracker.current()

┌─────────────────────────┐
│ Scoreboard.{this_over,  │
│ over_history,           │
│ current_partnership,    │
│ partnerships}           │
│ DEAD on the live path   │  ← only test_offline.py / declarations
│ — never reaches the UI  │
└─────────────────────────┘
```

This pattern materially changes the migration question. **The live divergence surface is between SM-internal mirrors and external managers, not between SM and Scoreboard.** Path B's `[SM-FEEDER-SYNC]` pattern was about SM ↔ SB lockstep; Path C is about whether SM-internal mirrors of external-manager state should exist at all.

---

## 1. `this_over` surface

### §A: Field inventory

The full inventory is in §0.1. Summary table for migration decision:

| # | Field | Owner | Path A reads it? | Live writes site count | Coupling cluster |
|---|---|---|:---:|---:|---|
| TO-1 | `SM.this_over` | SM | **NO** (only SM `_build_payload`, not WS) | 6 | SM-internal mirror |
| TO-2 | `SM.this_over_src` | SM | **NO** | 6 (paired w/ TO-1) | SM-internal mirror |
| TO-3 | `SM.over_history` | SM | **NO** (only SM `_build_payload`; SM `set_innings_2` archive) | 4 | SM-internal mirror |
| TO-4 | `SM.completed_over` | SM | **YES** (Path A fallback for held-over display) | 2 | SM-derived; WS-relevant |
| TO-5 | `SM.completed_over_runs` | SM | **YES** | 2 | paired with TO-4 |
| TO-6 | `SM.this_over_extras` | SM | **NO** (Path A reads `scoreboard.extras["this_over"]` via Item 3 property; SM-side reset hooks at L2387, L2586) | 4 | counter; not in WS via SM |
| TO-7 | `over_mgr.this_over` | over_mgr | **YES** (`get_display(overs)`) | many (`on_ball_event`, `on_broadcast_override`, `check_over_change`, `pop_last_extra`, `reorder_wicket_to_ball`, `resync_to_over`, `reset`) | **CANONICAL** for WS |
| TO-8 | `over_mgr.this_over_sources` | over_mgr | **NO** (DETAIL log only) | many (paired w/ TO-7) | paired source tracker |
| TO-9 | `over_mgr.over_history` | over_mgr | **YES** | 2 (archive + held re-archive) | dict-of-dict; richer shape |
| TO-10 | `over_mgr._pending_clear` (+`_at`+`_over_int`) | over_mgr | **NO** (gates over_mgr's own behaviour) | many | hold-window state |
| TO-11 | `over_mgr._held_over_bowler` / `_current_over_bowler` | over_mgr | **NO** | many | bowler-attribution coupling |
| TO-12 | `over_mgr._last_over_int` / `_over_start_score` / `_last_ball_event` | over_mgr | **NO** | many | cursor + reconcile |
| TO-13 | `over_mgr._last_mutation_score` / `_last_mutation_overs` | over_mgr | **NO** | many | broadcast-accept gating |
| TO-14 | `over_mgr._rollover_defer_count` | over_mgr | **NO** | many | rollover defer counter |
| TO-15 | `SB.this_over` | SB | **NO** (read by `SB.get_state` / snapshot only) | **DEAD on live path** | — |
| TO-16 | `SB.over_history` | SB | **NO** (read by `SB.get_state` / snapshot only) | **DEAD on live path** | — |

**Cross-reference table: writes vs payload contribution**

| WS payload key | Source on every WS frame | Fallback | Notes |
|---|---|---|---|
| `this_over` | `over_mgr.get_display(scoreboard._inn["overs"])` | `list(score_mgr.completed_over)` if over_mgr's display is empty | `_build_full_payload_from_state` L4183-4192 |
| `over_history` | `{str(k): v for k, v in over_mgr.over_history.items()}` | none — over_mgr-only | L4214-4216 |
| `completed_over` | `score_mgr.completed_over` | none — SM-only sticky | L4205-4208 |
| `completed_over_runs` | `score_mgr.completed_over_runs` | none — SM-only | L4209-4212 |

`over_mgr` owns the live ribbon; SM contributes the sticky completed-over snapshot that bridges the boundary frame. **Both fields are needed** to render the UI without flicker — the dual ownership is intentional, not accidental, and predates Path A. The Path A comment block at L4147-4170 documents the choice explicitly.

### §B: State coupling analysis

#### Transactional coupling (must update together — atomic write semantics required)

Within `over_mgr` (already enforced by the class): every `this_over.append(token)` is paired with `this_over_sources.append(source)`. Every `pop_last_extra` is paired with the matching `this_over_sources.pop`. Every `_consume_pending_clear` clears `(_pending_clear, _pending_clear_at, _pending_clear_over_int, _held_over_bowler)` together. The class is a transactional unit.

Within SM: `_apply_event` writes to `(this_over, this_over_src)`, sometimes also `(completed_over, completed_over_runs, over_history[k])`, plus the per-event `(this_over_extras` increment via `_extras_writable()["this_over"]`). The over-rollover branch writes **all of these** in a single straight-line code block (`score_manager.py:2375-2389`). No `await` in between — atomic at the bytecode level.

**Cross-component coupling (the migration-relevant form):** there is **no atomic invariant** that requires `over_mgr.this_over` and `SM.this_over` to match at the same frame. They are written independently:
- `over_mgr.this_over` is written by the test_pipeline main loop after BED produces a `ball_event` (`test_pipeline.py:9016` `over_mgr.on_ball_event(...)`) and after `over_mgr.check_over_change(...)` archives a completed over (`:9274`).
- `SM.this_over` is written by `score_mgr.on_frame(_sm_frame)` (`:9472`) which calls `_handle_warm` → `_apply_event` and decides on its own (delta-derived) which event to apply.

These two paths can disagree by 1–2 frames (the comment block at `test_pipeline.py:4147-4170` is exactly about this). The **correctness contract is at the boundary**: only `over_mgr` flows to the UI; SM contributes only `completed_over`/`runs`.

#### Computed coupling (derived from other fields)

Inside `over_mgr`:
- `over_history[N]["balls"]` is a snapshot of `this_over` at archive time (`check_over_change` L1061; `_append_to_held_and_rearchive` L375).
- `over_history[N]["runs"]` is computed from `this_over` digit tokens (L1063); `["wickets"]` from `W` tokens (L1065).
- `_pending_clear_over_int` is set to `_last_over_int` at archive time (L1088).
- `_held_over_bowler` is set to the just-bowled bowler (L1094) — derived from the cached `_current_over_bowler`/passed `bowler`/`_last_ball_event`.
- `get_display(overs)` returns `this_over` padded with `?` placeholders to match `round((overs % 1) * 10)` legal balls (the `[FLOOR]` log path).

Inside SM:
- `completed_over` ← `list(self.this_over)` at over rollover (L2377, L2575).
- `completed_over_runs` ← `sum(int(t) for t in self.this_over if t.isdigit())` at over rollover (L2378, L2576).
- `over_history[int(prev.overs)]` ← `list(self.this_over)` (L2380, L2578).

**Cross-component computation:** none. SM does not derive from `over_mgr` and vice versa; they re-derive from the same upstream events.

#### Lifecycle coupling (cache-invalidate together)

| Lifecycle event | over_mgr action | SM action | Coupled? |
|---|---|---|---|
| Innings 2 transition | `over_mgr.reset()` called from `_innings_reset_done_for` set bookkeeping in `test_pipeline.py:5002` | `score_mgr.set_innings_2()` re-`__init__`s SM (`score_manager.py:1762`) — wipes `this_over`, `over_history`, `completed_over`, `completed_over_runs` | **Independent calls, both required.** Currently coupled at `test_pipeline.py:_innings_reset_done_for` book-keeping; missing one would leak state |
| Mid-innings recovery (SM `COLD_START` → `WARM` after recovery) | `over_mgr.resync_to_over(score_mgr.overs, reason="score_manager_mid_innings_recovery")` (`test_pipeline.py:9477-9479`) | `_accept_initial` re-entry path preserves observed `this_over` (`score_manager.py:1380-1389`); `partnership_*` preserves on re-entry | **Coupled at the trigger** (SM cold→warm transition) |
| `full_reset` (POISON-RECAL) | **NO action on over_mgr.** `full_reset` calls `_clear_per_innings_sm_surface` which resets SM-side `this_over=[]`, `over_history={}`, `completed_over=None`, `completed_over_runs=None` (`score_manager.py:743-747`); does **not** call `over_mgr.reset()`. | wipes SM-internal mirrors | **NOT coupled.** `over_mgr` retains its state across `full_reset`. This is consistent with the `full_reset` design (it is per-SM-innings nuclear; over_mgr is reset only on innings 2 or via explicit `resync_to_over`). |
| `set_innings_2` archive | `over_mgr` not archived | SM archives `over_history` into `innings_history` entry (`score_manager.py:1750`) | **Independent.** `over_mgr.over_history` is observable post-innings-2 only via the dict reference (no archive) |

#### Cross-frame dependencies (does frame N+1 depend on frame N's state?)

- **`over_mgr` heavily.** `_pending_clear`, `_pending_clear_at`, `_held_over_bowler`, `_last_over_int`, `_last_mutation_score`, `_rollover_defer_count`, `_current_over_bowler`, `_last_ball_event` all carry across frames. The hold-window timer (`COMPLETED_OVER_HOLD_S=3.0`) is wall-clock based via `time.monotonic()`. Late-event handling, rollover defer (up to `ROLLOVER_MAX_DEFER_FRAMES=2`), score-gated mutation, and FOW reorder all depend on cross-frame state.
- **`SM` lightly.** `this_over` accumulates legal-ball tokens across frames; `completed_over` is sticky until the next rollover; `partnership_*` accumulates. No timer dependency.

**Path A WS payload assembly itself is stateless** with respect to this_over: it reads the snapshot at each frame.

### §C: Collection semantics

| Field | Type | Semantics | Special access patterns |
|---|---|---|---|
| `over_mgr.this_over` | `list[str]` | append-only on legal ball / extra; pop-only via `pop_last_extra` (extras only) and `WICKET_LATE`/`DRS_WIDE` (last-position upgrade); positional rewrite via `reorder_wicket_to_ball` (`reorder` is the **only** non-tail mutation) | index-based read (UI renders position-indexed); position-based write via `reorder_wicket_to_ball` |
| `over_mgr.this_over_sources` | `list[str]` | parallel to `this_over` (1:1 by index); `"obs"` for ball events, `"bcast"` for broadcast fills | index-paired with `this_over` |
| `over_mgr.over_history` | `dict[int, dict]` | append-only per key (FIRST-WRITE-WINS at L1054-1076); single sanctioned in-place mutation in `_append_to_held_and_rearchive` (L382) | int over-number key; dict value with `balls`/`bowler`/`runs`/`wickets` |
| `SM.this_over` | `list[str]` | append on event; clear on over rollover or MULTI_BALL | tail-only |
| `SM.this_over_src` | `list[str]` | parallel to `SM.this_over` | index-paired |
| `SM.over_history` | `dict[int, list]` | write-and-overwrite at over rollover (no immutability check) | int key; list value (different shape from over_mgr) |
| `SM.completed_over` | `list[str]` | snapshot of `SM.this_over` at over rollover; sticky until next rollover | sticky-snapshot |
| `SM.completed_over_runs` | `int` | derived from `SM.this_over` digit tokens at rollover | scalar |

**Critical asymmetry:** `over_mgr.over_history[N]` is a **dict** with `balls`/`bowler`/`runs`/`wickets`; `SM.over_history[N]` is a **list** of tokens. **Path A reads from `over_mgr.over_history` only**, so the shape consumers see is the dict. The list shape inside SM is dead with respect to the WS payload — it is only emitted from `SM._build_payload`, which is not consumed by Path A. This was the latent symptom of the historical "stuffing" bug (backlog #10 entry, `dual-broadcaster shape collision`); the Path A cutover (2026-04-27) **already resolved the WS-side symptom** by routing exclusively through `over_mgr`.

### §D: Migration shape categorization

Per the audit's classification taxonomy:

| Field | Category | Reasoning |
|---|---|---|
| TO-1 `SM.this_over` | **PATH-C-CANONICAL-OWNER** (over_mgr is the owner; SM read-through if needed; SM internal write removable) | Not read by Path A. `over_mgr` is canonical. Two preservation needs exist: (a) `_build_payload` (SM emits its own payload that goes nowhere on the live path — but SM tests still consume it); (b) `set_innings_2` archive into `innings_history`. Both can be satisfied by either (i) read-through property to `over_mgr.this_over` (requires SM to know about over_mgr; backref needed) or (ii) keep SM internal mirror but stop writing the divergent over-history shape. |
| TO-2 `SM.this_over_src` | **PATH-C-CANONICAL-OWNER** | Same as TO-1 — pair semantics |
| TO-3 `SM.over_history` | **PATH-C-CANONICAL-OWNER** (over_mgr is owner). Concretely: SM stops writing `over_history`, reads through to `over_mgr.over_history` projected to list-of-tokens shape if SM still needs the list shape for `set_innings_2` archive. | Same shape collision as backlog (10) noted; the dict shape is the canonical one, and the list shape on SM is divergent. Already resolved at the WS edge by Path A; Path C closes the SM-side write. |
| TO-4 `SM.completed_over` | **PATH-B-FEEDER (in spirit) but stays SM-owned** | This **is** a WS-relevant field, and it is an SM-derived sticky snapshot (over_mgr does not have a "completed_over sticky" concept). The Path A comment block at L4147-4170 explains this is intentional — SM bridges the over-rollover boundary frame. **No migration recommended.** |
| TO-5 `SM.completed_over_runs` | **PATH-B-FEEDER (stays SM-owned)** | Paired with TO-4. Stays as-is. |
| TO-6 `SM.this_over_extras` | **PATH-B-FEEDER (already migrated by Item 3)** | The Item 3 LOW-risk batch already turned `this_over_extras` into a property reading `SB.extras["this_over"]` (`score_manager.py:259-264`). Already shipped. **No work for Path C.** |
| TO-7 `over_mgr.this_over` | **CANONICAL — leave as-is** | Already authoritative for WS. No migration. |
| TO-8 `over_mgr.this_over_sources` | **CANONICAL — leave as-is** | Same |
| TO-9 `over_mgr.over_history` | **CANONICAL — leave as-is** | Already authoritative for WS |
| TO-10 — TO-14 (over_mgr internal cursor / hold / mutation-gate / defer state) | **CANONICAL — leave as-is** | Internal state of the canonical owner; no parallel exists |
| TO-15 `SB.this_over` | **REMOVABLE (dead on live path) but DEFER** | `update_this_over`, `on_new_over`, `initialize_this_over`, `get_this_over_runs`, `get_this_over_for_display` are only called by `test_offline.py:197`. Removing them from `Scoreboard` is a separate cleanup with `test_offline.py` test surface (out of Path C dual-broadcaster scope). |
| TO-16 `SB.over_history` | **REMOVABLE (dead on live path) but DEFER** | Same |

### §E: Migration approach

#### Recommended pattern for `this_over` surface

**`PATH-C-CANONICAL-OWNER` with `over_mgr` as the owner**, executed in the smallest possible PR:

1. **Stop writing `SM.this_over`, `SM.this_over_src`, `SM.over_history` in `_apply_event`.** Replace the writes (~L2360-2392) with a call to a helper that emits a no-op (or asserts the over_mgr-side write happened). Per-event tokens are constructed by SM (`event.get("this_over_token")`) but the actual append happens in `over_mgr.on_ball_event` driven by the test_pipeline main loop after BED produces an event. SM's internal mirror is redundant.
2. **Convert `SM.this_over` to a `@property` that reads `over_mgr.this_over` via a `score_mgr.over_mgr` back-reference** (or returns `[]` when no back-reference is set, mirroring the Item 3 fallback shape).
3. **Convert `SM.over_history` to a `@property` that reads `over_mgr.over_history`** projected to the list shape if SM consumers (e.g. `set_innings_2` archive) require list-of-tokens. The projection is `[d["balls"] for d in over_mgr.over_history.values()]` → reshape to `{k: d["balls"] for k, d in over_mgr.over_history.items()}` to preserve SM's dict-of-list contract.
4. **Keep `SM.completed_over` and `SM.completed_over_runs` SM-owned and SM-written** — they bridge the over-rollover boundary frame in a way over_mgr does not (over_mgr has `_pending_clear` / hold-window, but `get_display(overs)` does not synthesise the just-completed over for the *next over's* idle frames — Path A relies on SM's sticky `completed_over` for that).
5. **Add `[SM-OVER-HISTORY-DIVERGENCE]` telemetry** at any path where SM consumers would otherwise see a divergence between the new (read-through) and old (SM-internal) view of `over_history`. Pattern mirrors `[SM-FEEDER-DIVERGENCE]` from Item 3 — sig-rate-limited.
6. **No change to `over_mgr` itself.** It is canonical; the migration only removes the SM-internal mirror.

**Per-field migration spec**

| Field | Migration | Risk |
|---|---|---|
| `SM.this_over` | `@property` reading `self.over_mgr.this_over` if `self.over_mgr is not None` else `self._this_over_internal` (default `[]`) | LOW — reads only flow into `_build_payload` and the SM-internal copy; `_apply_event` writes are removable (currently re-derive from event token, no logic depends on the SM list except SM tests) |
| `SM.this_over_src` | Same property pattern reading `over_mgr.this_over_sources` | LOW |
| `SM.over_history` | `@property` projecting `over_mgr.over_history` to dict-of-list (`{k: d.get("balls", []) for k, d in over_mgr.over_history.items()}`) | LOW |
| `SM.completed_over`, `SM.completed_over_runs` | **NO CHANGE** — sticky bridge stays SM-owned | n/a |
| `SM._apply_event` over-rollover branch | Drop the `self.over_history[int(prev.overs)] = list(self.this_over)` write (L2380); drop the `self.this_over = []`/`this_over_src = []` resets (L2363-2364, L2388-2389, L2391-2392) — `over_mgr.check_over_change` already handles its own clear; SM event-token append at L2375/L2391 becomes a write to a thin SM-internal `_this_over_internal` for tests, or removed if no test relies on SM's mirror | LOW once tests audit shows no behavioural reliance |
| `SM.full_reset` / `_clear_per_innings_sm_surface` | Stop wiping `this_over`/`over_history`/`completed_over*` if they become read-through; **must keep** `completed_over*` clear (still SM-owned) | LOW |

**Risk assessment per migration option**

| Option | Risk | Reversibility |
|---|---|---|
| Property-backed read-through (recommended) | **LOW** — Path A WS payload is already over_mgr-sourced; SM's mirror was internal-only. Test fixtures that read `sm.this_over` after a frame must work either via the back-reference or via the `_this_over_internal` fallback | TRIVIAL — restore the `__init__` field, restore the writes |
| Wholesale removal of SM fields | **MEDIUM** — would break `score_mgr._build_payload` (still emits `this_over`/`over_history`), would break `set_innings_2` archive, would break `test_recent_fixes.py` tests that read `sm.this_over` | reversible via git but more diff |
| Leave-as-is + telemetry only | **VERY LOW** | trivially reversible |

#### Recommended pattern for `partnership_*` surface

**INFEASIBLE for full migration; PATH-B-FEEDER pattern works for the divergence-detection telemetry; SM-internal computation should stay** — see §D below for `partnership_*`. Reasoning: SM's `partnership_runs/balls/known` is computed from event-stream deltas (pure derived state, not a redundant copy of an external owner). `PartnershipTracker` is computed from `(team_score, team_balls, active_batters)` deltas — an entirely different derivation method (anchor + delta vs running accumulator). Both are valid; both can disagree by frame timing. Migration would either (a) make SM compute from PT (reverse direction; PT doesn't expose `partnership_known`-style "is anchor real?" gate), or (b) make PT compute from SM (would lose PT's broadcast-override capability and per-active-pair bookkeeping).

**Recommended Path C action: telemetry-only.** Add `[SM-PARTNERSHIP-DIVERGENCE]` log when `(SM.partnership_runs, SM.partnership_balls)` differs from `PartnershipTracker.current(team_score, team_balls)`'s `(runs, balls)` for the same active pair, signature-rate-limited like `[SM-FEEDER-DIVERGENCE]`. **No SM-side mutation.**

(See §2 below for the `partnership_*` surface specifics.)

### §F: Production impact prediction (for `this_over`)

**Telemetry implications:**

- **Existing tags affected:** none. `[SM-FEEDER-SYNC]` (Item 3) does not currently fire for `this_over`; we are not retroactively classifying `this_over` as a feeder field.
- **New tag:** `[SM-OVER-HISTORY-DIVERGENCE]` (signature-rate-limited; emits when the SM read-through sees a value different from the prior frame's snapshot). Useful for catching code paths that still write the SM-internal mirror after migration.
- `[OVER-RESYNC]` (existing, `eyes/this_over.py:171`) — unchanged; still fires when `resync_to_over` runs.
- `[FLOOR]` (existing, `eyes/this_over.py:1201`) — unchanged.
- `[ROLLBACK]`, `[OVER-DEFER]`, `[FOW-REORDER]`, `[ARCHIVE]`, `[THIS-OVER]` (existing) — unchanged.

**Observable rate impacts (production):**

- **`[WS-SLOT-INVARIANT]` rate:** **0% impact.** This invariant fires only on striker == non_striker (`test_pipeline.py:2230`); `this_over` plays no role in slot invariants. Lever 1 PR2 is the relevant lever for that rate.
- **WS payload byte-identity (Path A snapshot):** **0% impact** if recommended migration (§E option 1) preserves the read-through shape. The Path A snapshot baseline (`files/path_a_ws_payload_baseline.txt`) reads `this_over` and `over_history` from `over_mgr` — the SM-side migration does not touch the read source.
- **UI flicker between ribbon shapes:** **already addressed** by Path A 2026-04-27 cutover (backlog (10) entry). Path C closes the SM-side leak that caused the historical "stuffing" pattern, but the live-visible symptom is gone.
- **Architectural cleanup benefit:** removes a dual-writer surface that re-occurred in three historical bug classes (substrate audit §3 row 11, backlog (10), `dual-broadcaster shape collision`). Future-proof against regression.

**Cross-reference to PBKS-vs-RR production data:**

- Searched backlog for `[WS-SLOT-INVARIANT]` traces back to `this_over`: **none found**. The 387/26 fires (per Lever 1 design §3.2) all trace to slot-write sites (W1–W12), none to `this_over`.
- Backlog item (10) (`over_history dual-writer over-key/shape collision`) is **SHIPPED-pending-validation by Path A** (2026-04-27); Path C is an architectural follow-up, not a live-bug fix.
- Backlog items (11) (`this_over cold-start placeholder downgrade`), (21) (`this-over rollover cursor stuck after recovery`), (5) `Fix 2 token-alphabet validation` — **all live in `eyes/this_over.py`**; Path C does not change over_mgr.
- No pending live-validation backlog item depends on Path C migration of `SM.this_over`.

**Headline:** Path C `this_over` migration is **architectural-cleanup-grade**, not rate-reducing. The WS-visible symptom was already cured by Path A 2026-04-27; what remains is to close the SM-side dual-writer field.

### §G: Migration order (within `this_over` surface)

If the SM-side migration is undertaken, the order is mechanical:

1. Add `over_mgr` back-reference to SM (or accept passing `over_mgr` into SM at construction time; `score_mgr.scoreboard` precedent exists).
2. Convert `SM.this_over` and `SM.this_over_src` to read-through properties.
3. Convert `SM.over_history` to a projecting property.
4. Drop the `_apply_event` writes for the three fields above; keep `completed_over` / `completed_over_runs` writes intact.
5. Add `[SM-OVER-HISTORY-DIVERGENCE]` telemetry as a backstop.
6. Test fixtures: audit `test_recent_fixes.py` for any `sm.this_over` / `sm.over_history` write/read after `_apply_event`; many fixtures construct SM in shadow mode and may not have an `over_mgr` attached. Either attach one (preferred) or accept the `[]` fallback semantics.

**No coupling with `partnership_*` migration order** — the surfaces are independent at the migration level.

---

## 2. `partnership_*` surface

### §A: Field inventory

(Full inventory in §0.2; restated for the section structure.)

| # | Field | Owner | Path A reads it? | Live writes site count | Coupling cluster |
|---|---|---|:---:|---:|---|
| PT-1 | `SM.partnership_runs` | SM | **NO** (only SM `_build_payload`) | 4 | SM-internal accumulator |
| PT-2 | `SM.partnership_balls` | SM | **NO** | 4 (paired w/ PT-1) | SM-internal accumulator |
| PT-3 | `SM.partnership_known` | SM | **NO** (gates SM emission to `None`) | 4 | "is the counter trustworthy?" gate |
| PT-4 | `PartnershipTracker.current_pair` | PT | **YES** (read via `current_pair` truthiness check at `:4018, 4047`) | 2 (`update`, `reset`) | active-pair set |
| PT-5 | `PartnershipTracker.partnership_start_score` | PT | **YES** (via `current(team_score, team_balls)` at `:4048, 9679`) | 4 (`update` × 2 paths, `reset`, `override`) | anchor (back-datable) |
| PT-6 | `PartnershipTracker.partnership_start_balls` | PT | **YES** (same call) | 4 | anchor balls |
| PT-7 | `PartnershipTracker.partnerships` (list) | PT | **NO** (read only at end-of-match log `:10067`) | 2 (`update` append, `reset`) | completed-partnership archive |
| PT-8 | `SB.current_partnership` | SB | **NO** | **DEAD on live path** | — |
| PT-9 | `SB.partnerships` | SB | **NO** | **DEAD on live path** | — |

### §B: State coupling analysis

#### Transactional coupling

Within SM `_apply_event` wicket branch (`score_manager.py:2558-2560`): `(partnership_runs, partnership_balls, partnership_known)` reset together to `(0, 0, True)`. Within the legal-ball branch (`:2562-2567`): the `partnership_known` recovery sets all three; the accumulate path (`+= runs`, `+= 1 if legal`) updates the two counters together but does not touch `partnership_known`.

Within PT `update` (`commentary.py:771-799`): when the active pair changes, **all four** of `(partnerships[append], current_pair, partnership_start_score, partnership_start_balls)` update in one transaction.

**Cross-component coupling:** **none enforced**. SM and PT compute partnership independently. They can disagree (this is documented latent in backlog (20)).

#### Computed coupling

- SM's `(runs, balls)` is the running sum from `event.get("runs", 0)` and `event.get("legal", True)` — pure event-stream accumulation since the last reset.
- PT's `runs/balls` returned by `current(team_score, team_balls)` is `(team_score - start_score, team_balls - start_balls)` — anchor-and-delta.
- These derivations **always agree on a steady-state-only path**; they can disagree when:
  - SM resets `partnership_runs=0` on a wicket but PT's anchor was last updated before the wicket.
  - PT receives a `broadcast override` (broadcaster shows literal "P'SHIP X(Y)"); SM has no equivalent.
  - SM is in `partnership_known=False` mid-recovery state; PT's `current_pair` may be empty during the same window (different "I don't know" semantics).

#### Lifecycle coupling

| Lifecycle event | PT action | SM action | Coupled? |
|---|---|---|---|
| Innings 2 transition | `partnership_tracker.reset()` (`test_pipeline.py:5001`) | `set_innings_2()` re-`__init__`s SM → resets `partnership_*` to `(0, 0, True)` | Independent calls, both required |
| Mid-innings recovery | PT remains as-is unless `_active_for_pp` differs and `update()` triggers a re-anchor | `_accept_initial` sets `partnership_known = not mid_innings_boot` (re-entry preserves) | **Both** address the same recovery class but with different semantics: SM via `partnership_known` gate; PT via `current_pair` empty + `initial_guess_runs/balls` back-date |
| `full_reset` (POISON-RECAL) | **NOT touched** by SM `full_reset`; remains as-is | `_clear_per_innings_sm_surface` resets `(runs, balls, known)` to `(0, 0, True)` | **NOT coupled.** PT survives `full_reset` |

#### Cross-frame dependencies

- SM `(partnership_runs, partnership_balls)` accumulate across frames; reset on wicket; depend on the prior-frame value for accumulation.
- PT `partnership_start_score/balls` are sticky across frames; only updated on pair change or override.
- Path A always re-reads `partnership_tracker.current(team_score, team_balls)` per frame — stateless at the read site.

### §C: Collection semantics

| Field | Type | Semantics | Special access |
|---|---|---|---|
| `SM.partnership_runs/balls` | int | scalar accumulator; reset on wicket | scalar |
| `SM.partnership_known` | bool | scalar gate | scalar |
| `PT.current_pair` | `set[str]` | replaced wholesale on pair change | set membership |
| `PT.partnership_start_score/balls` | int | scalar anchor | scalar |
| `PT.partnerships` | `list[dict]` | append-only on pair change; cleared on `reset` | list of dicts |

### §D: Migration shape categorization

| Field | Category | Reasoning |
|---|---|---|
| PT-1 `SM.partnership_runs` | **INFEASIBLE for read-through migration** (also INFEASIBLE for canonical-owner) | Different derivation method from PT (event accumulator vs anchor-and-delta). Replacing SM's value with PT's would change the SM payload semantics (e.g. `partnership_known=False` SM emits `None`; PT has no equivalent gate). Cannot project either way without semantic loss. |
| PT-2 `SM.partnership_balls` | **INFEASIBLE for migration** | Same as PT-1 |
| PT-3 `SM.partnership_known` | **INFEASIBLE for migration** | SM-side concept with no PT analog |
| PT-4 `PT.current_pair` | **CANONICAL — leave as-is** | PT is canonical for the WS partnership |
| PT-5 `PT.partnership_start_score` | **CANONICAL — leave as-is** | Same |
| PT-6 `PT.partnership_start_balls` | **CANONICAL — leave as-is** | Same |
| PT-7 `PT.partnerships` | **CANONICAL — leave as-is** | Per-innings archive; not in WS payload (`test_pipeline.py:10067` end-of-match only) |
| PT-8 `SB.current_partnership` | **REMOVABLE (dead) but DEFER** | Never written. Cleanup is independent of dual-broadcaster work. |
| PT-9 `SB.partnerships` | **REMOVABLE (dead) but DEFER** | Same |

**Observation:** the two computation methods (SM event accumulator, PT anchor-delta) are not "redundant copies" in the Path B sense; they are **independently designed estimators** of the same physical quantity, with different fault models (SM: sensitive to event-detection misses; PT: sensitive to `team_score`/`team_balls` regression). The substrate audit's "PARALLEL (3 sources)" was misleading because it conflated declared-but-dead `SB.current_partnership` with the active dual-estimator pair.

### §E: Migration approach (telemetry-only)

**Recommended pattern for `partnership_*`: `INFEASIBLE` for migration; `PATH-B-FEEDER`-style telemetry only.**

Rationale: the two estimators serve different fault models. Suppressing SM's accumulator in favor of PT's anchor-delta would lose the ability to detect score-side anchor drift (the failure mode that drove backlog (20)'s mid-innings backstage shipped 2026-04-28). Suppressing PT in favor of SM would lose broadcast-override capability (PT's `override(team_score, team_balls, broadcast_runs, broadcast_balls)` from a Cricbuzz / Hotstar literal "P'SHIP X(Y)" overlay; called from `test_pipeline.py:8632`). The two estimators provide cross-checks, not redundancy.

**Recommended PR shape:** add `[SM-PARTNERSHIP-DIVERGENCE]` telemetry that fires when SM and PT disagree on `(runs, balls)` for the same active pair, and ship as a per-PR diagnostic.

**Per-field migration spec (telemetry-only):**

| Field | Action | Risk |
|---|---|---|
| All SM `partnership_*` | **NO CHANGE** | n/a |
| All PT fields | **NO CHANGE** | n/a |
| `_build_full_payload_from_state` | **Add `[SM-PARTNERSHIP-DIVERGENCE]` block** (analogous to `[SM-FEEDER-DIVERGENCE]` for bowler at `:3890-3915`): compare `(score_mgr.partnership_runs, score_mgr.partnership_balls)` vs `partnership_tracker.current(team_score, team_balls)` `(runs, balls)`; emit a sig-rate-limited log when they differ AND `score_mgr.partnership_known is True` AND `partnership_tracker.current_pair` is non-empty | VERY LOW — diagnostic only; no payload byte changes |

**Risk assessment:**

| Option | Risk | Reversibility |
|---|---|---|
| Telemetry-only (recommended) | **VERY LOW** — no behavioural change | trivial |
| Migrate SM → PT | **HIGH** — would lose `partnership_known=None` semantics; would break backlog (20)'s shipped backstage logic | non-trivial; requires re-introducing the `known` gate elsewhere |
| Migrate PT → SM | **HIGH** — would lose broadcast-override (`PT.override`); would break end-of-match partnerships archive | non-trivial |
| Wholesale removal of SM `partnership_*` | **HIGH** — breaks SM `_build_payload` (test consumers); breaks `_clear_per_innings_sm_surface` semantics | non-trivial |

### §F: Production impact prediction (for `partnership_*`)

**Telemetry implications:**

- **New tag:** `[SM-PARTNERSHIP-DIVERGENCE]` — sig-rate-limited divergence log. Mirrors `[SM-FEEDER-DIVERGENCE]` (Item 3 PR for `bowler_name`).
- **Existing tag:** `[PARTNERSHIP]` (`eyes/commentary.py:780, 794, 818`) — unchanged.

**Observable rate impacts:**

- **`[WS-SLOT-INVARIANT]` rate:** **0%.** Disjoint surface.
- **WS payload byte-identity (Path A):** **0%** — telemetry-only PR does not touch payload assembly.
- **Pending backlog item (20)** (mid-innings partnership anchor) — **already shipped 2026-04-28** via SM `partnership_known=False` backstage; no Path C contribution required.

**Cross-reference to PBKS-vs-RR production data:**

- Backlog item (20): `partnership display anchors from zero after mid-innings recovery` — SHIPPED 2026-04-28; PT's `initial_guess_runs/balls` in `update(...)` provides the back-date for cold-start; SM's `partnership_known` provides the gate for `_build_payload` emission.
- No `[WS-SLOT-INVARIANT]` traces to partnership.
- Telemetry-only PR adds **observability**, not behavioural change.

### §G: Migration order (within `partnership_*`)

The recommendation is telemetry-only; there is no per-field migration order. The single telemetry PR is independent of all other Path C work.

---

## 3. Combined recommendations and next steps

### 3.1 Decision points addressed

| Decision point | Resolution |
|---|---|
| Should HIGH-risk surfaces use Path B feeder pattern with extended primitives, or genuinely need different pattern? | **Different pattern: PATH-C-CANONICAL-OWNER for `this_over`; INFEASIBLE-with-telemetry for `partnership_*`.** Path B's read-through fits `this_over` (over_mgr canonical, SM mirror redundant); does **not** fit `partnership_*` (two estimators with disjoint fault models). |
| Are `this_over` and `partnership_*` coupled at architecture level? | **No.** Both relate to current-over context, but their writers, consumers, lifecycle events, and migration shapes are independent. Migration may be done in any order. |
| Path A interaction? | **`this_over` migration: zero-byte impact** if `over_mgr` remains the canonical reader (option 1 in §1.E). Path A snapshot regression test (`test_path_b_low_risk_batch_path_a_regression_signature_match`) covers the byte-identity guard. **`partnership_*` migration: zero-byte impact** (telemetry-only). |
| State recovery interaction? | **`this_over`:** `full_reset` currently wipes SM-side `this_over`/`over_history`/`completed_over*` (`_clear_per_innings_sm_surface` L743-747). Post-migration, the read-through properties make the SM-side wipe a no-op (over_mgr still holds state). **`completed_over*` MUST remain SM-owned and wiped** to preserve POISON-RECAL semantics. **`partnership_*`:** `full_reset` currently wipes SM-side `partnership_runs/balls/known`. Post-PR (telemetry-only), unchanged. |
| Test fixture implications? | **`this_over`:** ~12 tests in `test_recent_fixes.py` construct `ThisOverManager()` directly (id rows 187, 189, 199, 200, 209, 210, 224, 225, 246, 247, 346, 347, etc.); they don't touch SM. SM-side fixtures (~5 tests) read `sm.this_over` after invoking SM directly without an attached over_mgr — these would observe the `[]` fallback or need to attach an over_mgr. **`partnership_*`:** no fixture changes needed (telemetry-only). |
| Audit honesty | **DELIVERED.** `partnership_*` is honestly classified INFEASIBLE for migration; recommendation is telemetry-only. `this_over` is classified PATH-C-CANONICAL-OWNER but the recommendation is explicit that the WS-visible symptom is already cured — the work is architectural cleanup, not rate-reducing. |

### 3.2 Recommended PR shape (if Path C work is undertaken)

| PR | Surface | Scope | LOC est. | Tests | Telemetry | Risk |
|---|---|---|---:|---|---|---|
| **C1** (optional) | `partnership_*` divergence telemetry | Add `[SM-PARTNERSHIP-DIVERGENCE]` block in `_build_full_payload_from_state`; sig-rate-limited via module-level dict (mirror Item 3 `_last_feeder_div_sig`) | +30 | +1 fixture test (no divergence on steady-state; divergence on synthetic mismatch) | new tag | VERY LOW |
| **C2** | `this_over` SM-mirror removal | Convert `SM.this_over`, `SM.this_over_src`, `SM.over_history` to read-through properties; drop the SM-internal writes in `_apply_event` over-rollover branch; keep `SM.completed_over` / `SM.completed_over_runs` SM-owned | +60 / -40 | +2 fixture tests (read-through equivalence; over_mgr-back-ref None fallback). Audit existing `sm.this_over`-touching tests (~5) for breakage | new tag `[SM-OVER-HISTORY-DIVERGENCE]` (sig-rate-limited) | LOW |

**Sequencing:** **C1 first** (lower-risk, isolates the diagnostic), **C2 second** (or skip entirely as architectural cleanup — see 3.3). They are independent.

**Rejected alternatives:**

- Wholesale `SM.this_over` removal: breaks `SM._build_payload` and `set_innings_2` archive; not recommended.
- `partnership_*` consolidation: breaks backlog (20) shipped semantics; not recommended.
- `Scoreboard.this_over` / `SB.over_history` / `SB.current_partnership` / `SB.partnerships` removal: independent dead-code cleanup; out of dual-broadcaster scope; defer to a separate "SB dead-field cleanup" task that addresses the `test_offline.py` callsite for `update_this_over` / `on_new_over`.

### 3.3 Honest "do nothing" alternative

Both surfaces have **zero pending live-validation backlog items requiring Path C migration** (cross-checked §1.F and §2.F). The WS-visible symptoms previously attributable to dual writers (`over_history` "stuffing", partnership mid-innings anchor) are **already shipped fixes** via Path A 2026-04-27 and backlog (20) 2026-04-28 respectively. **Path C work is architectural-cleanup-grade.** It is acceptable to defer indefinitely if no future bug class re-surfaces the dual-writer pattern.

If chosen to defer, document in backlog as: *"Path C `this_over` SM-mirror removal: NOT scheduled; WS-visible symptom already cured by Path A 2026-04-27 cutover. Path C `partnership_*`: NOT scheduled; INFEASIBLE for migration (two estimators with disjoint fault models); telemetry PR available if a future divergence class is observed."*

### 3.4 Stop-and-route-back conditions

The Path C executor (if work is undertaken) should stop and route back if:

- **(a) `over_mgr` ↔ SM coupling needs a back-reference shape change.** Current SM uses `self.scoreboard` as its only injected dep. Adding `self.over_mgr` is the recommended pattern but requires a constructor signature change OR a post-init `attach_over_mgr` method. Decide before writing code.
- **(b) A test in `test_recent_fixes.py` fails on the `[]` fallback when `over_mgr` is not attached.** Audit shows ~5 SM-only tests; expected to pass with the fallback, but verify on a per-test basis.
- **(c) `test_path_b_low_risk_batch_path_a_regression_signature_match` byte snapshot fails.** This would mean the migration leaked into Path A reads — the recommended pattern preserves the over_mgr read-source, so this should be impossible by construction.
- **(d) `[SM-OVER-HISTORY-DIVERGENCE]` fires non-zero in production after C2 ships.** A bypass site exists; route to investigation.
- **(e) `[SM-PARTNERSHIP-DIVERGENCE]` fires at a higher rate than expected** (>1/over per innings). This may indicate a real algorithmic divergence between the two estimators worth investigating, not a Path C migration concern.

---

## 4. Risk-and-test summary

| Risk | Severity | Likelihood (under recommended PRs) | Mitigation |
|---|---|---|---|
| Path A WS payload byte-identity changes | HIGH | LOW | Path A snapshot regression test in CI; recommended PRs preserve `over_mgr` as the canonical reader |
| SM tests break on `sm.this_over` read-through fallback | LOW | MEDIUM | Audit fixtures; attach `over_mgr` where a test expects observed tokens |
| `[SM-OVER-HISTORY-DIVERGENCE]` indicates a missed write site | MEDIUM | LOW | Stop-and-route §3.4(d); enumerate bypass site before next PR |
| `[SM-PARTNERSHIP-DIVERGENCE]` fires high (>1/over) | MEDIUM | MEDIUM-LOW | This is **diagnostic value**, not regression — investigate if observed |
| `full_reset` semantics change (over_mgr not wiped, SM read-through is now a property) | LOW | LOW | `full_reset` still wipes `completed_over*`; over_mgr survival is consistent with current behaviour (only innings 2 and explicit `resync_to_over` reset over_mgr) |
| Behavioural divergence under `MULTI_BALL` rollover | LOW | LOW | Existing test `test_score_manager_boundary_ball_belongs_to_completed_over` covers the SM-side; over_mgr-side tests cover the rollover defer |

---

## 5. Cross-references summary

| Source | Use in this audit |
|---|---|
| `dual_broadcaster_substrate_audit.md` (Item 5) §3 row 11–12 | Origin of HIGH-risk classification; corrected the "3 sources" count to "2 active + 1 dead" for both surfaces |
| `dual_broadcaster_path_b_migration_contract.md` (Item 3) | `[SM-FEEDER-SYNC]` pattern used as analog for new `[SM-OVER-HISTORY-DIVERGENCE]` and `[SM-PARTNERSHIP-DIVERGENCE]` tags |
| `build_full_payload_extraction_design.md` | Path A snapshot baseline `files/path_a_ws_payload_baseline.txt` referenced as the byte-identity guard |
| `get_broadcast_state_path_b_audit.md` (Lever 2) | Precedent for "no migrable work" honest finding pattern (this audit's `partnership_*` INFEASIBLE classification mirrors the same pattern) |
| `sm_rotation_atomicity_design.md` (Lever 1 PR1+PR2) | Disjoint surface (striker/non_striker); confirms `[WS-SLOT-INVARIANT]` is unaffected by Path C |
| `striker_path_b_read_audit.md` (Item 1) | Precedent for the read-side audit producing partial migration with `defer` outcomes per site |
| `full_reset_fow_extras_verification.md` | `full_reset` correctness baseline; this audit confirms `completed_over*` must remain SM-owned to preserve POISON-RECAL semantics |
| `backlog.md` items (10), (11), (20), (21) | Production-symptom anchors; (10) and (20) confirm the WS-visible bugs are already shipped; (11) and (21) live in over_mgr (out of Path C scope) |

---

## Files

- **New:** `files/docs/investigations/dual_broadcaster_path_c_audit.md` (this file).
- **No code changes** in this task. Output feeds Path C decision (C1 telemetry-only PR; C2 architectural-cleanup PR; or defer indefinitely per §3.3).
