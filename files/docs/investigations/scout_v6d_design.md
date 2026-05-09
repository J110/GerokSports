# Scout V6d — design (targeted f941 escalation fix, V6c closeup gains preserved)

**Date:** 2026-04-30
**Scope:** Prompt-only design. No code changes in this doc; all edits are
specified for Composer 2 paste-execution into
`files/shadow_eval/variants.py`.
**Status:** Design candidate.  Hypothesis ranking H1+H4 (combined) is
load-bearing; if shadow run refutes it, route back to re-diagnosis (S4).

---

## §1 Executive summary

V6c (`files/shadow_eval/variants.py:439-455`) replaced V5's STEP-1
`closeup` example sentence with a tighter "no full pitch receding away
even if camera angle is from bowler's end direction" formulation.  The
three-replicate analysis (`scout_v6c_replicate_runs_decision.md`)
confirms the trade is **structural, not stochastic**:

- f205 (human `side_on`) → `closeup` on **all 3 runs** (intended win,
  preserved).
- f748 (human `side_on`) → `closeup` on runs 2-3, `bowlers_end` on run 1
  (partial win, bistable).
- f941 (human `other`, atmospheric stadium / drone-show shot, **no
  pitch visible**) → `bowlers_end` on **all 3 runs** (operational
  escalation).
- Net frame accuracy 19/41 on every run vs V5's 20/41 (stable −1).
- Strict `bowlers_end` precision 33.3% on every run vs V5's 31.2%
  (stable +2.1pp).

**Diagnosis (§2):** the dominant mechanism is **H1 ⊗ H4 combined** —
V6c's tightened closeup example is a discrimination *gate*, not just a
broader closeup attractor.  Frames that fail the new closeup test
("face/upper body fills frame" AND "no full pitch receding away") fall
back to the **first** STEP-1 example, whose canonical literal pair
remains `("bowlers_end", "release")`.  V4's diagnostic
(`variants.py:350-372`) already proved that example values dominate
rulebook constraints: when V4 swapped the example to
`("other", "other")`, Scout emitted "other" on 36/41 frames.  V6c
inadvertently exploited the same lever in the closeup direction; the
side-effect is that **frames with no clear closeup, graphic, or
delivery signature now anchor on the first example by default**.  f941
is the textbook case (no face, no pitch, no graphic).

**V6d strategy (§4):** mirror V6c's lever — apply a **negative
discrimination test inside the bowlers_end STEP-1 example sentence**
(parallel structure to V6c's closeup tightening) plus a **single,
narrow expansion of the `other` rulebook entry**.  Both edits are
isolated to text V6c does not own and explicitly preserve V6c's
closeup example verbatim, which keeps the f205/f748 remediation intact
by construction.

**Acceptance summary (§8):** PRIMARY = net ≥ 20/41 AND f941 ≠
bowlers_end AND f205 = closeup AND BE precision ≥ 31.2%.  If V6d
shadow run misses any PRIMARY criterion, do not iterate to V6e in the
same execution session — route back per §9.

---

## §2 V6c → f941 mechanism diagnosis

### 2.1 Hypothesis ranking

The user enumerated four hypotheses.  Evidence below; ranking after.

#### H1 — Bowlers_end criteria *implicitly* loosened by closeup tightening

**Evidence (high):**
- V6c modifies *only* `_V5_CLOSEUP_EXAMPLE` → `_V6C_CLOSEUP_EXAMPLE`
  (`variants.py:439-455`).  No edit to bowlers_end rulebook
  (`_V2A_BOWLERS_END`, lines 176-185) and no edit to the bowlers_end
  STEP-1 example.  Yet f941 (and f942 in 2 of 3 runs, f020 in some
  cases) shifted INTO `bowlers_end`.
- V4 diagnostic established that the FIRST STEP-1 example's
  `camera_view` literal is the dominant default attractor (single
  swap → 36/41 emissions).  V5 retained `bowlers_end/release` as the
  first example (`variants.py:391-394`) and V6c inherits this
  ordering.
- The bowlers_end *rulebook* says "REQUIRED: the pitch extends away"
  (`vision.py:111-119` / `_V2A_BOWLERS_END`).  But because the
  example is the dominant control surface, this rulebook constraint
  is being silently ignored by Scout for f941-class frames.  The
  loosening is **emergent**, not lexical.

#### H4 — Closeup example over-specification turns it into a *gate*

**Evidence (high):**
- V5 closeup example sentence: "During a player closeup (face/body
  fills frame)" — single positive criterion, broadly inclusive.
  Scout reads any face-ish OR ambiguous-non-delivery frame as
  closeup.
