# Scout V6e — design (side_on / boundary fielding preservation in bowlers_end STEP-1)

**Date:** 2026-04-30
**Scope:** Prompt-only design. No code changes in this doc; all edits are
specified for Composer 2 paste-execution into `files/shadow_eval/variants.py`.
**Derives from:** V6d (preserves V6d's f941 fix and V6c's closeup remediation).
**Status:** Design candidate. Proceed to Composer 2 implementation only after
reading §9 stop-and-route-back conditions.

---

## §1 Executive summary

V6d (`variants.py:495–532`) extended V6c's bowlers_end STEP-1 example with a
negative discrimination test targeting atmospheric / no-pitch frames (the f941
escalation class). The combined-corpus shadow run (`discriminating_frames_v6c_vs_v6d_combined.md`)
reveals one new V6d regression: **`pbks_rr_f600`** (`powerplay_inn1`, boundary
fielding chase) which V6c correctly classified as `side_on` but V6d majority-votes
`bowlers_end` across all five post-harness runs.

**Root cause (§2):** V6d's negative clause excludes only *atmospheric / no-pitch*
frames; boundary fielding chase shots often have a pitch or readable field geometry
visible, so the exclusion does not fire. The strong bowlers_end first-example attractor
(V4 diagnostic: single example swap → 36/41 emissions) dominates by default. This is
the H1+H3 mechanism documented in `scout_v6d_implementation_audit.md` §4.

**V6e strategy (§3):** Option A — a third negative clause appended to the bowlers_end
STEP-1 example sentence, covering side-on / lateral camera angles where the fielder
runs parallel to the boundary rope or the ball travels laterally across the frame.
Minimal structural change from V6d; preserves the two-clause construction pattern
established by V6d.

**V6e is a single targeted edit (Edit C):** replace `_V6D_BOWLERS_END_EXAMPLE` with
`_V6E_BOWLERS_END_EXAMPLE` in `PROMPT_V6D`. The edit adds one semicolon-delimited
"NOT side-on" clause and a destination label ("those are `side_on`"). All other
V6d text — `_V6D_OTHER_RULEBOOK`, `_V6C_CLOSEUP_EXAMPLE`, the bowlers_end positive
criteria, STEP-1 ordering, JSON schema — is preserved by construction.

**Acceptance summary (§8):** PRIMARY = f600 V6e plurality ≠ `bowlers_end` AND f941
V6e plurality ≠ `bowlers_end` AND f205 V6e plurality = `closeup` AND V6d combined
corpus net accuracy maintained or improved AND V6d combined corpus `bowlers_end`
recall on TPs ≥ V6d recall.

---

## §2 f600 mechanism (V6d limitation)

### 2.1 Frame characterisation

`pbks_rr_f600`, `powerplay_inn1`: a boundary fielding chase shot. The fielder is
near the boundary rope, moving laterally or diagonally away from the infield. The
camera is positioned roughly square or at a third-man / fine-leg angle — not behind
the bowler, not down the pitch.

Combined-corpus ensemble result:
- **V6c majority:** `side_on` (all five runs).
- **V6d majority:** `bowlers_end` (all five runs — post-harness data).

Human label: `side_on` (ground truth from combined corpus adjudication).

### 2.2 Why V6d's negative clause does not fire for f600

V6d bowlers_end STEP-1 example parenthetical (`variants.py:496–498`):

```
camera behind bowler AND pitch extends away toward the far stumps;
NOT atmospheric/crowd/stadium shots without a visible cricket pitch — those are "other"
```

For f600:

1. **"NOT atmospheric/crowd/stadium without a visible cricket pitch"** — this
   clause targets f941-class frames (drone show, stadium lights, fan crowd,
   boundary-board ad). A boundary fielding shot is *none* of these: it is a live
   game field shot. The clause does not fire.

2. **"camera behind bowler AND pitch extends away toward the far stumps"** — a
   square / fine-leg camera showing a fielder near the rope may still reveal
   portions of the pitch in the frame background, or the model may assimilate
   the general cricket field geometry to "pitch extends away." The AND-conjunction
   is not strictly enforced by Scout for ambiguous wide-angle cricket shots
   (V4-diagnostic evidence: the example literal dominates over condition text).

3. **First-example attractor dominance:** with no applicable negative clause and no
   STEP-1 example for `side_on`, Scout defaults to the first STEP-1 example's
   literal pair (`bowlers_end/release`). This is the H3 mechanism from the audit.

### 2.3 Why V6c gets f600 right

