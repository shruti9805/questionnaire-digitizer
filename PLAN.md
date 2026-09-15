# Questionnaire Digitizer — Build Plan
Last updated: 2026-09-15 | Current stage: 2 | Current component: 2 (schema ingestion)

## 1. Product summary
A local desktop/web tool that turns scanned paper research questionnaires (bilingual,
Likert-scale + demographic checkboxes) into structured Excel output, for a PhD research study
where the question set changes each research phase but the form's structure does not. See
PRODUCT.md for full detail.

## 2. Constraints (from Stage 0)
- **Team**: Claude builds and maintains solo, one-off. No future-hire optimization needed.
- **Platforms**: Desktop/web tool. No app store distribution.
- **Native depth**: None required — file import (PDF/docx) and a local web UI is sufficient.
- **Timeline**: No pressure; optimize for correctness and a solid review/correction workflow.
- **Scale**: Hundreds of respondents per phase. A real local database is worthwhile; no server
  infrastructure needed.
- **Distribution**: Local-only, run by the researcher on their own machine. [INFERRED: "desktop/
  web tool" + "just me building it" rules out store distribution and multi-tenant hosting]
- **Non-negotiable**: Respondents are minors. Data must stay on the researcher's machine.
- **Scope cut (2026-09-15, user decision):** the vision/API-based handwriting-reading step was cut
  from v1 after the user asked about API cost and clarified their Claude Pro subscription doesn't
  cover standalone API usage — a separate, billed API key would be needed for that step. Rather
  than take on that cost now, v1 captures only the Likert checkbox grid (fully local, free,
  deterministic). Demographic fields are entered manually by the researcher. This makes v1 fully
  offline — no API key, no network dependency, no per-respondent cost. See DR-002 (deferred).

## 3. Success criteria
- A researcher can import a phase's `.docx` template and the app correctly extracts the ordered
  {SrNo, Code, Statement} list and demographic field list with zero manual re-entry.
- A researcher can import a scanned PDF (Adobe-Scan-style booklet spread) and get back an Excel
  file (Demographics / Likert long-format / Wide-format sheets) matching the structure hand-built
  this session, for a batch of respondents in one run — with Likert values auto-captured and
  demographic fields entered by the researcher in a short on-screen form per respondent.
- Checkbox-column detection matches manual visual verification on a held-out sample of rows with
  no disagreement after the review pass.
- Every Likert field the pipeline is not confident about (ambiguous column, missing mark,
  page-break split) is surfaced in a review screen before export, not silently guessed.
- Processing a ~70-item, 6-image questionnaire completes end-to-end (import → review-ready) in
  under 15 seconds on a normal laptop — this is now pure local image processing, no external API
  call in the loop.

## 4. Technology decisions
| # | Decision | Choice | Confidence |
|---|---|---|---|
| DR-001 | App shell / UI | Streamlit 1.50.0 | High |
| DR-002 | Handwriting/text reading | **Deferred to v2** — manual entry by researcher in v1, see below | High (on the deferral) |
| DR-003 | Checkbox-grid detection | Ported/generalized version of this session's Pillow+NumPy pipeline | High |
| DR-004 | Schema ingestion | `python-docx` 1.2.0 reading the phase's `.docx` table | High |
| DR-005 | Storage | SQLite (stdlib `sqlite3`) | High |
| DR-006 | PDF rendering | `pdftoppm` (poppler) via subprocess, already installed this session | High |
| DR-007 | Export | `openpyxl` 3.1.5, reusing this session's workbook structure | High |

## 5. Architecture

```
.docx template (per phase)  ──▶  Schema parser (python-docx)  ──▶  SQLite: phases, items, demo_fields
                                                                          │
scanned PDF (per batch)     ──▶  pdftoppm @300dpi ──▶ page PNGs          │
                                                          │               │
                                                          ▼               │
                                        Checkbox pipeline (local, no API) │
                                        - gridline detection              │
                                        - ink-color clustering            │
                                        - column binning                  │
                                        - boundary/duplicate resolution   │
                                                          │               │
                                                          └───────┬───────┘
                                                                  ▼
                                          SQLite: responses, response_items,
                                          each Likert field tagged confidence: ok / low / conflict
                                                                  │
                                                                  ▼
                                          Review screen (Streamlit):
                                          - human confirms/edits anything not "ok"
                                          - demographic fields (school, district, class, gender,
                                            signature present?, etc.) typed in by the researcher
                                            while viewing the source page image alongside the form
                                                                  │
                                                                  ▼
                                          Export (openpyxl) — Demographics / Likert_Responses /
                                          Wide_Format / Extraction_Notes, one workbook per batch
                                          or cumulative across a phase
```

**On-device (no API call, deterministic, free, fast — this is all of v1's processing):**
- PDF→PNG rendering
- Gridline detection (longest-contiguous-dark-run projection)
- Ink-pixel isolation (RGB channel-difference mask, thresholds tuned this session)
- Row clustering + column binning
- Page-break duplicate/split resolution (compare adjacent-half row counts against schema-expected
  counts; when they disagree, flag for manual review instead of guessing)

**Deferred to v2 (would need a separately-billed Claude API key — see DR-002):**
- Demographic field transcription (school name, district, signature, free text) — v1 has the
  researcher type these in by hand instead
- A structure sanity check per page (did the schema's item order actually match what's printed?)

**Human-in-the-loop (Streamlit review UI):**
- Every Likert field has its confidence surfaced (ok/low/conflict) with the source crop shown
  inline so the researcher can confirm or type a correction in seconds, rather than re-deriving it
  from the raw PDF. This directly generalizes what I did by hand this session for DS_6 and AS_2.
- Demographic fields are a short, plain data-entry form next to the page image — not automated in
  v1, but still faster than switching to a separate spreadsheet.

## 6. Component breakdown

| # | Component | Why now | Depends on | Done when | Status |
|---|---|---|---|---|---|
| 1 | Walking skeleton | Proves toolchain: Streamlit app runs, SQLite created, file upload works | — | A blank Streamlit app launches locally, accepts a .docx upload, and writes a row to SQLite | Done |
| 2 | Schema ingestion | Needed before any scan can be interpreted; low technical risk but blocks everything else | 1 | Uploading the real bilingual .docx produces the correct 71-item schema + 8 demographic fields in SQLite, verified against this session's hand-transcribed list | Not started |
| 3 | Checkbox pipeline port | Highest technical risk — must generalize the session's hand-tuned, single-document pipeline to arbitrary page geometry without a human re-tuning thresholds each time | 1 | Running the pipeline on the same sample PDF used this session reproduces the same 71 values without manual threshold changes, including correctly flagging the DS_6 and AS_2 boundary cases rather than silently guessing | Not started |
| 4 | Review UI | Where the human-in-the-loop promise is delivered, and where demographic fields get entered (manually, per the v1 scope cut) | 2,3 | For the sample PDF, every Likert field the pipeline was unsure about is shown with its source crop; demographic fields have a working entry form next to the page image; both write back to SQLite | Not started |
| 5 | Excel export | Ties it together into the actual deliverable | 4 | Exporting the sample PDF's reviewed response produces a workbook matching this session's hand-built one in structure and values | Not started |
| 6 | Batch mode | Needed for "hundreds of respondents", not just one | 2–5 | Importing multiple scanned PDFs under one phase produces one cumulative export with one row per respondent | Not started |

Order reasoning: 1 and 2 are cheap and de-risk the schema side entirely. 3 is the one genuinely
uncertain technical bet left after cutting the vision-API step (component 4 in the prior version of
this plan) — does the geometry pipeline generalize past one hand-tuned document? — built and proven
against the real sample data from this session before any UI is built around it. 4–6 are
comparatively low-risk assembly once 3 is proven.

## 7. Risks

| Risk | Likelihood | Impact | Early signal | Mitigation |
|---|---|---|---|---|
| Checkbox pipeline was hand-tuned on one document; thresholds (dark-pixel cutoffs, ink-color cutoffs, min-run lengths) may not generalize to different scan quality, pen color, or table styling in other phases | Medium | High — silent wrong answers are worse than no automation | Component 3's Done-when explicitly requires reproducing this session's values without retuning; if a new document needs threshold changes, that's a real signal to build calibration into the UI (e.g., "sample a few known rows, auto-tune") rather than hardcoding | Build a threshold-calibration step from the start rather than hardcoding this session's numbers; always cross-check row counts against the schema and flag mismatches instead of forcing a guess |
| Manual demographic entry is tedious/error-prone at "hundreds of respondents" scale without any automation | Medium | Medium | Researcher feedback once component 4 is in real use | Keep the entry form fast (tab order, sensible defaults, remembers the last-used school/district for the same batch) since this is now a standing part of the workflow, not a stopgap; revisit DR-002 (vision API) as a v2 if this becomes the bottleneck |
| Respondent data sensitivity (minors) | Low | High | N/A until built | Even with v1 fully offline, keep the SQLite file local and document this explicitly for the researcher; re-examine if v2 adds the API call, since that would send page images off-machine |

## 8. Out of scope (v1)
- Automatic reading of handwritten/demographic fields, signatures, and free text (deferred to v2 —
  would need a separately-billed Claude API key; cut after the user's cost question, see DR-002)
- Mobile app / camera capture in the field (noted as a possible v2 if the researcher's workflow
  turns out to need in-field capture rather than "scan later, process in batch")
- Multi-user / hosted deployment
- Statistical analysis beyond producing the export (that's the researcher's existing stats
  software's job)
- Automatic detection of a *new* form structure the researcher hasn't described (the app assumes
  the fixed structure documented in PRODUCT.md — consent, demographics table, Likert table with
  SrNo/Code/Statement/1-5 columns)

## 9. Decision log

### DR-001: App shell / UI framework
**Status:** Proposed
**Date:** 2026-09-15

**Context:** Solo Claude-maintained, desktop/web tool, no store distribution, needs a review UI
where a human looks at image crops next to detected values and corrects them, plus file
upload (.docx, PDF) and a batch/export flow. No existing frontend or design system to match.

**Criteria (set before evaluation):**
1. Speed/reliability of solo build — weight: high — the team constraint is "just me, one-off";
   a stack that needs a separate frontend+backend+API contract multiplies surface area for bugs
   with no offsetting benefit here.
2. Fit for image-heavy review UI (show crop, show buttons, take correction) — weight: high — this
   is the actual hard UI requirement, not a generic CRUD form.
3. Reuse of this session's already-verified Python pipeline (Pillow/NumPy/openpyxl/python-docx)
   — weight: high — rewriting a proven pipeline into another language is pure risk with no
   benefit given there's no cross-platform/native requirement.
4. Long-term maintainability by "just me" — weight: medium.

**Options considered:**
| Option | Solo build speed | Image review UI fit | Pipeline reuse | Notes |
|---|---|---|---|---|
| Streamlit | Very high — single Python file per page, built-in file upload/image/data widgets | Good — `st.image`, `st.columns`, `st.button` cover the review screen directly | Direct — same process, same language | No auth/multi-user story, fine for local single-user tool |
| Flutter (desktop or mobile) | Low — separate language/toolchain from the pipeline, would need to reimplement or wrap the Python pipeline behind a service boundary | Good widget support, but built from scratch | None — pipeline is Python; would need an IPC/HTTP boundary | Matches the user's passing mention, but the stated platform need is "desktop/web," not mobile, and native depth is none |
| React/Next.js + FastAPI backend | Medium — two codebases, an API contract, more moving parts | Very good, most flexible | Backend reuses pipeline directly, frontend does not | More power/polish than this tool needs at this scale; more to maintain solo for no stated benefit |

**Decision:** Streamlit, version 1.50.0 [VERIFIED: `pip index versions streamlit`, checked
2026-09-15]

**Why this wins:** The team constraint (solo, one-off) and the platform constraint (desktop/web,
no store) both point away from a multi-codebase stack. Streamlit lets the review UI, the pipeline,
and the export logic live in one Python codebase using libraries already proven this session,
which directly serves criteria 1 and 3. Its image/dataframe widgets are a close match for
criterion 2's actual requirement (crop + value + correction control).

**What we give up:** Visual polish and UI flexibility compared to a hand-built frontend; no path
to a native mobile app without a rewrite of the UI layer (though the pipeline underneath would be
reusable behind an API if that's ever needed); Streamlit's single-process model isn't built for
concurrent multi-user access (not a stated requirement here).

**What would change this:** If the researcher later needs in-field mobile capture by research
assistants (out of scope for v1, noted above), or needs multiple people using the tool
concurrently over a network — either would justify revisiting toward a client/server split.

**Confidence:** High.

---

### DR-002: Handwriting/text reading
**Status:** Accepted as the right approach, but **deferred out of v1 scope** on 2026-09-15 — the
user asked what the API would cost given they already have a Claude Pro subscription; once it was
clear Pro doesn't cover standalone API usage and a separate billed key would be needed, the user
chose to cut automatic handwriting reading from v1 entirely rather than pay for it, in favor of
manual entry (see PRODUCT.md and section 5/6/8 above). This record is kept because the technical
analysis remains correct and directly informs a v2 revisit — nothing below was wrong, the scope
was cut for a cost-ownership reason unrelated to the technical merits.
**Date:** 2026-09-15

**Context:** Demographic fields (school name, district, class, signature, free text) and a
structure sanity check need reading real handwriting and printed bilingual text off page images.
This session did this by having a multimodal model (me) look directly at rendered page crops —
no OCR engine was used or needed, and that approach's accuracy is the baseline to match.

**Criteria (set before evaluation):**
1. Demonstrated accuracy on this exact kind of content (mixed print/cursive, bilingual, real scan
   noise) — weight: high — this was the entire reason OCR was rejected this session.
2. Structured, checkable output (so the app can programmatically tell "which field is this") —
   weight: high.
3. Cost/latency at hundreds-of-respondents scale — weight: medium — real number is [UNKNOWN],
   flagged as a risk in section 7, to be measured in component 4.

**Options considered:**
| Option | Accuracy on this content | Structured output | Cost/latency known | Notes |
|---|---|---|---|---|
| Traditional OCR (Tesseract etc.) | Low — this session explicitly found checkbox/handwriting reading unreliable at a glance for a pure pixel/text engine; OCR is worse still for cursive signatures and mixed Hindi/English | Poor — needs heavy post-processing | Fast/free | Rejected in this session's own validated approach; no reason to revisit without new evidence |
| Anthropic API (Claude, vision), `anthropic` SDK | High — this is literally the method already validated this session (via direct multimodal reading) | Good — can be prompted to return structured JSON per field | ~$0.04-0.05/respondent (Opus 5) or ~$0.015-0.02/respondent (Sonnet 5) [VERIFIED: platform.claude.com/docs/en/build-with-claude/vision, checked 2026-09-15] — negligible at hundreds-of-respondents scale; latency not yet measured | Directly continues the proven approach; the SDK is the programmatic equivalent of what was done by hand this session |
| Another vision LLM API | [UNKNOWN] — unverified for this content | [UNKNOWN] | [UNKNOWN] | No evidence gathered this session; would need its own validation pass for no clear benefit over the option already proven to work |

**Decision:** Anthropic API (Claude, vision) via the `anthropic` Python SDK, version 0.125.0
[VERIFIED: `pip index versions anthropic`, checked 2026-09-15]

**Why this wins:** Criterion 1 is decisive — this is the exact method already validated against
the real sample document this session, not a new bet. Structured JSON output is straightforward to
prompt for with a vision-capable Claude model.

**What we give up:** A per-respondent API cost and a hard network dependency — this tool cannot
run fully offline. Also ties the app to one vendor; switching later would need re-validation.

**What would change this:** If measured cost/latency in component 4 turns out to be prohibitive
at hundreds-of-respondents scale, worth comparing against a cheaper/smaller vision model for the
demographic-field-only calls (the checkbox grid never needs this call at all).

**Confidence:** High — accuracy already demonstrated this session, and cost is now verified
negligible at the stated scale. Only latency (not cost) remains unmeasured, pending component 4.

---

### DR-003: Storage
**Status:** Proposed
**Date:** 2026-09-15

**Context:** Hundreds of respondents per phase, potentially multiple phases over the life of the
study, need to persist schema + raw detections + confidence flags + human corrections + export
history, queryable and re-exportable without re-processing scans.

**Criteria (set before evaluation):**
1. Zero operational overhead for a solo local tool — weight: high — no server to run or maintain.
2. Enough structure to query "all low-confidence fields across a batch" for the review UI —
   weight: high.
3. Durable enough that hundreds of respondents' worth of manually-reviewed data isn't at risk from
   a crash mid-write — weight: medium.

**Options considered:**
| Option | Ops overhead | Query structure | Durability | Notes |
|---|---|---|---|---|
| Flat files (JSON per respondent) | None to run, but no query layer — would need to hand-roll scanning every file for "low confidence" lookups | Poor | Medium — file-level, no transactional guarantee | Fine for tiny scale, painful once "flag everything low-confidence across a batch" is a real UI need |
| SQLite (stdlib `sqlite3`) | None — a single file, no server process | Good — real SQL, indexes, joins across phases/respondents/items | Good — ACID transactions | Already the natural fit for "hundreds of rows, one file, no server" |
| Postgres/other server DB | Real — a process to run and keep alive | Best | Best | No stated need justifies the operational cost at this scale for a solo local tool |

**Decision:** SQLite via Python's stdlib `sqlite3`.

**Why this wins:** Matches criterion 1 exactly (zero install, ships with Python) while satisfying
criteria 2 and 3 far better than flat files, with no operational cost compared to a server DB that
this scale and single-user context doesn't need.

**What we give up:** No concurrent multi-writer support (not a stated requirement — single
researcher, local tool) and no built-in remote access (also not a stated requirement).

**What would change this:** Multi-user concurrent access or a hosted/shared deployment — neither
in scope for v1.

**Confidence:** High.

---

### DR-004: Checkbox-grid detection approach
**Status:** Proposed
**Date:** 2026-09-15

**Context:** This session hand-built and validated a Pillow+NumPy pipeline (gridline detection via
longest-contiguous-dark-run, blue-ink isolation via RGB channel difference, y-clustering,
x-centroid column binning) against the real sample PDF, catching and correctly resolving two
page-break edge cases. The open question is packaging, not the algorithm itself.

**Criteria (set before evaluation):**
1. Preserve the validated accuracy — weight: high — do not regress from what was proven this
   session.
2. Generalize across documents without per-document manual threshold tuning — weight: high — this
   is the actual v1 risk (see section 7).
3. Runs locally, no API cost, since it's pure geometry/color — weight: medium.

**Options considered:**
| Option | Preserves accuracy | Generalizes | Local/free | Notes |
|---|---|---|---|---|
| Port this session's script as-is, hardcoded thresholds | Yes, on this document | No — thresholds (e.g. `b-r>35`) were tuned by inspecting this specific scan's ink color | Yes | Fastest to build, but component 3's Done-when will likely fail on any other document without generalization work |
| Same algorithm, with a calibration step (sample a handful of known-answer rows or a printed color reference, derive thresholds per-document) | Yes, plus adapts to scan variation | Much better | Yes | More work, but directly addresses the top risk in section 7 |
| Replace geometry approach with an ML checkbox-detection model | [UNKNOWN] — unvalidated for this content | [UNKNOWN] | Likely still local | No evidence this session that the geometry approach is insufficient; would be replacing a proven method with an unproven one for no demonstrated reason |

**Decision:** Port this session's algorithm, but build it as a calibration-first pipeline (derive
gridline and ink thresholds per document/batch rather than hardcoding this session's numbers), with
row-count-vs-schema cross-validation kept as a first-class step (this is what caught both boundary
cases this session, not luck).

**Why this wins:** Directly serves criterion 1 (same proven algorithm) while treating criterion 2
as a real requirement instead of an afterthought — hardcoding would pass this session's document
and silently fail the next phase's scan.

**What we give up:** More implementation work upfront than a hardcoded port.

**What would change this:** If calibration proves unreliable in practice (component 3), fall back
to prompting the vision LLM for checkbox columns directly as a slower but more robust alternative
for the specific rows calibration can't resolve confidently — not a full replacement, since the
geometry approach's speed and zero cost are worth keeping for the confident majority of rows.

**Confidence:** Medium — the core algorithm is proven, the calibration generalization is not yet
tested on a second document.

## 10. Changelog
- 2026-09-15: Initial plan created from Stage 0 constraint interview and this session's hand-
  validated extraction pipeline.
- 2026-09-15: Cut automatic handwriting/demographic-field reading (DR-002) from v1 scope after the
  user asked about API cost and decided not to take on a separately-billed API key right now. v1
  is now fully local/offline: only the Likert checkbox grid is auto-extracted; demographic fields
  are entered manually via the review UI. Component breakdown reduced from 7 to 6 (vision
  integration component removed); success criteria, architecture diagram, and risks updated to
  match. DR-002's analysis is kept as a reference for a possible v2, not deleted.
- 2026-09-15: Component 1 (walking skeleton) done. `app.py` + `db.py` with the full v1 SQLite
  schema (phases/items/demo_fields/batches/responses/response_items, only `phases` exercised so
  far); verified by running the real Streamlit server (`streamlit run app.py`), confirming
  `/_stcore/health`, driving the live app in a browser and confirming a phase row written via
  `create_phase()` renders correctly in the "Phases stored so far" table. Not verified: clicking
  the actual file-drop widget end-to-end through browser automation (the available browser tooling
  has no programmatic file-input control) — the upload button's code path (`create_phase`) was
  instead verified directly, and the widget itself was confirmed to render and accept the intended
  file type. Git repo initialized for the project.