- V6c closeup example sentence: "During a closeup of a player
  (face/upper body fills frame, no full pitch receding away even if
  camera angle is from bowler's end direction)" — TWO conjunctive
  criteria (face dominant AND no receding pitch).  This is a
  discrimination *test*, not an inclusive description.
- f941 satisfies neither: no face dominant (drone show / stadium
  lights), no receding pitch (no pitch at all).  Both branches of
  the conjunction reject it → falls to the `bowlers_end/release`
  default literal pair from example #1.

**H1 and H4 are not independent.**  H4 is the *immediate cause* (V6c
narrowed the closeup gate); H1 is the *consequence* (the absence of an
explicit no-pitch sink lets bowlers_end become the default attractor).
Treat as **H1 ⊗ H4 combined**.  Confidence: **high**.

#### H2 — Other category attrition

**Evidence (medium):** V6c does NOT remove or weaken the `other`
rulebook entry (`vision.py:135-136`, unchanged from V1).  But the
`other` rulebook is also weak in absolute terms: a one-line catch-all
("pre-match presenter, post-match presentation, drinks break, anything
else") with **no STEP-1 example anchor**.  Per V4's lesson, rulebook
language without an example anchor has limited control authority.  So
"other" attrition is not what V6c *did*; it is the **pre-existing
weakness** that H1+H4 now exposes for the first time.

H2 is a **contributing structural condition**, not a primary mechanism.

#### H3 — Side_on collapses into bowlers_end

**Evidence (low / refuted):** f205 and f748 (both human `side_on`)
migrated to `closeup`, not `bowlers_end`, under V6c.  If H3 were
operative we'd see them stuck in `bowlers_end`, not moving toward
`closeup`.  The side_on rulebook entry is unchanged in V6c.  **Reject
H3 for V6c.**

#### Hypothesis ranking summary

| Rank | Hypothesis | Confidence | Role |
|------|------------|-----------|------|
| 1 | H1 ⊗ H4 (combined: closeup gate + first-example default) | High | Primary mechanism |
| 2 | H2 (other-category structural weakness) | Medium | Pre-existing condition exposed by H1/H4 |
| 3 | H3 (side_on / bowlers_end collapse) | Low | Refuted by f205/f748 evidence |

### 2.2 Cross-reference: f942, f020, f022, f749

The §4 watch table in `scout_v6c_replicate_runs_decision.md` and the
autogen `scout_v6c_replicate_analysis_autogen.md` give per-run votes.
The user's prompt table inverts f942's runs; the autogen ground truth
is:

| Frame | Human | Notes (corpus_v1) | V5 | V6c run 1 | V6c run 2 | V6c run 3 |
|-------|-------|--------------------|----|-----------|-----------|-----------|
| f941 | other | drone show / stadium lights, no pitch | closeup | bowlers_end | bowlers_end | bowlers_end |
| f942 | other | boundary-board ad close-up, no pitch | bowlers_end | closeup | bowlers_end | bowlers_end |
| f020 | other | dark crowd / camera-side angle, no pitch | graphic | closeup | (per autogen f942/f748 are the ONLY 2-of-3 splits, so f020 is stable; first-run results doc said f020 V6c=closeup) | (same) |
| f022 | other | crowd in stands celebrating | other | graphic | (per autogen, stable) | (stable) |
| f749 | other | wide stand crowd shot | (not enumerated) | (not enumerated) | (not enumerated) | (not enumerated) |

**f942 supports H1+H4:** like f941, no pitch + no face-dominant
subject → falls to first-example default in 2 of 3 runs.  The 1-run
closeup outlier is consistent with V6c's bistability on borderline
frames (also seen in f748).

**f020 (closeup under V6c) is mildly inconsistent with H4:** dark
ambiguous frame still got pulled into closeup (not bowlers_end).  Best
read: closeup remains a *secondary* attractor when face-dominance is
plausibly inferable from low-light human silhouettes.  H4 explains the
default-fallback when *neither* closeup nor delivery signatures are
inferable; it does not preclude closeup wins on ambiguous frames where
some face-shape may be present.

**f022 (graphic under V6c) does not bear directly on the bowlers_end
escalation,** but flags that V6c also disturbs the closeup/graphic
boundary in ways unrelated to the f941 mechanism.  V6d does not
target this; if the regression persists we revisit separately.

---

## §3 V6c → f205 / f748 mechanism diagnosis (preserve)

### 3.1 What V6c added that drives f205/f748

Comparing `_V5_CLOSEUP_EXAMPLE` vs `_V6C_CLOSEUP_EXAMPLE`
(`variants.py:439-452`):

```
V5 :  "During a player closeup (face/body fills frame)"
V6c:  "During a closeup of a player (face/upper body fills frame,
       no full pitch receding away even if camera angle is from
       bowler's end direction)"
```

Two new lexical features:

1. **"no full pitch receding away"** — explicit visual feature
   constraint that matches f205/f748's geometry exactly (pitch
   visible but oriented left-to-right, not receding).  These frames
   pass V6c's test: face/upper body present (batter at crease) AND
   no full pitch receding away.
2. **"even if camera angle is from bowler's end direction"** — direct
   override clause that pre-empts the model's tendency to call
   anything-bowler-end-ish a `bowlers_end`.  This is the override that
   pulled f205/f748 *out* of bowlers_end.

Both features are exactly the V6c remediation language.  The corpus
narrative (`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` §"Per-frame
migrations") confirms this is the design intent.

### 3.2 What V6d MUST preserve verbatim

`_V6C_CLOSEUP_EXAMPLE` text — both the JSON shape (`closeup` /
`between_play`) and the parenthetical sentence — must be byte-identical
in V6d.  Any rewording risks breaking the f205/f748 migration.
Implementation specification §7.b enforces this with a re-use of the
existing `_V6C_CLOSEUP_EXAMPLE` constant rather than a re-typed string.

The closeup *rulebook* entry (`_V2B_CLOSEUP`, `variants.py:217-225`)
is also preserved verbatim — it carries the same "pitch does NOT
extend away → closeup" instruction in long-form, reinforcing the
example.

---

## §4 V6d prompt language design

### 4.1 Strategy

Two coordinated edits to V6c:

- **Edit A (primary lever):** tighten the **bowlers_end** STEP-1
  example sentence with a negative discrimination test, exactly
  mirroring the V6c closeup pattern.  This is the highest-authority
  prompt surface (V4 diagnostic).  Adds a "NOT atmospheric/crowd/
  stadium shots without a visible cricket pitch" guard inside the
  parenthetical.
- **Edit B (secondary attractor):** expand the `other` rulebook entry
  to enumerate the f941-class visual signatures (atmospheric/stadium/
  drone, boundary-board close-up, wide crowd) so that on-the-margin
  frames have an explicit positive landing zone in the rulebook even
  if they don't reach STEP-1 example influence.

### 4.2 Edits NOT made (and why)

- **Do NOT add a 4th STEP-1 example for "other".**  V4's
  catastrophic over-shift (single-character example swap → 36/41
  emissions) means examples have outsized control authority.  Adding
  a peer "other" example would create a fourth attractor whose pull
  on legitimate cricket frames is unpredictable.  The bowlers_end
  example tightening achieves the targeted suppression without
  introducing a new positive default.
- **Do NOT swap the FIRST STEP-1 example off bowlers_end.**  Same V4
  evidence: changing the first example shifts the entire emission
  distribution.  V4b (V2A rulebook + neutral example) is on the
  shelf if we ever want to test that lever independently; V6d is not
  the place.
- **Do NOT modify the bowlers_end RULEBOOK entry**
  (`_V2A_BOWLERS_END`).  V4 showed rulebook constraints are weak
  control surface; the rulebook already says "REQUIRED: the pitch
  extends away" and Scout ignores it for f941.  Adding more rulebook
  text wastes attention budget without addressing the actual lever.
- **Do NOT modify the V6c closeup example or rulebook.**  Preserving
  f205/f748 gains is a PRIMARY acceptance criterion (§8).  Any edit
  here puts the preserved gain at risk.

### 4.3 Edit A — bowlers_end STEP-1 example sentence

V5/V6c text (`variants.py:391-394`, embedded in `_V5_STEP1_BLOCK`):

```
- During a delivery (camera behind bowler, pitch extends away):
{"has_strip": true, "has_overlay_stats": false, "drs_review": false,
"camera_view": "bowlers_end", "frame_phase": "release",
"ball_position": null}
```

V6d replacement (parenthetical extended, JSON shape unchanged):

```
- During a delivery (camera behind bowler AND pitch extends away
toward the far stumps; NOT atmospheric/crowd/stadium shots without
a visible cricket pitch — those are "other"):
{"has_strip": true, "has_overlay_stats": false, "drs_review": false,
"camera_view": "bowlers_end", "frame_phase": "release",
"ball_position": null}
```

Length delta: +88 characters in the parenthetical.  Comparable to
V6c's closeup tightening (+95 characters).  JSON shape and ordering
unchanged; first-example-default behavior for legitimate delivery
frames is preserved (the default attractor still resolves to
`bowlers_end/release` when the discrimination test passes).

Discrimination semantics:
- AND-conjunction "camera behind bowler AND pitch extends away" — both
  must hold (mirrors V6c closeup's compound test).
- "NOT atmospheric/crowd/stadium shots without a visible cricket pitch"
  — explicit f941-class exclusion in the model's preferred control
  surface.
- "those are 'other'" — explicitly names the bin Scout should fall to,
  removing the implicit-default ambiguity that pushes Scout back to
  example #1.

### 4.4 Edit B — `other` rulebook entry expansion

V5/V6c text (`vision.py:135-136`, identical to V1 in `variants.py`
since V1; lives inside `PROMPT_V1` and propagates to V5/V6c
unchanged):

```
  - "other": pre-match presenter, post-match presentation, drinks
    break, anything else.
```

V6d replacement:

```
  - "other": pre-match presenter, post-match presentation, drinks
    break, atmospheric/stadium/crowd shots without a visible cricket
    pitch (drone shows, boundary-board close-ups, wide stand crowds,
    dark camera-side angles), anything else.
```

Length delta: +119 characters.  Adds explicit positive enumeration of
the f941/f942/f020/f749 visual signatures derived from
`scout_corpus_v1.json` notes.  Keeps "anything else" tail to preserve
generality.

### 4.5 Implementation diff (V6c → V6d)

Two anchored replacements on `PROMPT_V6C`:

```python
# Anchor 1: bowlers_end STEP-1 example sentence (Edit A)
_V5_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler, pitch extends away): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)
_V6D_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)

# Anchor 2: "other" rulebook entry (Edit B)
_V1_OTHER_RULEBOOK = (
    "  - \"other\": pre-match presenter, post-match presentation, "
    "drinks \\\n    break, anything else."
)
_V6D_OTHER_RULEBOOK = (
    "  - \"other\": pre-match presenter, post-match presentation, "
    "drinks \\\n    break, atmospheric/stadium/crowd shots without "
    "a visible cricket pitch (drone shows, boundary-board close-ups, "
    "wide stand crowds, dark camera-side angles), \\\n    anything "
    "else."
)

assert _V5_BOWLERS_END_EXAMPLE in PROMPT_V6C, \
    "V5 bowlers_end example anchor missing"
assert _V1_OTHER_RULEBOOK in PROMPT_V6C, \
    "V1 'other' rulebook anchor missing"
PROMPT_V6D = (
    PROMPT_V6C
    .replace(_V5_BOWLERS_END_EXAMPLE, _V6D_BOWLERS_END_EXAMPLE)
    .replace(_V1_OTHER_RULEBOOK, _V6D_OTHER_RULEBOOK)
)
assert PROMPT_V6D != PROMPT_V6C, "V6d edits were a no-op"
```

> **Composer 2 caveat — line-continuation backslash:** The `_V1_…`
> anchor contains the literal backslash-newline-spaces sequence used
> by Python's implicit string-continuation in the source file.  When
> Composer 2 pastes the anchor it must extract the EXACT byte
> sequence from `PROMPT_V1` (`variants.py:99-100`).  If the anchor
> assertion fires on first run, Composer 2 must re-derive
> `_V1_OTHER_RULEBOOK` by literal slice from `PROMPT_V1` rather than
> re-typing.  This is stop-condition S1.

### 4.6 Output schema / harness compatibility

Unchanged.  V6d's edits are **inside** existing prompt anchors; the
JSON-tag line shape, STEP-2 strip block, STEP-3 overlay block, STEP-4
action sentence, the `{vision_hint}` slot, and the alias / canon
machinery (`variants.py:18-61`) are all untouched.  Downstream:

- `run_shadow.py:38` imports `VARIANTS`; adding `"V6d": {...}` to the
  dict (§7.a) makes V6d available to `--variants V6d` without harness
  changes.
- `analyze.py` variant list must add `V6d` for table generation
  (Composer 2 task; mirrors the V6c addition documented in
  `scout_v6c_shadow_run_corpus_v1_2026-04-25.md` "Files touched").
- `replicate_analysis.py` is owned by the parallel determinism
  session (§10) — V6d session does NOT touch it.

---

## §5 Expected V6d behavior (per-frame predictions)

Predictions are validation criteria for the V6d shadow run.  Sources:
human label from `scout_corpus_v1.json`; V5 vote from
`shadow_run_v1.json` baseline; V6c vote from autogen.

| Frame | Human | V5 vote | V6c vote (3-run mode) | V6d expected | Rationale | Confidence |
|-------|-------|---------|------------------------|--------------|-----------|------------|
| f941 | other | closeup | bowlers_end (3/3) | **other** | Edit A's negative test in bowlers_end example explicitly excludes atmospheric/no-pitch frames. Edit B's expanded `other` rulebook names this exact signature. Closeup gate (V6c) still rejects (no face dominance). Default-fallback now resolves to "other" because example A explicitly directs there. | High |
| f942 | other | bowlers_end (run1=closeup, run2/3=bowlers_end) | bowlers_end (2/3 mode) | **other** | Same mechanism as f941: boundary-board close-up has no pitch. Edit A excludes; Edit B names "boundary-board close-ups" verbatim. Run-1's `closeup` outlier suggests f942 is bistable; V6d should land on "other" stably. | High |
| f205 | side_on | bowlers_end | closeup (3/3) | **closeup** | V6c closeup example preserved verbatim. Closeup test still passes (face dominant, no pitch receding). No V6d edit affects this path. | High (preserved by construction) |
| f748 | side_on | bowlers_end | closeup (run1=bowlers_end, run2/3=closeup) | **closeup** | Same path as f205. V6c bistability on f748 (run 1 outlier) is a separate determinism issue; V6d does not address it but does not aggravate it. f748 inherits V6c's behavior here. | Medium (bistability inherited from V6c) |
| f020 | other | graphic | closeup | **closeup or other** | Dark camera-side crowd, no pitch. Edit B mentions "dark camera-side angles" → potential pull to "other". Closeup has been winning under V6c (perhaps reading low-light human silhouettes as face-ish). Either outcome counts as non-regression vs PRIMARY (closeup keeps V5's net deficit; other is the human-label win). | Low |
| f022 | other | other | graphic | **other (target) or graphic (V6c carry-over)** | Crowd celebration in stands. V5 correctly emitted "other"; V6c regressed to "graphic" by mechanism unrelated to bowlers_end gate. Edit B's expanded `other` rulebook may pull it back; Edit A does not target this path. If V6d returns "other", that is a bonus non-PRIMARY win. | Low |
| f169 / f955 / f754 / f945 / f946 (BE TPs) | bowlers_end | bowlers_end | bowlers_end | **bowlers_end** | All five frames have a clearly receding pitch with bowler/batter visible. Edit A's tightened example still resolves to `bowlers_end/release` for legitimate deliveries; both clauses of the AND-conjunction hold. Recall floor preserved. | High (recall floor by construction) |

**Aggregate prediction (best case):** f941 → other, f942 → other,
f205/f748/f205 closeup gains preserved, BE recall floor preserved.
That yields net frame accuracy 21/41 (V5 baseline 20/41 +1 from f941
flipping to correct, +1 from f942 flipping to correct, −1 because V6c
already gave away f022 to graphic and V6d may not fully recover it
within margin of the prompt's secondary effects).  **Realistic target:
21/41 ± 1.**

**Aggregate prediction (worst case that still passes PRIMARY):** f941
→ other (PRIMARY satisfied), f942 → unchanged (carry V6c noise),
f205/f748 preserved, BE precision unchanged at 33.3%, net = 20/41.
This is the floor case where V6d ships ship-conditional per §8.

---

## §6 Risk assessment

### R1 — Tightened bowlers_end example reduces strict BE precision below V5's 31.2%

- Mechanism: Edit A's negative test is additive (it excludes
  atmospheric frames; it does not change the criteria for legitimate
  deliveries).  Theory: legitimate deliveries pass the AND-conjunction
  unchanged, so emissions remain.
- Empirical risk: if Scout reads the negative clause too aggressively
  and starts excluding low-confidence delivery frames (e.g., f175
  partial graphic overlay), BE emissions could drop below 15.
- Mitigation: §7.c specifies a precision-floor guard in the V6d
  shadow analysis — if BE emissions drop below 13 (≈ −2 from V6c
  baseline), declare R1 realised and route back per S3/S4.

### R2 — Expanded "other" rulebook pulls legitimate side_on frames toward "other"

- Mechanism: side_on is rulebook-anchored only (no STEP-1 example
  inside V5/V6c lineage).  Edit B widens the rulebook's `other` —
  could create competition for borderline side_on frames.
- Empirical risk: f205/f748 are NOT side_on by Scout's STEP-1 path
  (they go to closeup under V6c), so this risk is decoupled from the
  preserved gain.  But other side_on frames in larger corpora could
  get pulled.
- Mitigation: corpus_v1 has only 3 human side_on frames (f205, f748,
  one more); validate on §5's table.  If R2 fires we revisit Edit B
  scope.

### R3 — Edit A breaks V6c closeup gains via interaction with the closeup example

- Mechanism: V6c closeup example references "even if camera angle is
  from bowler's end direction".  V6d's bowlers_end example now also
  has discrimination language.  Possible interaction: Scout reads
  both negative tests and gets confused.
- Empirical risk: the two examples target different visual
  signatures.  V6c closeup says "no full pitch receding away" (about
  pitch geometry).  V6d bowlers_end says "no atmospheric/crowd/
  stadium without pitch" (about scene type).  Disjoint vocabulary;
  low interaction risk.
- Mitigation: §7.c requires explicit f205/f748 check on V6d shadow
  run.  If f205 regresses, S5 routes back.

### R4 — V6d net accuracy doesn't improve over V5's 20/41

- Mechanism: f941 fix could be correct (PRIMARY ✓) while other
  frames regress under the same lever.  E.g., f175 (medium-confidence
  graphic) flips to closeup instead of graphic.
- Empirical risk: medium.  V6c already moves frames around without
  net gain; V6d edits could continue this pattern.
- Mitigation: §8 PRIMARY explicitly does NOT require improvement,
  only non-regression.  If net = 20/41 and f941 fixed, ship-
  conditional.  If net < 20/41, route back per S3.

### R5 — V6d determinism is worse than V6c

- Mechanism: longer example sentences with more complex parenthetical
  may introduce sampling-variance under temperature=0 bounded-
  stochastic execution (the cause of V6c's 4.9% cross-run flip and
  10.6% mean internal flip per the replicate analysis).
- Empirical risk: medium.  V6c's two-hash run profile suggests prompt
  length is not the dominant determinism driver (run 2 = run 3 is
  pair-stable despite identical prompt).  Edit A and Edit B are
  shorter than the V3 disambiguation block (which itself shipped
  fine in test).
- Mitigation: V6d shadow run uses **3 replicate runs** (mirroring
  V6c's session), and the parallel determinism session (§10) is
  adding 2 V6c runs and Groq metadata capture which will inform any
  determinism decision.  V6d does not block on determinism analysis;
  it inherits it.

### R6 (new) — "Atmospheric/stadium/crowd" vocabulary mismatches Scout's internal scene taxonomy

- Mechanism: Scout (Llama-4 Scout 17B) may not recognize
  "atmospheric" in the cricket-broadcast sense, or may over-apply it
  to legitimate wide field shots.
- Empirical risk: low — the vocabulary is descriptive and matches
  language a vision model would readily ground (cf. similar phrasing
  in V3's disambiguation block which shipped without issue).
- Mitigation: if observed, replace "atmospheric" with concrete
  signature words ("drone show", "stadium lights", "fan crowd in
  stands") in V6e iteration; do not block V6d on this.

---

## §7 Implementation specification (Composer 2 execution-ready)

### 7.a Where V6d goes in `variants.py`

Append after the V6c block (`variants.py:416-455`).  Insertion point
is **immediately before** the `_unescape` helper definition
(`variants.py:458`).  Add the new variant to the `VARIANTS` dict
(`variants.py:469-478`) as the last entry:

```python
VARIANTS = {
    "V1":  {"prompt": _unescape(PROMPT_V1),  "alias": ALIAS_REPOINTED},
    ...
    "V6c": {"prompt": _unescape(PROMPT_V6C), "alias": ALIAS_REPOINTED},
    "V6d": {"prompt": _unescape(PROMPT_V6D), "alias": ALIAS_REPOINTED},
}
```

Update the `analyze.py` variants list to include `"V6d"` analogous to
V6c (`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` "Files touched"
entry).

### 7.b Exact V6d prompt definition (paste-ready)

Insert at `variants.py:456` (immediately after the `assert PROMPT_V6C
!= PROMPT_V5` line):

```python
# ---------------------------------------------------------------------
# V6d — V6c base + targeted f941 escalation fix.
#
# V6c (closeup STEP-1 example tightened with "no full pitch receding
# away" discrimination) preserved f205/f748 closeup remediation but
# inadvertently turned the closeup example into a discrimination GATE
# rather than an inclusive attractor: frames that fail both the
# closeup test (no face dominance + no pitch receding) and the
# delivery signature now fall back to the FIRST STEP-1 example's
# default literal pair (bowlers_end/release).  f941 (atmospheric
# stadium / drone show, no pitch) lands stably on bowlers_end across
# all 3 V6c replicates — operational severity escalation per
# files/docs/investigations/scout_v6c_replicate_runs_decision.md §4.
#
# V6d edits ONLY:
#   (A) the bowlers_end STEP-1 example parenthetical — adds a
#       symmetric negative discrimination test ("NOT atmospheric/
#       crowd/stadium shots without a visible cricket pitch — those
#       are 'other'") to mirror the V6c closeup tightening pattern,
#       which V4 (variants.py:350-372) established as the dominant
#       prompt control surface.
#   (B) the "other" rulebook entry — appends explicit visual-
#       signature enumeration matching f941/f942/f020/f749 corpus
#       notes, giving "other" a stronger positive landing zone for
#       no-pitch ambiguous frames.
#
# V6d preserves V6C_CLOSEUP_EXAMPLE byte-identically (f205/f748
# remediation by construction) and does NOT change the bowlers_end
# rulebook, the closeup rulebook, the side_on rulebook, the STEP 1
# example count or ordering, or any STEP 2-4 content.  Schema /
# alias / canon machinery untouched.
#
# Predicted f941 fix (high confidence per §2 of design doc):
# atmospheric/no-pitch frames now have an explicit named exclusion in
# the dominant control surface (Edit A) AND a positive landing zone
# in the rulebook (Edit B).  Predicted f205/f748 preservation (high
# confidence): closeup example untouched.
# ---------------------------------------------------------------------
_V5_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler, pitch extends away): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)
_V6D_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)

# Anchor for the "other" rulebook entry — derived by literal slice
# from PROMPT_V1 lines that produce vision.py:135-136.  IMPORTANT:
# this anchor includes the source-file backslash-continuation
# pattern; if the assert below fires, re-derive by literal slice
# from PROMPT_V1 rather than re-typing.
_V1_OTHER_RULEBOOK = (
    "  - \"other\": pre-match presenter, post-match presentation, "
    "drinks \\\n    break, anything else."
)
_V6D_OTHER_RULEBOOK = (
    "  - \"other\": pre-match presenter, post-match presentation, "
    "drinks \\\n    break, atmospheric/stadium/crowd shots without "
    "a visible cricket pitch (drone shows, boundary-board close-ups, "
    "wide stand crowds, dark camera-side angles), \\\n    anything "
    "else."
)

assert _V5_BOWLERS_END_EXAMPLE in PROMPT_V6C, \
    "V5 bowlers_end example anchor missing in V6c"
assert _V1_OTHER_RULEBOOK in PROMPT_V6C, \
    "V1 'other' rulebook anchor missing in V6c"
PROMPT_V6D = (
    PROMPT_V6C
    .replace(_V5_BOWLERS_END_EXAMPLE, _V6D_BOWLERS_END_EXAMPLE)
    .replace(_V1_OTHER_RULEBOOK, _V6D_OTHER_RULEBOOK)
)
assert PROMPT_V6D != PROMPT_V6C, "V6d edits were a no-op"
assert PROMPT_V6D.count("\"camera_view\": \"bowlers_end\"") == \
    PROMPT_V6C.count("\"camera_view\": \"bowlers_end\""), \
    "V6d unintentionally changed bowlers_end example count"
assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6D, \
    "V6d must preserve V6c closeup example byte-identically"
```

### 7.c Test fixtures (no API calls)

Add to whichever existing pytest module covers `variants.py`
(grep for `PROMPT_V6C` or `VARIANTS` in `files/shadow_eval/tests` —
Composer 2 to discover and place; if no test module exists for
variants, add a new one named `test_variants_v6d.py`).

```python
def test_v6d_variant_registered_correctly():
    from shadow_eval.variants import VARIANTS, ALIAS_REPOINTED
    assert "V6d" in VARIANTS
    assert VARIANTS["V6d"]["alias"] is ALIAS_REPOINTED
    assert VARIANTS["V6d"]["prompt"]


def test_v6d_preserves_v6c_closeup_example():
    """Load-bearing: V6d MUST keep V6c's closeup example verbatim
    so f205/f748 closeup remediation is structurally preserved."""
    from shadow_eval.variants import (
        VARIANTS, _V6C_CLOSEUP_EXAMPLE, _unescape,
    )
    v6d = VARIANTS["V6d"]["prompt"]
    assert _unescape(_V6C_CLOSEUP_EXAMPLE) in v6d


def test_v6d_bowlers_end_example_has_negative_test():
    from shadow_eval.variants import VARIANTS
    v6d = VARIANTS["V6d"]["prompt"]
    assert "NOT atmospheric/crowd/stadium" in v6d
    assert "those are \"other\"" in v6d


def test_v6d_other_rulebook_enumerates_atmospheric():
    from shadow_eval.variants import VARIANTS
    v6d = VARIANTS["V6d"]["prompt"]
    assert "drone shows" in v6d
    assert "boundary-board close-ups" in v6d


def test_v6d_distinct_from_v6c():
    from shadow_eval.variants import VARIANTS
    assert VARIANTS["V6d"]["prompt"] != VARIANTS["V6c"]["prompt"]


def test_v6d_first_step1_example_still_bowlers_end():
    """Mechanistic safety: the FIRST STEP-1 example camera_view
    must remain 'bowlers_end' (V4 evidence: first example dominates
    the default attractor).  V6d edits must not reorder or swap."""
    from shadow_eval.variants import VARIANTS
    v6d = VARIANTS["V6d"]["prompt"]
    first_camera_view = v6d.split("\"camera_view\":", 1)[1]
    first_camera_view = first_camera_view.split(",", 1)[0].strip()
    assert "bowlers_end" in first_camera_view
```

### 7.d Shadow run command

Run from `files/`:

```bash
cd files
python3 shadow_eval/run_shadow.py \
  --variants V6d \
  --corpus docs/scout_corpus_v1.json \
  --output docs/shadow_run_v6d_<TS>.json \
  --no-resume
```

For determinism parity with V6c's three-replicate analysis, execute
**three independent runs** with `--no-resume` and disjoint output
filenames following the V6c naming convention:

```
docs/shadow_run_v6d_<TS>.json
docs/shadow_run_v6d_<TS>_run2.json
docs/shadow_run_v6d_<TS>_run3.json
```

### 7.e Analysis commands

V6d vs V5 baseline (single-run analysis):

```bash
python3 shadow_eval/analyze.py \
  --shadow docs/shadow_run_v6d_<TS>.json \
  --baseline-shadow docs/shadow_run_v1.json \
  --variants V5,V6d \
  --out-md docs/scout_v6d_first_shadow_analysis_autogen.md
```

V6d vs V6c (regression check on preserved gains) — three-run replicate
analysis using the existing tool (owned by determinism session per
§10, but read-only invocation is fine):

```bash
python3 shadow_eval/replicate_analysis.py \
  --runs docs/shadow_run_v6d_<TS>.json \
         docs/shadow_run_v6d_<TS>_run2.json \
         docs/shadow_run_v6d_<TS>_run3.json \
  --baseline docs/shadow_run_v1.json \
  --out-md docs/scout_v6d_replicate_analysis_autogen.md
```

Manually compose `files/docs/investigations/scout_v6d_first_shadow_run_results.md`
mirroring the V6c first-run results doc structure once the run lands.

---

## §8 Acceptance criteria

### PRIMARY (all must hold for ship-conditional candidacy)

- **P1.** Net frame accuracy (vote_cam == human label, N=41) ≥ **20/41**
  (V5 baseline; V6d must not regress further than V6c).
- **P2.** f941 majority vote across V6d runs is **NOT** `bowlers_end`
  (operational-severity fix; the sole non-negotiable).
- **P3.** f205 majority vote across V6d runs is `closeup` (V6c
  remediation preserved; load-bearing assumption check).
- **P4.** Strict `bowlers_end` precision ≥ **31.2%** (V5 baseline;
  prevents R1 silent regression).
- **P5.** Strict `bowlers_end` recall on the 5 human BE TPs (f169,
  f955, f754, f945, f946) stays at **100%** (recall floor preserved).

### SECONDARY (nice-to-have; non-blocking)

- S1. Net frame accuracy **≥ 21/41** (improvement over V5).
- S2. f748 majority vote is `closeup` stably across all 3 runs
  (improves on V6c's run-1 bistability).
- S3. f942 majority vote is **NOT** `bowlers_end` (additional f941-
  class win).
- S4. Strict `bowlers_end` precision **≥ 33.3%** (V6c level
  preserved or improved).
- S5. Internal flip rate **≤ 7.3%** (V5 stability).

### TERTIARY (informational only)

- T1. Cross-run flip rate ≤ V6c's 4.9%.
- T2. f020 / f022 classification correctness (any improvement is bonus;
  no regression bar).
- T3. Migration-hash equality across all 3 V6d runs (would be
  evidence that the prompt change reduces sampling variance, not just
  shifts attractors).

### Decision matrix

| Outcome | Action |
|---------|--------|
| All PRIMARY hit, ≥1 SECONDARY hit | Ship-candidate; proceed to combined-corpus expansion gating |
| All PRIMARY hit, no SECONDARY hit | Ship-conditional; re-evaluate after combined-corpus or determinism session signal |
| Any PRIMARY missed | Do **not** iterate to V6e in same session; route back per §9 |

---

## §9 Composer 2 stop-and-route-back conditions

| ID | Condition | Action |
|----|-----------|--------|
| **S1** | The `_V1_OTHER_RULEBOOK` anchor assertion fires (line-continuation byte sequence mismatch with `PROMPT_V1`) | Stop. Re-derive the anchor by literal slice from `PROMPT_V1` (`variants.py:99-100`). If still failing, route back: V6c → V6d diff is more complex than expected; design assumed clean string anchors. |
| **S2** | f941 visual characteristics turn out NOT to match the corpus_v1 notes (e.g., the actual frame is a wide field shot Scout reads as bowlers_end for legitimate geometric reasons) | The targeted Edit A language ("atmospheric/crowd/stadium without visible pitch") may not match. Document observed frame content in `scout_v6d_first_shadow_run_results.md` §"f941 visual characterization" and route back rather than tweaking Edit A in-session. |
| **S3** | V6d shadow run net accuracy < 20/41 (PRIMARY P1 missed) | Route back. Do **not** iterate to V6e in same session. The PRIMARY-miss signal warrants design re-think; iterating in-session risks compounding errors. |
| **S4** | V6d shadow run reveals f941 still classified as `bowlers_end` (PRIMARY P2 missed) | Route back. The H1 ⊗ H4 hypothesis was wrong; re-diagnose mechanism. Possible alternates: rulebook-only weakness, model-internal closeup definition robustness, or a non-prompt-only path needed. |
| **S5** | V6d shadow run reveals f205 regression (no longer `closeup`) (PRIMARY P3 missed) | Route back. V6d edits had unintended impact on closeup boundary. Likely R3 realised — Edit A's negative test is interfering with V6c closeup reading. |
| **S6** | V6d strict bowlers_end precision drops below 31.2% (PRIMARY P4 missed) | Route back per R1. Edit A's negative clause is over-aggressive; needs softening (e.g., remove the "those are 'other'" suffix and re-test). |
| **S7** | V6d strict bowlers_end recall on the 5 BE TPs drops below 100% (PRIMARY P5 missed) | Route back. Edit A's "AND pitch extends away toward the far stumps" wording is being read as exclusionary by Scout for legitimate frames where the pitch geometry is partially occluded (e.g., f175). |
| **S8** | All 3 V6d runs produce identical migration hashes AND match V6c run 2/3 hash | Inform parallel determinism session — pair-stable hash recurrence across two prompts suggests the determinism phenomenon is not prompt-driven; their hypothesis space narrows. Not a stop, just a coordination signal. |

---

## §10 Coordination with parallel determinism session

The determinism instrumentation session (Composer 2 parallel) owns:

- `files/shadow_eval/run_shadow.py` (Groq metadata capture additions).
- 2 additional V6c shadow runs (runs 4, 5) on
  `docs/scout_corpus_v1.json`.
- `files/shadow_eval/replicate_analysis.py` extensions.
- Output doc: `scout_v6c_determinism_decision.md`.

V6d session **does not** touch:

- `run_shadow.py` (read-only invocation only).
- V6c shadow runs / V6c output JSONs.
- `replicate_analysis.py` source (read-only invocation for V6d
  replicate analysis is fine; do not modify).

V6d session **does** touch:

- `files/shadow_eval/variants.py` (append PROMPT_V6D + VARIANTS entry).
- `files/shadow_eval/analyze.py` (add `"V6d"` to variants list,
  mirroring V6c addition).
- New file: `files/docs/investigations/scout_v6d_design.md` (this doc).
- New file (post-execution): `files/docs/investigations/scout_v6d_first_shadow_run_results.md`.
- New file (post-execution, if 3 runs): `files/docs/scout_v6d_first_shadow_analysis_autogen.md`,
  `files/docs/scout_v6d_replicate_analysis_autogen.md`.
- New file (post-execution): three `docs/shadow_run_v6d_<TS>*.json`
  artifacts.

`files/docs/backlog.md` is the shared edit point — append-only,
mergeable.  Add a single bullet under the "Scout prompt iterations"
section after V6d shadow run lands.

If the determinism session lands first and reports that V6c
non-determinism is harness-induced (e.g., a `temperature=0` violation
in a retry path), then **§5 predictions for f942 and f748** become
re-evaluable: V6d may inherit fewer determinism-driven flips than
predicted.  If the determinism session lands *after* V6d, V6d's
shadow run data feeds their analysis.

Either ordering is fine.  No execution dependency between sessions.

---

## §11 Cross-references

| Path | Purpose |
|------|---------|
| `files/shadow_eval/variants.py:439-455` | V6c definition (V6d source diff) |
| `files/shadow_eval/variants.py:384-413` | V5 STEP-1 block (Edit A anchor source) |
| `files/shadow_eval/variants.py:99-100` (within `PROMPT_V1`) | "other" rulebook anchor source for Edit B |
| `files/shadow_eval/variants.py:350-372` | V4 diagnostic — example dominance evidence |
| `files/eyes/vision.py:83-215` | Production SCOUT_PROMPT (currently = V5) |
| `files/eyes/vision.py:111-119` | Production bowlers_end rulebook (Edit A's rulebook companion; not modified) |
| `files/eyes/vision.py:135-136` | Production "other" rulebook (Edit B target) |
| `files/docs/scout_corpus_v1.json` | Frame metadata; f941/f942/f020/f022/f749 visual notes informed Edit B vocabulary |
| `files/docs/investigations/scout_v6c_first_shadow_run_results.md` | First V6c run flag of f941 escalation |
| `files/docs/investigations/scout_v6c_replicate_runs_decision.md` | Three-run replicate analysis; §4 watch frames table |
| `files/docs/scout_v6c_replicate_analysis_autogen.md` | Machine-generated cross-run metrics; ground truth on f942 run-by-run votes |
| `files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md` | V6c hypothesis & intended remediation; §"Per-frame migrations" |
| `files/docs/investigations/scout_codebase_discovery.md` | Scout = Groq llama-4-scout + SCOUT_PROMPT |
| `files/shadow_eval/run_shadow.py:335-380` | `--variants` CLI flag handling |

---

## §12 Honesty / open gaps

- **Bistability inheritance:** V6d does not address V6c's f748 / f942
  run-1 outlier behavior.  If determinism is fundamentally a Groq
  inference-side phenomenon (parallel session's hypothesis), V6d's
  prompt edits do not alter that surface.  Acceptance criterion P3
  is stated on **majority vote**, so single-run outliers don't fail
  PRIMARY — but they do hint that V6d may need a determinism-driven
  follow-up regardless of prompt-design correctness.
- **f020 prediction confidence is genuinely low.**  The frame is a
  dark camera-side angle; whether Edit B's "dark camera-side angles"
  language is enough of a pull against V6c's closeup attractor is
  unknown.  This is acknowledged in §5 — f020 outcome is informational
  (T2), not blocking.
- **No corpus expansion in V6d session.**  The 41-frame corpus is
  small; net 20→21 is a single-frame swing.  PRIMARY criteria are
  calibrated to this reality (non-regression rather than improvement).
  Combined-corpus expansion is gated on sampler M-2 per
  `scout_v6c_shadow_run_corpus_v1_2026-04-25.md` and is out of V6d
  scope.
- **Alternative if V6d as designed cannot achieve PRIMARY:**  if S3,
  S4, or S5 fires, the recommendation is **not** to immediately
  iterate to V6e.  Instead:
  1. Wait for parallel determinism session signal — if V6c
     non-determinism is harness-driven, V6d's prompt edits may not
     have been the load-bearing variable in the first place.
  2. If determinism is confirmed prompt-stable but V6d still misses
     PRIMARY, the next move is **non-prompt-only investigation** —
     either a stronger vision model (Llama-4 Maverick, Pixtral,
     GPT-4o-mini-vision) on the same SCOUT_PROMPT, or a post-hoc
     verification call (Scout outputs `bowlers_end` → secondary
     pass with a "confirm pitch extends away" boolean question).
  3. Only after both of the above clear should V6e be designed —
     and then with a re-grounded mechanism diagnosis, not a
     "tighten further" reflex.
