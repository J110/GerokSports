# Scout V6d — implementation vs design audit (read-only)

**Date:** 2026-04-30  
**Scope:** Compare `scout_v6d_design.md` (spec) to **`files/shadow_eval/variants.py`** as shipped (`PROMPT_V6D`). No edits to variants or shadows in this audit.  
**Context:** Combined-corpus disagreement on **`pbks_rr_f600`** — V6c majority `side_on`, V6d majority `bowlers_end` (`discriminating_frames_v6c_vs_v6d_combined.md`).

---

## §1 Executive summary

| Question | Answer |
|---------|--------|
| Does **`PROMPT_V6D` match design intent for Edits A and B? | **Yes** — the bowlers-end STEP‑1 symmetric negative wording and the expanded `other` rulebook enumeration match **`scout_v6d_design.md` §4.3–§4.4** and the paste block in §7.b, modulo one **documentation-vs-repo footnote** on the **`_V1_OTHER_RULEBOOK` anchor string** (see §2). |
| **Most likely explanation for `f600` (`side_on` → `bowlers_end` under V6d)?** | **H1 (design scope gap) dominates:** the V6d negative clause only excludes **atmospheric / crowd / stadium without a visible pitch**. A **boundary fielding chase** angle typically **does show pitch** (or the model assimilates geometry to “pitch extends away”), so the exclusion **does not fire**; **`f600` was never in the f941-class target set.** **H3** is a strong **secondary** amplifier: **STEP‑1 Example 1 remains the dominant attractor** (V4 diagnostic); tightened AND-language (“pitch extends away toward the far stumps”) can still be satisfied by ambiguous wide-angle cricket shots. |
| **H2 (implementation drift)?** | **Refuted for substantive text:** literals are present where the tests and design prescribe (NOT atmospheric clause, `"other"` redirect, enumerated signatures). |
| **Recommendation** | **Iterate V6e on design**, not “fix V6d drift”: add explicit **boundary / side‑on vs bowlers_end** discrimination (negative on `bowlers_end` example **or** a carefully scoped STEP‑1 / rulebook augmentation); **preserve** **`_V6C_CLOSEUP_EXAMPLE`** verbatim. Optionally **replay** disputed frames at **lower concurrency** if treating Groq noise separately (orthogonal to this audit). |

---

## §2 V6d prompt structure (actual vs design)

### 2.1 Construction (verified)

Per `variants.py`:

- **`PROMPT_V6D = PROMPT_V6C.replace(_V5_BOWLERS_END_EXAMPLE, _V6D_BOWLERS_END_EXAMPLE).replace(_V1_OTHER_RULEBOOK, _V6D_OTHER_RULEBOOK)`** (lines **522–525**).
- Assertions enforce: anchors present in **`PROMPT_V6C`**, `PROMPT_V6D ≠ PROMPT_V6C`, same count of **`"camera_view": "bowlers_end"`** in examples, and **`_V6C_CLOSEUP_EXAMPLE`** substring remains in **`PROMPT_V6D`** (**lines **518–531**).

So **substitution sites (a)** bowlers-end STEP‑1 example and **(b)** `other` rulebook — **both** exist, as designed. **No other replace** touches V6c.

### 2.2 Edit A — `_V6D_BOWLERS_END_EXAMPLE` (excerpt — source verbatim)

Source (`variants.py` **495–502**):

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

Comparison to **`scout_v6d_design.md` §4.3 / §7.b:** **Same lexical content** — AND-conjunction, **NOT atmospheric/crowd/stadium shots without a visible cricket pitch**, and **those are `"other"`** inside the STEP‑1 **first** example line. Functions as **discrimination** language (compound condition + explicit negative + destination label), not mere decoration.

### 2.3 Edit B — `_V6D_OTHER_RULEBOOK` (excerpt — source verbatim)

Source (`variants.py` **510–516**):

```python
_V6D_OTHER_RULEBOOK = (
    '  - "other": pre-match presenter, post-match presentation, '
    'drinks     break, atmospheric/stadium/crowd shots without '
    'a visible cricket pitch (drone shows, boundary-board close-ups, '
    'wide stand crowds, dark camera-side angles), '
    'anything else.'
)
```

Comparison to **design §4.4:**

- Lists **atmospheric/stadium/crowd without visible pitch**, **drone shows**, **boundary-board close-ups**, **wide stand crowds**, **dark camera-side angles** — **matches** the design bullet (generalised **from** corpus notes, **not** frame ids in the prompt — as spec’d).
- **Does not** add language that distinguishes **square / boundary fielding with visible pitch** from **bowlers_end** beyond what V1/V5 already implied.

### 2.4 Footnote — `_V1_OTHER_RULEBOOK` anchor vs design paste

Implementation (`variants.py` **506–508**):

```python
_V1_OTHER_RULEBOOK = (
    '  - "other": pre-match presenter, post-match presentation, '
    'drinks     break, anything else.'
)
```