V6c tightened the *closeup* example with a "no full pitch receding away" discrimination
gate. The exact mechanism by which V6c routes f600 to `side_on` rather than a STEP-1
attractor is not fully confirmed (no STEP-1 example for `side_on` in either V6c or
V6d). Most likely: V6c's closeup test rejects f600 (fielder in boundary, not face-
dominant); with the closeup gate active, f600 has no STEP-1 anchor and the rulebook's
`side_on` entry ("square / side-on field camera, e.g. third-man or fine-leg angle on
a boundary chase") provides enough pull to land correctly. V6d's expanded negative
clause on bowlers_end does *not* push f600 toward side_on — it is silent on this
frame class — but the same attractor-dominance that causes the V6d regression was
already present in V6c; V6c escaped it through different prompt dynamics.

The safe inference: the f600 regression is V6d-introduced, not V6c-preserved, and
the mechanism is the absence of an explicit bowlers_end exclusion for side-on /
boundary-fielding geometry.

### 2.4 H1 + H3 combined (from audit §4)

- **H1 (design scope gap):** V6d's negative clause covers only the f941 class;
  boundary fielding was never in the target set. Plausibility: **high**.
- **H3 (strong bowlers_end attractor):** STEP-1 Example 1 dominates; side_on has
  no STEP-1 example to compete. Plausibility: **high**, complementary to H1.
- Both mechanisms are simultaneously active for f600. V6e must address H1 directly
  (widen the negative clause to cover the boundary-fielding class) to break the H3
  default pathway.

---

## §3 V6e design strategy (Option A: third negative clause)

### 3.1 Option landscape

Per `scout_v6d_implementation_audit.md` §5:

| Option | Description | Structural change | Risk |
|--------|-------------|-------------------|------|
| **A** | Third negative clause on bowlers_end STEP-1 line | Minimal — extends existing NOT pattern | Line density increases; clause must stay concise |
| B | Tighten side_on rulebook entry with "DISTINCT from bowlers_end" language | Moderate — requires rulebook edit | Rulebook has weak authority vs STEP-1 examples (V4 diagnostic); may not fire |
| C | Add fourth STEP-1 example for side_on | Structural — adds new attractor | V6d design §4.2 explicitly warns against unless A/B gated; unpredictable pull on other frames |

**Selected: Option A.**

Rationale:
- The V4 diagnostic established that STEP-1 examples are the dominant control surface;
  negative clauses within STEP-1 examples have high authority.
- V6d's Edit A pattern (NOT clause + destination label in the first STEP-1 example)
  is confirmed effective for the f941 class. V6e extends the same pattern.
- Option B's rulebook-only edit is a secondary surface; V4 showed rulebook constraints
  are routinely overridden by example attractors. Option B may be included as
  belt-and-suspenders (Edit D, §3.3) but cannot be the primary fix.
- Option C violates the V6d design constraint (§4.2) against a fourth STEP-1 example
  without A/B gating. Not justified for a single-frame targeted fix.

### 3.2 Option A implementation shape

Extend the V6d bowlers_end STEP-1 parenthetical with a second semicolon-delimited
NOT clause targeting side-on / lateral / boundary-tracking camera angles. Structure:

```
camera behind bowler AND pitch extends away toward the far stumps;
NOT atmospheric/crowd/stadium shots without a visible cricket pitch — those are "other";
NOT side-on/lateral camera angles showing fielder running parallel to boundary rope
or chasing ball laterally across frame — those are "side_on"
```

Key design choices:
1. **Semicolon continuity:** the second NOT clause appends to the first with a
   semicolon, preserving the parallel structure. The model sees two named exclusions,
   both with explicit destination labels.
2. **"side-on/lateral":** matches vocabulary already in the side_on rulebook entry
   ("square / side-on field camera") and the V6d audit's description of f600.
3. **"fielder running parallel to boundary rope or chasing ball laterally across
   frame":** concrete visual signatures. "Parallel to boundary rope" directly
   describes boundary-fielding chase geometry. "Laterally across frame" contrasts
   with "away toward the far stumps" (down-the-pitch delivery geometry).
4. **"those are `side_on`":** explicit destination label, mirroring the "those are
   `other`" pattern from the first NOT clause. Prevents the model from landing on a
   different category by default.

### 3.3 Optional Edit D: side_on rulebook tightening

The side_on rulebook entry (`variants.py:90–91`, within PROMPT_V1 lineage):

```
"side_on": square / side-on field camera (e.g. third-man or fine-leg angle on a
boundary chase).
```

Option: append "DISTINCT from bowlers_end (delivery camera down the pitch)" or similar.

**Recommendation: skip Edit D for V6e.** Rationale:
- The rulebook is a weak control surface (V4 diagnostic). Edit C alone, in the
  dominant STEP-1 surface, is the load-bearing fix.
- Adding Edit D risks introducing a new anchor string that may interact with the
  existing `_V6D_OTHER_RULEBOOK` replace chain in non-obvious ways.
- If V6e shadow run shows f600 still `bowlers_end` despite Edit C (stop-condition S2),
  Edit D can be added in a V6f iteration with targeted diagnosis. Do not add
  speculative edits in V6e.

---

## §4 V6e prompt language (paste-ready Python)

### 4.1 V6e Edit C — `_V6E_BOWLERS_END_EXAMPLE`

The V6d anchor (exact bytes from `variants.py:495–502`):

```python
_V6D_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)
```

V6e replacement:

```python
_V6E_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"; "
    "NOT side-on/lateral camera angles showing fielder running "
    "parallel to boundary rope or chasing ball laterally across "
    "frame — those are \"side_on\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)
```

Diff against `_V6D_BOWLERS_END_EXAMPLE`:
- Line 3: `"shots without a visible cricket pitch — those are \"other\"): "` →
  `"shots without a visible cricket pitch — those are \"other\"; "`  
  (semicolon replaces closing parenthesis; `)` deferred to after the new clause)
- Lines 4–6 (new):
  ```python
  "NOT side-on/lateral camera angles showing fielder running "
  "parallel to boundary rope or chasing ball laterally across "
  "frame — those are \"side_on\"): "
  ```
- JSON shape unchanged (`has_strip`, `camera_view`, `frame_phase`, `ball_position`
  values and ordering are byte-identical to V6d and V6c).

Character delta: +118 characters in the parenthetical (comparable to V6d Edit A's
+88 character and V6c closeup tightening's +95 character additions).

### 4.2 Full V6e prompt definition (paste-ready)

Insert immediately after the V6d block (after `variants.py:533`, the closing
`assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6D` line):

```python
# ---------------------------------------------------------------------
# V6e — V6d base + explicit side_on / boundary fielding preservation.
#
# V6d (bowlers_end STEP-1 example tightened with "NOT atmospheric/
# crowd/stadium" discrimination) fixed f941-class atmospheric/no-pitch
# frames but introduced a regression on f600 (boundary fielding chase):
# boundary shots often show cricket field geometry, so V6d's NOT clause
# does not fire; the strong bowlers_end first-example attractor then
# dominates by default (H1+H3 combined, per
# files/docs/investigations/scout_v6d_implementation_audit.md §4).
#
# V6e Edit C ONLY: extend the bowlers_end STEP-1 example with a third
# semicolon-delimited NOT clause targeting side-on / lateral / boundary-
# tracking camera angles, with an explicit "those are side_on" label.
# This mirrors the Option A recommendation in the audit §5 and follows
# the same NOT-clause + destination-label pattern established by V6d.
#
# V6e preserves by construction:
#   - _V6D_OTHER_RULEBOOK (V6d's f941 fix — atmospheric/no-pitch)
#   - _V6C_CLOSEUP_EXAMPLE (V6c's f205/f748 closeup remediation)
#   - bowlers_end positive criteria (delivery camera recall floor)
#   - STEP-1 example count and ordering (unchanged from V6d/V6c/V5)
#   - JSON schema, alias, canon machinery (untouched)
#
# Design: files/docs/investigations/scout_v6e_design.md
# ---------------------------------------------------------------------
_V6E_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"; "
    "NOT side-on/lateral camera angles showing fielder running "
    "parallel to boundary rope or chasing ball laterally across "
    "frame — those are \"side_on\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)

assert _V6D_BOWLERS_END_EXAMPLE in PROMPT_V6D, (
    "V6d bowlers_end example anchor missing in PROMPT_V6D — "
    "re-derive from literal slice at variants.py:495-502")
PROMPT_V6E = PROMPT_V6D.replace(
    _V6D_BOWLERS_END_EXAMPLE,
    _V6E_BOWLERS_END_EXAMPLE,
)
assert PROMPT_V6E != PROMPT_V6D, "V6e edit is a no-op"
assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6E, (
    "V6e must preserve V6c closeup example byte-identically")
assert _V6D_OTHER_RULEBOOK in PROMPT_V6E, (
    "V6e must preserve V6d other rulebook entry")
assert (PROMPT_V6E.count("\"camera_view\": \"bowlers_end\"") ==
        PROMPT_V6D.count("\"camera_view\": \"bowlers_end\"")), (
    "V6e unintentionally changed bowlers_end example count")
```

Then add the VARIANTS entry (inside the `VARIANTS` dict):

```python
"V6e": {"prompt": _unescape(PROMPT_V6E), "alias": ALIAS_REPOINTED},
```

### 4.3 Sentence-level parenthetical comparison

For readability, the complete parenthetical in each generation:

| Version | Parenthetical content |
|---------|-----------------------|
| V5 | `camera behind bowler, pitch extends away` |
| V6d | `camera behind bowler AND pitch extends away toward the far stumps; NOT atmospheric/crowd/stadium shots without a visible cricket pitch — those are "other"` |
| **V6e** | `camera behind bowler AND pitch extends away toward the far stumps; NOT atmospheric/crowd/stadium shots without a visible cricket pitch — those are "other"; NOT side-on/lateral camera angles showing fielder running parallel to boundary rope or chasing ball laterally across frame — those are "side_on"` |

Each NOT clause names its destination class explicitly. The positive AND-criteria
("camera behind bowler AND pitch extends away toward the far stumps") are unchanged
from V6d and provide the delivery-geometry gate for legitimate bowlers_end frames.

---

## §5 Expected V6e behavior (per-frame predictions)

Sources: human label from `scout_corpus_combined_v1.json`; V6c/V6d combined-corpus
ensemble from `discriminating_frames_v6c_vs_v6d_combined.md` and post-harness run
results in `scout_v6d_postharness_rerun_results.md`.

### 5.1 Primary validation frames

| Frame | Human | V6c maj | V6d maj | V6e expected | Mechanism | Confidence |
|-------|-------|---------|---------|--------------|-----------|------------|
| `pbks_rr_f600` | `side_on` | `side_on` | `bowlers_end` | **`side_on`** | Edit C's third NOT clause fires: boundary fielder running parallel to rope is an explicit named exclusion with destination `side_on`. | **High (target fix)** |
| `f941` (atmospheric) | `other` | `bowlers_end` | `other` | **`other`** | V6d's "NOT atmospheric/crowd/stadium" clause preserved verbatim in V6e. No change to this path. | **High (V6d preserved)** |
| `f205` | `side_on` | `closeup` | `closeup` | **`closeup`** | `_V6C_CLOSEUP_EXAMPLE` preserved byte-identically. V6e adds no edit touching this path. | **High (V6c preserved by construction)** |

### 5.2 Secondary validation frames

| Frame | Human | V6c maj | V6d maj | V6e expected | Mechanism | Confidence |
|-------|-------|---------|---------|--------------|-----------|------------|
| `f748` | `side_on` | `closeup` | `bowlers_end` | **`side_on` or `closeup`** | V6d regressed f748 from V6c's closeup; V6e's third NOT clause may route it to `side_on` (boundary/square geometry), or it may remain `closeup` if face-dominance cues persist. Either is an improvement over V6d's `bowlers_end`. | **Medium** |
| `rcb_gt_f1455` | `other` | `graphic` | `other` | **`other`** (V6d preserved) | V6d routes this to `other` via expanded `_V6D_OTHER_RULEBOOK`. V6e preserves `_V6D_OTHER_RULEBOOK` unchanged. | **High (V6d preserved)** |
| `rcb_gt_f937` | `other` | `closeup` | `other` | **`other`** (V6d preserved) | Same as above — `_V6D_OTHER_RULEBOOK` pull preserved. | **High (V6d preserved)** |

### 5.3 Aggregate prediction table (full 7-frame cross-version)

| Frame | Human | V5 | V6c | V6d | V6e expected |
|-------|-------|-----|-----|-----|--------------|
| `f941` | `other` | `bowlers_end` | `bowlers_end` | `other` | `other` (V6d preserved) |
| `f205` | `side_on` | `bowlers_end` | `closeup` | `closeup` | `closeup` (V6c+V6d preserved) |
| `f748` | `side_on` | `bowlers_end` | `closeup` | `bowlers_end` | `side_on` or `closeup` (V6e targeted improvement) |
| `pbks_rr_f600` | `side_on` | n/a | `side_on` | `bowlers_end` | `side_on` (V6e primary target) |
| `rcb_gt_f1455` | `other` | n/a | `graphic` | `other` | `other` (V6d preserved) |
| `rcb_gt_f937` | `other` | n/a | `closeup` | `other` | `other` (V6d preserved) |
| `f942` | `other` | `bowlers_end` | `bowlers_end` | `other` | `other` (V6d preserved) |

### 5.4 Bowlers_end recall floor (combined corpus TPs)

V6d's five post-harness runs show zero bowlers_end TP regressions on the core delivery
frames (f169, f955, f754, f945, f946 from the 41-frame corpus; equivalent TPs in the
combined corpus). V6e's positive criteria ("camera behind bowler AND pitch extends away
toward the far stumps") are unchanged — legitimate deliveries pass the AND-gate and
neither new NOT clause applies (delivery frames are not atmospheric and not square/
boundary-tracking). Recall floor preservation is **by construction**.

---

## §6 Risk assessment

### R1 — Third NOT clause makes STEP-1 line excessively dense

**Mechanism:** V6e bowlers_end STEP-1 parenthetical will be ~3× the V5 baseline
length (V5: 35 chars → V6d: 123 chars → V6e: ~241 chars). Longer parentheticals
may dilute the model's attention toward the positive criteria.

**Mitigation:** The clause is concise and uses the same semicolon-delimited NOT
pattern already established by V6d. Visual feature description ("fielder running
parallel to boundary rope", "ball laterally across frame") is concrete, not abstract.
Accept this risk; if V6e shadow shows attenuated bowlers_end recall on legitimate
delivery frames, shorten the clause in a V6f pass.

**Severity: Low.**

### R2 — V6e over-restricts bowlers_end and pushes legitimate delivery frames to side_on

**Mechanism:** Edit C's "NOT side-on/lateral camera angles" clause could be read
broadly by Scout. An ambiguous wide delivery shot with a square element (e.g., a
batter sweep at a lateral angle) might be excluded from bowlers_end.

**Mitigation:** The clause specifies "fielder running parallel to boundary rope or
chasing ball laterally across frame" — these are fielding-specific visual signatures,
not batting or bowling actions. The positive bowlers_end test ("camera behind bowler
AND pitch extends away") still gates the primary classification. V6e shadow run must
check bowlers_end recall on combined corpus TPs (acceptance criterion P5).

**Severity: Low–Medium.**

### R3 — V6e shifts f748 to side_on from closeup (unexpected direction)

**Mechanism:** f748 is `side_on` by human label but V6c/V6d-combined classified it
as `closeup` (V6c) or `bowlers_end` (V6d). If V6e's Edit C fires for f748 and routes
it to `side_on`, that is actually the human-correct answer — not a regression.

**Note:** This is included only because changing V6c's established closeup-preservation
pattern for f748 triggers P3 concern. However, f748 moving from `bowlers_end` (V6d)
to `side_on` (V6e) is an *improvement* over V6d, even if it differs from V6c's
`closeup`. The acceptance criterion P3 covers f205 (not f748); f748 is secondary (S1).

**Severity: Low (expected upside).**

### R4 — V6e inadvertently weakens the atmospheric/no-pitch exclusion (f941 regression)

**Mechanism:** Edit C modifies the parenthetical sentence that also contains V6d's
atmospheric NOT clause. A structural reparse by the model might weaken the first
NOT clause if the sentence is now too long.

**Mitigation:** The atmospheric clause is unchanged in character — the only difference
is that its closing parenthesis `)` is replaced by a semicolon `;` to allow the
second NOT clause. The first clause ("NOT atmospheric/crowd/stadium shots without a
visible cricket pitch — those are `other`") remains lexically complete at the
semicolon boundary. The model reads each clause as a named exclusion independently.

**Severity: Low.** However, f941 regression is stop-condition S3 — if observed,
halt immediately.

### R5 — V6e does not actually fix f600 (mechanism is deeper than prompt language)

**Mechanism:** If Scout's internal scene representation for `pbks_rr_f600` strongly
resembles its delivery schema despite the lateral camera, the new NOT clause may not
fire even with explicit negative language.

**Mitigation:** None at prompt-only level. If f600 remains `bowlers_end` after V6e
(stop-condition S2), the fix requires a different mechanism: either a STEP-1 example
for `side_on` (V6f/Option C, with full A/B gating), or a post-hoc side_on vs
bowlers_end discriminator call, or a stronger vision model.

This is the principal epistemic uncertainty in V6e. The prompt-engineering path is
not guaranteed to resolve a model-internal schema conflict.

**Severity: High if triggered (stop-condition S2). Acknowledged openly.**

### R6 — Increased prompt length raises variance across runs

**Mechanism:** Longer parenthetical may create more ambiguous decision points,
increasing the hash-count per 5-run ensemble.

**Mitigation:** V6d shadow data shows 0.53% pooled error rate and clean hash
distribution (post-harness). V6e adds ~118 characters — comparable to V6d's 88-char
and V6c's 95-char increments, neither of which materially worsened variance. Monitor
V6e hash distribution in shadow run.

**Severity: Low.**

### R7 — V6e response length / latency regression vs V6d

**Mechanism:** Longer system prompt → potentially longer completions and higher
latency.

**Mitigation:** V6d's 15 s harness timeout already provides headroom. V6e prompt
increase is ~118 chars at the system-prompt level; prior increments of similar size
did not produce latency regressions. V6d post-harness p50 latency was ~2951 ms
(well within timeout).

**Severity: Negligible.**

---

## §7 Implementation specification

### 7.a Where V6e goes in `variants.py`

Append immediately after the V6d block closing assertion:

```
variants.py:533  assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6D, (...)
variants.py:534  ← INSERT V6e block here
```

V6e is appended last; insertion point is after `variants.py:533` (the last V6d
assertion). No other file structure is affected.

Add `"V6e"` to the `VARIANTS` dict (the dict definition follows `_unescape` at
`variants.py:535+`):

```python
VARIANTS = {
    "V1":  {"prompt": _unescape(PROMPT_V1),  "alias": ALIAS_REPOINTED},
    # ... existing entries ...
    "V6d": {"prompt": _unescape(PROMPT_V6D), "alias": ALIAS_REPOINTED},
    "V6e": {"prompt": _unescape(PROMPT_V6E), "alias": ALIAS_REPOINTED},
}
```

Update `files/shadow_eval/analyze.py` `DEFAULT_VARIANTS` list to include `"V6e"`
(mirroring the V6c and V6d additions).

### 7.b Assertion patterns (mirror V6d)

All four assertions are required immediately after `PROMPT_V6E` definition:

```python
assert _V6D_BOWLERS_END_EXAMPLE in PROMPT_V6D, (
    "V6d bowlers_end example anchor missing in PROMPT_V6D — "
    "re-derive from literal slice at variants.py:495-502")
PROMPT_V6E = PROMPT_V6D.replace(
    _V6D_BOWLERS_END_EXAMPLE,
    _V6E_BOWLERS_END_EXAMPLE,
)
assert PROMPT_V6E != PROMPT_V6D, "V6e edit is a no-op"
assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6E, (
    "V6e must preserve V6c closeup example byte-identically")
assert _V6D_OTHER_RULEBOOK in PROMPT_V6E, (
    "V6e must preserve V6d other rulebook entry")
assert (PROMPT_V6E.count("\"camera_view\": \"bowlers_end\"") ==
        PROMPT_V6D.count("\"camera_view\": \"bowlers_end\"")), (
    "V6e unintentionally changed bowlers_end example count")
```

Note on first assertion: the anchor is `_V6D_BOWLERS_END_EXAMPLE` in `PROMPT_V6D`
(not `PROMPT_V6C`). V6e derives from V6d, not V6c. The anchor must exist in
`PROMPT_V6D` as confirmed by `variants.py:518–519` (`assert _V5_BOWLERS_END_EXAMPLE
in PROMPT_V6C` + the V6d replace chain). If the assertion fires, re-derive
`_V6D_BOWLERS_END_EXAMPLE` by literal slice from `variants.py:495–502` rather
than re-typing.

### 7.c Tests in `test_recent_fixes.py`

Add after V6d test block:

```python
def test_v6e_variant_registered():
    from shadow_eval.variants import VARIANTS, ALIAS_REPOINTED
    assert "V6e" in VARIANTS
    assert VARIANTS["V6e"]["alias"] is ALIAS_REPOINTED
    assert VARIANTS["V6e"]["prompt"]


def test_v6e_preserves_v6d_other_rulebook():
    """V6d's atmospheric/no-pitch fix must survive in V6e."""
    from shadow_eval.variants import VARIANTS, _V6D_OTHER_RULEBOOK, _unescape
    v6e = VARIANTS["V6e"]["prompt"]
    assert _unescape(_V6D_OTHER_RULEBOOK) in v6e


def test_v6e_preserves_v6c_closeup_example():
    """V6c's f205/f748 closeup remediation must survive in V6e."""
    from shadow_eval.variants import VARIANTS, _V6C_CLOSEUP_EXAMPLE, _unescape
    v6e = VARIANTS["V6e"]["prompt"]
    assert _unescape(_V6C_CLOSEUP_EXAMPLE) in v6e


def test_v6e_includes_side_on_negative_clause():
    """Edit C: bowlers_end example must contain explicit side_on exclusion."""
    from shadow_eval.variants import VARIANTS
    v6e = VARIANTS["V6e"]["prompt"]
    assert "NOT side-on/lateral camera angles" in v6e
    assert 'those are "side_on"' in v6e


def test_v6e_preserves_atmospheric_negative_clause():
    """V6d's atmospheric NOT clause must survive unchanged in V6e."""
    from shadow_eval.variants import VARIANTS
    v6e = VARIANTS["V6e"]["prompt"]
    assert "NOT atmospheric/crowd/stadium" in v6e
    assert 'those are "other"' in v6e


def test_v6e_prompt_structure_matches_v6d():
    """V6e must differ from V6d exactly in the bowlers_end example."""
    from shadow_eval.variants import VARIANTS
    v6d = VARIANTS["V6d"]["prompt"]
    v6e = VARIANTS["V6e"]["prompt"]
    assert v6e != v6d
    # bowlers_end example count unchanged
    assert (v6e.count('"camera_view": "bowlers_end"') ==
            v6d.count('"camera_view": "bowlers_end"'))
```

Note: the `_unescape` helper converts `{{`/`}}` → `{`/`}` for comparison with
`VARIANTS[…]["prompt"]` which is stored in unescaped form.

### 7.d Shadow run command

K=5 ensemble on combined corpus (mirrors V6d post-harness methodology from
`scout_v6d_postharness_rerun_results.md`):

```bash
cd files
for i in 1 2 3 4 5; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    python3 shadow_eval/run_shadow.py \
        --variants V6e \
        --corpus docs/scout_corpus_combined_v1.json \
        --output docs/shadow_run_v6e_combined_${TIMESTAMP}_run${i}.json \
        --no-resume
    sleep 6
done
```

Use the post-harness runner (default `--timeout-s 15`, `asyncio.TimeoutError`
retry, `MAX_ATTEMPTS=5`) — do not use a pre-harness runner version.

### 7.e Analysis comparison

V6e vs V6d comparison (ensemble majority over 5 runs each):

```bash
python3 shadow_eval/analyze.py \
    --shadow docs/shadow_run_v6e_combined_<TS>_run1.json \
             docs/shadow_run_v6e_combined_<TS>_run2.json \
             docs/shadow_run_v6e_combined_<TS>_run3.json \
             docs/shadow_run_v6e_combined_<TS>_run4.json \
             docs/shadow_run_v6e_combined_<TS>_run5.json \
    --baseline-shadow docs/shadow_run_v6d_combined_postharness_20260430_165832_run1.json \
    --variants V6e,V6d \
    --out-md docs/scout_v6e_combined_shadow_analysis_autogen.md
```

Per-frame plurality extraction for f600 specifically:

```bash
python3 -c "
import json, collections
runs = [json.load(open(f'docs/shadow_run_v6e_combined_<TS>_run{i}.json'))
        for i in range(1, 6)]
votes = collections.Counter(
    r['camera_view']
    for run in runs for r in run.get('results', [])
    if r.get('frame_id') == 'pbks_rr_f600'
)
print('f600 V6e votes:', dict(votes))
"
```

---

## §8 Acceptance criteria

### PRIMARY (all must hold for ship-conditional candidacy)

| ID | Criterion | Source | Rationale |
|----|-----------|--------|-----------|
| **P1** | `pbks_rr_f600` V6e plurality across 5 runs ≠ `bowlers_end` | Combined corpus shadow | Primary target. Any non-bowlers_end outcome (ideally `side_on`) satisfies the fix. |
| **P2** | `f941` V6e plurality across 5 runs ≠ `bowlers_end` | V6d post-harness baseline | V6d fix preserved. Atmospheric exclusion still fires. |
| **P3** | `f205` V6e plurality across 5 runs = `closeup` | V6d/V6c baseline | V6c closeup remediation preserved. Load-bearing. |
| **P4** | V6e combined corpus net accuracy ≥ V6d post-harness combined corpus net accuracy | Post-harness comparison | No net regression from V6e. |
| **P5** | V6e `bowlers_end` recall on combined corpus BE TPs ≥ V6d recall | Post-harness comparison | Edit C must not over-restrict legitimate delivery frames. |

### SECONDARY (nice-to-have; non-blocking)

| ID | Criterion |
|----|-----------|
| **S1** | `f748` V6e plurality = `side_on` or `closeup` (improvement over V6d's `bowlers_end`) |
| **S2** | V6e migration hash count ≤ 2 distinct hashes per 5 runs (determinism comparable to V6d) |
| **S3** | V6e pooled error rate < 1% (matches V6d post-harness 0.53%) |
| **S4** | V6e net accuracy improvement on combined corpus vs V6d |

### Decision matrix

| Outcome | Action |
|---------|--------|
| All PRIMARY hit, ≥1 SECONDARY hit | Ship-candidate; proceed to combined-corpus expansion gating |
| All PRIMARY hit, no SECONDARY hit | Ship-conditional; document gap and re-evaluate after next corpus expansion |
| Any PRIMARY missed | Do **not** iterate to V6f in same session; route back per §9 |

---

## §9 Composer 2 stop-and-route-back conditions

| ID | Trigger | Action |
|----|---------|--------|
| **S1** | `_V6D_BOWLERS_END_EXAMPLE` anchor assertion fires (byte mismatch in `PROMPT_V6D`) | Stop. Re-derive `_V6D_BOWLERS_END_EXAMPLE` by literal slice from `variants.py:495–502`. Do not retype from memory. If still failing: V6d → V6e construction chain is more complex than expected; route back to re-audit. |
| **S2** | V6e shadow run: `pbks_rr_f600` still plurality `bowlers_end` across 5 runs | Stop. Edit C is insufficient — model-internal schema conflict exceeds prompt-language fix. Document and route back. Next candidate: Option C (STEP-1 side_on example, with A/B gating) or post-hoc discriminator call. Do not iterate further in same session. |
| **S3** | V6e shadow run: `f941` regresses to plurality `bowlers_end` | Stop. Edit C inadvertently weakened the V6d atmospheric exclusion. Route back; inspect parenthetical structure for clause-boundary parsing issue. Do not proceed to V6f. |
| **S4** | V6e shadow run: `f205` regresses off `closeup` | Stop. V6e edit interacted with V6c closeup path. `_V6C_CLOSEUP_EXAMPLE` byte-identity assertion passing does not guarantee zero interaction; model may now prefer the new bowlers_end NOT clause over the closeup example for f205-class frames. Route back. |
| **S5** | V6e `bowlers_end` recall on combined corpus TPs drops below V6d recall (PRIMARY P5 fail) | Stop. Edit C is over-restrictive. The "fielder running parallel to boundary rope" language is being applied to delivery frames where a fielder happens to be near the boundary. Soften clause (remove "chasing ball laterally" or narrow to "boundary-fielding-only" with more explicit language) in V6f. |
| **S6** | V6e pooled error rate > 3% across 5 runs (4.5× V6d post-harness baseline) | Flag as structural issue — V6e prompt is causing timeout or parse failures at a rate inconsistent with prompt-length-only explanation. Route back before drawing accuracy conclusions from shadow data. |

---

## §10 Cross-references

| Resource | Role in V6e |
|----------|-------------|
| `files/docs/investigations/scout_v6d_implementation_audit.md` §4–§5 | H1+H3 f600 mechanism; Option A recommendation (primary design source) |
| `files/docs/investigations/scout_v6d_design.md` §4.2–§4.3, §7.b | V6d design constraint against 4th STEP-1 example; Edit A pattern for third NOT clause; Python paste format template |
| `files/shadow_eval/variants.py:457–533` | `PROMPT_V6D`, `_V6D_BOWLERS_END_EXAMPLE` (anchor), `_V6D_OTHER_RULEBOOK`, `_V6C_CLOSEUP_EXAMPLE` (insertion context) |
| `files/shadow_eval/variants.py:80–91` | Side_on rulebook entry (current wording; V6e does not modify it) |
| `files/docs/discriminating_frames_v6c_vs_v6d_combined.md` | 3 discriminating frames; `pbks_rr_f600` V6c→V6d regression evidence |
| `files/docs/investigations/scout_v6d_postharness_rerun_results.md` | Clean V6d baseline (0.53% pooled error, post-harness) for V6e comparison |
| `files/docs/investigations/scout_v6c_determinism_decision.md` | K=5 ensemble methodology; determinism tracking methodology for V6e shadow runs |
| `files/docs/investigations/combined_corpus_shadow_v6c_v6d_2026-04-30.md` | Combined corpus structure (50 frames, 150 rows/run); V6c/V6d majority hash infrastructure |
| `files/docs/investigations/scout_v6d_first_shadow_run_results.md` | V6d per-frame vote baseline for V6e per-frame comparison |
