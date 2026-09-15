# Questionnaire Digitizer — Product

## What it is
A tool that turns scanned paper research questionnaires (photographed booklet spreads, PDF) into
structured spreadsheet data, for a PhD research study on digital technology, school environment,
and education quality (researcher: Mridul Rathi, BITS Pilani).

## Who it's for
The researcher (and possibly research assistants) who collect paper questionnaires from students
across multiple school visits/phases, and currently need to manually transcribe hundreds of
handwritten Likert-scale ticks and demographic fields into a spreadsheet for statistical analysis.

## Why it's worth building
Manual transcription of ~70+ Likert items per respondent across potentially hundreds of
respondents is slow and error-prone. A validated hybrid pipeline (vision-model reading for
printed/handwritten text + pixel/geometry-based checkbox detection) was hand-verified this session
against a real sample (71 items, 100% match against manually cross-checked rows, two page-break
edge cases correctly resolved). Automating this pipeline removes the manual-transcription
bottleneck while keeping a human in the loop for anything low-confidence.

## The form, structurally (constant across phases)
Each research "phase" has its own Word (.docx) master template, which is what the researcher
prints to produce the paper questionnaire. Structure is fixed:
- Part 0: Parent/guardian consent (checkbox + signature + date + place)
- Part A: Demographic info table (school name, district/block, class/grade, school attendance
  [4-option checkbox], gender [3-option checkbox], family income [4-option checkbox],
  extracurricular Y/N, digital access Y/N)
- Part B: A Likert table with columns SrNo | Code | Statement (English/Hindi) | 1 | 2 | 3 | 4 | 5,
  one printed row per item, respondent marks one of 5 boxes per row.

What varies phase to phase: the number of Likert items, their Code labels, and their statement
text — i.e., the *content* of Part B's rows, not its shape.

## Core workflow (v1 scope)
1. Researcher imports the phase's .docx template once (defines the schema: demographic field list
   + ordered list of {SrNo, Code, Statement}).
2. Researcher scans/photographs a filled questionnaire (or a batch) and imports the PDF/images.
3. App processes each response: Likert values (the 1-5 checkbox grid) are extracted automatically
   via local image processing — no handwriting recognition, no external API call.
4. App surfaces anything uncertain about the checkbox extraction (low-confidence column reads,
   blank/skipped items, page-break split marks) for a quick human confirm/correct pass, and
   presents a simple form for the researcher to type in the demographic fields (school, district,
   class, gender, etc.) by hand while looking at the same page image.
5. Export: one row per respondent to Excel (wide format for stats import), plus a long-format and
   a demographics sheet, matching the format already produced by hand this session.

**v1 explicitly does not attempt to read handwriting** (demographic fields, signatures, free text)
automatically — that would require a multimodal LLM API call, which is billed separately from a
Claude.ai/Pro subscription and was cut from scope for now. The researcher enters those fields
manually via a short on-screen form instead. This can be revisited as a v2 addition once there's
appetite for the (small, ~$5-15/phase) API cost. See PLAN.md DR-002.

## Constraints/context worth carrying into Stage 0
- Respondents are minors (school students) — data sensitivity matters even without formal
  regulatory scope; avoid sending identifying data anywhere it doesn't need to go, and keep
  researcher in control of storage.
- v1 is fully local/offline by construction: no API key, no per-respondent cost, no network
  dependency. This was a deliberate scope cut (see above) to avoid API billing separate from the
  researcher's existing Claude Pro subscription. A future v2 could add automatic handwriting
  reading via the Claude API if that tradeoff becomes worth it.
- Real sample scans are phone-camera "booklet spread" PDFs (Adobe Scan), two printed pages per
  image, with real-world skew/lighting variation — not clean flatbed scans.

## Deployment (added 2026-09-15, see PLAN.md changelog for the full decision trail)
The app is deployed for a small named team (the researcher + research assistants), not the public,
on Streamlit Community Cloud (free tier). This changed the storage model, decided through explicit
tradeoffs with the user rather than assumed:

- **Phase schemas** (parsed from a phase's .docx: `phases`/`items`/`demo_fields`) are the one thing
  that must survive a restart. Streamlit Cloud's local disk is wiped on every restart/redeploy, so
  instead of standing up an external database for what's a small, rarely-changing amount of data,
  each phase's parsed schema is committed to the repo as JSON (`schemas/*.json`, produced by
  `dump_schema.py`) and re-loaded into local SQLite on every app startup (`schema_loader.py`). The
  git repo is the actual source of truth; local SQLite is just a cache rebuilt each run.
- **Response/batch data** (`batches`/`responses`/`response_items`/`response_demo_values`) is
  explicitly NOT persisted beyond local disk. The user's own stated workflow is process → review →
  export within one sitting, with the downloaded Excel file as the durable record — so losing
  in-progress (not yet exported) work on an unexpected restart is an accepted tradeoff, not a bug.
  Concretely: don't leave a batch half-reviewed for long stretches; finish and download before
  walking away.
- **Adding a new phase once deployed**: send the researcher's .docx to a Claude session (this
  workflow, not a feature in the app itself), which runs `dump_schema.py`, commits the resulting
  JSON, and pushes — Streamlit Cloud auto-redeploys with the new phase available. A GitHub-API
  self-service alternative (the running app committing its own schema updates) was considered and
  explicitly rejected: it would need a repo-write credential living in the hosted app plus a new
  class of failure modes, for something the user described as infrequent enough not to justify it.
- **Access control**: Streamlit Community Cloud's native private-app setting (specific email
  addresses as allowed viewers, signed in via Google OAuth or a magic link) - no auth code in the
  app itself.
- Free-tier alternatives were checked and ruled out with dated evidence (see PLAN.md): Railway and
  Fly.io no longer have real always-on free tiers as of 2026; Render's free tier explicitly wipes
  local disk on every restart, same problem as Streamlit Cloud without a workaround.