Comment **504–508** states the design’s **`\`‑newline pasted anchor** does not match this repo’s **literal `PROMPT_V1`** concatenation. The **`assert _V1_OTHER_RULEBOOK in PROMPT_V6C`** (**520–521**) ensures the replace is anchored to **what V6c actually contains**.  

**Interpretation:** **not** substantive intent drift vs §4 — **operational** anchoring differs from Composer copy-paste appendix. If design doc Appendix still shows **`drinks \\` newline `break`**, treat that as **documentation cleanup**, not runtime bug.

---

## §3 V6c closeup preservation verification

### 3.1 Byte‑identity requirement

Design §4.5 / §7.b: **`_V6C_CLOSEUP_EXAMPLE`** must survive in **`PROMPT_V6D`** unchanged.

- **Module‑level assertion:** **`assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6D`** (**531–532**).
- **`test_recent_fixes.py`** — **`test_v6d_preserves_v6c_closeup_example`** (**440–448**): requires **`_unescape(_V6C_CLOSEUP_EXAMPLE) in VARIANTS["V6d"]["prompt"]`**.

So the **escaped** PROMPT fragment is unchanged; **`_unescape`** only affects **`{{` / `}}`** in outputs — same as other variants.

### 3.2 String equality sanity (optional)

Because **`PROMPT_V6D`** is only **`PROMPT_V6C`** with **two replacements** targeting **bowlers_end** line and **`other`** rulebook, **`_unescape(V6c closeup excerpt)` ⊆ `VARIANTS["V6d"]["prompt"]`** follows from the above; no additional replace touches the closeup line.

---

## §4 `f600` hypothesis analysis (against actual prompt text)

**Frame characterization (from discriminate report):** `pbks_rr_f600`, **`powerplay_inn1`**, V6c → **`side_on`**, V6d → **`bowlers_end`** (stable across ensemble).

**H1 — Design insufficient for side_on / boundary fielding (exclude only atmospheric)**

- **Evidence:** Edit A excludes **only** **`NOT atmospheric/crowd/stadium … without … visible cricket pitch`**. Boundary chase shots often include **pitch** or **readable depth** cues; model may **fail** this NOT clause altogether.
- **Design itself** scopes f941 escalation to **no-pitch / atmospheric** (design §2, §5 table). **`f600` is outside that class.**
- **Plausibility:** **High.**

**H2 — Implementation missing or softened negative test**

- **Evidence:** Substrings **`NOT atmospheric/crowd/stadium`** and **`those are "other"`** appear in **`VARIANTS["V6d"]["prompt"]`**; **`test_v6d_includes_bowlers_end_negative_test`** enforces both.
- **Plausibility:** **Low — rejected.**

**H3 — Strong `bowlers_end` attractor; negative test overridden**

- **Evidence:** RULEBOOK **`"bowlers_end"`** still describes delivery camera (**`variants.py`** **85–89**); **`"side_on"`** mentions **boundary chase** (**90–91**) but **has no STEP‑1 format example**. V6d retains **three** STEP‑1 examples (**bowlers_end / closeup / graphic** — **`_V5_STEP1_BLOCK`**, **`PROMPT_V5`** lineage). Combined with V4‑style dominance of Example 1, misreading **delivery geometry** yields **`bowlers_end`** even when negatives are present.
- **Plausibility:** **High**, **complementary to H1** (not mutually exclusive).

**H1 vs H4 (novel)**

- Neither H1/H2/H3 alone requires a fourth hypothesis: **combined corpus** disagreement rate **6%** is consistent with rare geometry confusion; no need to posit off‑prompt mechanism unless provider errors correlate with specific frames (**out of audit scope**).

---

## §5 Recommended action

| Track | Owner | Concrete next Composer 2 directions |
|------|-------|-------------------------------------|
| **V6e (preferred)** | Design | In **`scout_v6d_design.md` successor**, add **explicit side_on preservation** contrasting **delivery camera down the lane** vs **square / lateral tracking / rope chase** — e.g. a **third negative clause on the bowlers_end STEP‑1 line** (`NOT … side-on boundary tracking / square camera showing fielder running parallel to rope — classify as side_on`), **or** a **single bullet** reinforcing **`side_on` rulebook** with “**not bowlers_end** when …” (**avoid** fourth STEP‑1 example unless A/B gated — design §4.2 warns). |
| **Fix V6d** | Impl | **Only** if QA finds substring mismatch vs spec — **this audit finds none** for Edits A/B meaning. Optional: align **`scout_v6d_design.md` §7.b** `_V1_OTHER_RULEBOOK` paste with **`variants.py:506`** to avoid stop‑condition S1 false alarms. |
| **Hybrid** | Both | Implement **V6e** discriminators; **keep** assertions **`_V6C_CLOSEUP_EXAMPLE in PROMPT_V6D`** and replicate **`f205`/`f748` smoke** subset on combined corpus slices. |

**Validation criteria for V6e**

- **`pbks_rr_f600`** → **`side_on`** (or consensus with human adjudication once labeled).
- **No regression:** **`f941`‑class** still **≠ `bowlers_end`**; **`f205`/`f748`** **`closeup`** preserved (existing tests + spot shadow).

---

## §6 Cross-references

| Resource | Role |
|---------|------|
| `files/docs/investigations/scout_v6d_design.md` | Canonical spec §4 strategy, §7.b paste |
| **`files/shadow_eval/variants.py`** **457–533** (`PROMPT_V6D`, `_V6D_*`) | **Implementation under audit** |
| `files/test_recent_fixes.py` `test_v6d_preserves_v6c_closeup_example`, `test_v6d_includes_bowlers_end_negative_test`, `test_v6d_other_rulebook_includes_f941_signature` | Drift guards |
| `files/docs/investigations/combined_corpus_shadow_v6c_v6d_2026-04-30.md` | Multi‑match corpus + methodology |
| `files/docs/discriminating_frames_v6c_vs_v6d_combined.md` | **`f600`** disagreement row |

---

## §7 Stop-condition checklist (audit)

| ID | Trigger | Result |
|----|---------|--------|
| S1 | `PROMPT_V6D` missing | **N/A — located.** |
| S2 | Closeup preservation test absent | **N/A — present** (`test_v6d_preserves_v6c_closeup_example`). |
| S3 | Wholesale divergence | **N/A —** two substitutions only; asserts hold. |
| S4 | H1/H2/H3 insufficient | **N/A — H1+H3 explain `f600` without new mechanism.**
