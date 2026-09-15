"""Detect Likert checkbox values (1-5) from a scanned questionnaire PDF.

No OCR, no vision API - pure geometry + color, calibrated per document rather
than hardcoded, per PLAN.md DR-004. Two things generalize across documents by
construction rather than by hardcoded constants tuned on one scan:

1. Column gridlines are found via "longest contiguous run of dark pixels"
   projected onto each x column, restricted to the right half of the page
   (this template's answer grid is consistently right-aligned) - this finds
   the grid wherever it sits vertically on the page, no fixed y-region.
2. Ink is isolated by HSV saturation, thresholded per-document with Otsu's
   method applied to the *non-background* pixels in the detected grid region.
   This is pen-color-agnostic (works for blue, red, green ink) rather than
   assuming blue specifically, which was the actual hardcoded assumption in
   this session's original hand-built prototype (rejected here per DR-004).

Known limitation, not hidden: this cannot distinguish black/graphite marks
from printed black text by color alone. If a phase uses black pens, this
pipeline will under-detect and the row-count cross-check below should catch
it (falling back to full manual review) rather than silently miss marks.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image


# ---------- PDF -> page images ----------

def render_pdf_pages(pdf_path: str, out_dir: str, dpi: int = 300) -> list[str]:
    """Render every page of pdf_path to PNG via pdftoppm. Returns sorted paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = out / "page"
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), pdf_path, str(prefix)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr}")
    pages = sorted(out.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    if not pages:
        raise RuntimeError(f"pdftoppm produced no pages for {pdf_path}")
    return [str(p) for p in pages]


def split_halves(page_png_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Split a two-page-spread scan into (left, right) RGB arrays.
    A genuinely single-page (portrait, non-spread) scan is returned whole as
    the "right" half with an empty left half, detected by aspect ratio."""
    im = Image.open(page_png_path).convert("RGB")
    w, h = im.size
    if w < h:  # portrait single page, not a spread
        return np.zeros((1, 1, 3), dtype=np.uint8), np.array(im)
    left = np.array(im.crop((0, 0, w // 2, h)))
    right = np.array(im.crop((w // 2, 0, w, h)))
    return left, right


# ---------- gridline / column detection ----------

def _longest_run(mask_1d: np.ndarray) -> tuple[int, int, int]:
    """Returns (length, start_index, end_index_exclusive) of the longest run of True."""
    best_len = cur_len = 0
    best_start = cur_start = 0
    for i, v in enumerate(mask_1d):
        if v:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
        else:
            cur_len = 0
    return best_len, best_start, best_start + best_len


def find_answer_grid_columns(rgb: np.ndarray, min_run_frac: float = 0.14, right_frac: float = 0.5):
    """Find the 5 equal-width answer-column boundaries AND the table's
    vertical extent on a half-page image, using only the longest-contiguous-
    dark-run gridlines (real printed table borders span the whole table
    height in one unbroken run; paragraph text above/below does not).
    Returns (left, right, col_bounds[6], y_top, y_bottom) or None if no grid
    is found (e.g. a half with no Likert table on it)."""
    h, w, _ = rgb.shape
    gray = np.array(Image.fromarray(rgb).convert("L"))
    dark = gray < 235
    min_run = int(h * min_run_frac)
    x0 = int(w * right_frac)
    runs = {}
    for x in range(x0, w):
        length, start, end = _longest_run(dark[:, x])
        if length > min_run:
            runs[x] = (length, start, end)
    if not runs:
        return None
    xs = sorted(runs.keys())
    lines = []  # each: (x_center, y_start, y_end) of one gridline
    cur_xs, cur_starts, cur_ends = [xs[0]], [runs[xs[0]][1]], [runs[xs[0]][2]]
    for x in xs[1:]:
        if x - cur_xs[-1] <= 3:
            cur_xs.append(x)
            cur_starts.append(runs[x][1])
            cur_ends.append(runs[x][2])
        else:
            lines.append((int(np.mean(cur_xs)), int(np.mean(cur_starts)), int(np.mean(cur_ends))))
            cur_xs, cur_starts, cur_ends = [x], [runs[x][1]], [runs[x][2]]
    lines.append((int(np.mean(cur_xs)), int(np.mean(cur_starts)), int(np.mean(cur_ends))))

    xs_only = [l[0] for l in lines]
    left, right = min(xs_only), max(xs_only)
    if right - left < 20:  # degenerate: no real grid width found
        return None

    # Deliberately NOT trying to detect the table's exact vertical extent
    # here. These are phone-camera photos of a book spread (not flatbed
    # scans), and every geometric approach tried this session - longest
    # single-column dark run, union of first/last dark pixel, horizontal
    # line-density, multi-gridline quorum voting - was fragile against the
    # resulting perspective skew, each fixing one page's false positives
    # while breaking another page's true detections. The full half-page
    # height is searched instead (see detect_ink_mask / cluster_ticks),
    # and stray printed-text pixels are excluded there by pixel-count
    # (real ink blobs are reliably larger than any printed-text
    # antialiasing cluster - verified against this session's real sample).
    col_bounds = [left + (right - left) * i / 5 for i in range(6)]
    return left, right, col_bounds


# ---------- ink detection (calibrated, not hardcoded) ----------

def _otsu_threshold(values: np.ndarray, bins: int = 100) -> float:
    hist, edges = np.histogram(values, bins=bins, range=(0, 1))
    hist = hist.astype(float)
    total = hist.sum()
    if total == 0:
        return 0.2  # no dark pixels at all; harmless fallback, nothing will match anyway
    sum_all = np.sum(hist * np.arange(bins))
    sumB = wB = 0.0
    best_var, best_t = -1.0, bins // 2
    for i in range(bins):
        wB += hist[i]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += i * hist[i]
        mB, mF = sumB / wB, (sum_all - sumB) / wF
        var_between = wB * wF * (mB - mF) ** 2
        if var_between > best_var:
            best_var, best_t = var_between, i
    return float(edges[best_t])


def detect_ink_mask(rgb: np.ndarray, region: tuple[int, int, int, int]) -> tuple[np.ndarray, float]:
    """region = (y0, y1, x0, x1) - the answer-grid bounding box to calibrate
    and search within. Returns (boolean ink mask over the FULL image, the
    calibrated saturation threshold used) so callers can sanity-check it."""
    arr = rgb.astype(float) / 255.0
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    maxc, minc = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    sat = np.where(maxc > 0, (maxc - minc) / np.where(maxc == 0, 1, maxc), 0)
    val = maxc

    y0, y1, x0, x1 = region
    region_sat, region_val = sat[y0:y1, x0:x1], val[y0:y1, x0:x1]
    dark = region_val < 0.9
    if dark.sum() < 20:
        threshold = 0.2  # not enough data to calibrate; conservative default
    else:
        threshold = max(0.12, _otsu_threshold(region_sat[dark]))

    mask = (sat > threshold) & (val < 0.9)
    return mask, threshold


# ---------- clustering + binning ----------

@dataclass
class Tick:
    y: float
    x: float
    n_pixels: int
    col: int | None
    near_boundary: bool = False


# A tick whose x-centroid lands within this fraction of a column's width
# from a column boundary is treated as too close to call from geometry
# alone (verified against a real case this session: a centroid landed 0.2px
# from a boundary, putting it in the wrong column by the barest possible
# margin - exactly the "don't trust one threshold" failure mode the
# original hand-built process this pipeline replaces was designed against).
BOUNDARY_MARGIN_FRAC = 0.15


def cluster_ticks(mask: np.ndarray, region: tuple[int, int, int, int], col_bounds: list[float],
                   min_pixels: int = 80, y_gap: int = 15) -> list[Tick]:
    y0, y1, x0, x1 = region
    sub = mask[y0:y1, x0:x1]
    ys, xs = np.where(sub)
    if len(ys) == 0:
        return []
    ys, xs = ys + y0, xs + x0
    order = np.argsort(ys)
    ys, xs = ys[order], xs[order]

    clusters = []
    cur_y, cur_x = [ys[0]], [xs[0]]
    for y, x in zip(ys[1:], xs[1:]):
        if y - cur_y[-1] <= y_gap:
            cur_y.append(y)
            cur_x.append(x)
        else:
            clusters.append((float(np.mean(cur_y)), float(np.mean(cur_x)), len(cur_y)))
            cur_y, cur_x = [y], [x]
    clusters.append((float(np.mean(cur_y)), float(np.mean(cur_x)), len(cur_y)))

    col_width = (col_bounds[-1] - col_bounds[0]) / 5
    margin = col_width * BOUNDARY_MARGIN_FRAC

    def bincol(x):
        for i in range(5):
            hi = col_bounds[i + 1] + (5 if i == 4 else 0)
            if col_bounds[i] <= x < hi:
                return i + 1
        return None

    def is_near_boundary(x):
        # internal boundaries only (col_bounds[1..4]); the outer edges
        # (col_bounds[0] and [5]) aren't ambiguous - there's no adjacent
        # column on the other side to confuse it with
        return any(abs(x - b) < margin for b in col_bounds[1:5])

    return [
        Tick(y=cy, x=cx, n_pixels=n, col=bincol(cx), near_boundary=is_near_boundary(cx))
        for cy, cx, n in clusters if n >= min_pixels
    ]


# ---------- per-half and whole-document orchestration ----------

@dataclass
class HalfResult:
    source: str  # e.g. "page-3.png:R"
    half_height: int
    ticks: list[Tick] = field(default_factory=list)


def process_half(rgb: np.ndarray, source_label: str) -> HalfResult:
    h = rgb.shape[0]
    grid = find_answer_grid_columns(rgb)
    if grid is None:
        return HalfResult(source=source_label, half_height=h, ticks=[])
    left, right, col_bounds = grid
    region = (0, h, max(0, left - 10), min(rgb.shape[1], right + 10))
    mask, _threshold = detect_ink_mask(rgb, region)
    ticks = cluster_ticks(mask, region, col_bounds)
    return HalfResult(source=source_label, half_height=h, ticks=ticks)


TOP_FRACTION_FOR_CONTINUATION = 0.15  # empirically calibrated against this session's hand-verified sample


@dataclass
class AlignedItem:
    schema_index: int  # 0-based index into the schema item list
    value: int | None
    confidence: str  # "ok" | "low" | "conflict"
    note: str | None
    source: str
    y: float | None


@dataclass
class AlignmentResult:
    aligned: list[AlignedItem] | None  # None if counts couldn't be reconciled
    total_ticks_detected: int
    total_expected: int
    per_half: list[HalfResult]
    collapsed_boundaries: list[tuple[str, str]]  # (prev_half_source, half_source) pairs collapsed


def align_to_schema(per_half: list[HalfResult], n_expected: int) -> AlignmentResult:
    """Flattens per-half ticks into one sequence, collapsing a half's leading
    tick into the previous half's trailing tick when BOTH (a) the column
    values match and (b) the leading tick sits in the top
    TOP_FRACTION_FOR_CONTINUATION of its half's image - the geometric
    signature of a row whose text (and mark) was split across a page-break,
    verified against this session's real sample (5 true continuations, all
    in the top ~10-12%; one same-value-but-unrelated adjacent pair at ~22%,
    correctly excluded by this threshold).
    """
    flat: list[Tick] = []
    flat_source: list[str] = []
    collapsed_boundaries: list[tuple[str, str]] = []

    for half in per_half:
        ticks = list(half.ticks)
        if flat and ticks:
            prev_source = flat_source[-1]
            prev_tick = flat[-1]
            first = ticks[0]
            y_frac = first.y / half.half_height if half.half_height else 1.0
            if first.col is not None and first.col == prev_tick.col and y_frac < TOP_FRACTION_FOR_CONTINUATION:
                ticks = ticks[1:]  # drop the leading duplicate fragment
                collapsed_boundaries.append((prev_source, half.source))
        flat.extend(ticks)
        flat_source.extend([half.source] * len(ticks))

    total = len(flat)
    if total != n_expected:
        return AlignmentResult(
            aligned=None, total_ticks_detected=total, total_expected=n_expected,
            per_half=per_half, collapsed_boundaries=collapsed_boundaries,
        )

    boundary_sources = {s for pair in collapsed_boundaries for s in pair}
    aligned = []
    for i, (tick, source) in enumerate(zip(flat, flat_source)):
        is_boundary = source in boundary_sources and (
            (i > 0 and flat_source[i - 1] != source) or (i + 1 < len(flat_source) and flat_source[i + 1] != source)
        )
        notes = []
        if is_boundary:
            notes.append("adjacent to a collapsed page-break duplicate")
        if tick.near_boundary:
            notes.append("mark sits very close to a column boundary; column may be misread")
        confidence = "conflict" if tick.near_boundary else ("low" if is_boundary else "ok")
        aligned.append(
            AlignedItem(
                schema_index=i,
                value=tick.col,
                confidence=confidence,
                note="; ".join(notes) + " - please confirm" if notes else None,
                source=source,
                y=tick.y,
            )
        )
    return AlignmentResult(
        aligned=aligned, total_ticks_detected=total, total_expected=n_expected,
        per_half=per_half, collapsed_boundaries=collapsed_boundaries,
    )


def process_document(pdf_path: str, n_expected_items: int, work_dir: str) -> AlignmentResult:
    pages = render_pdf_pages(pdf_path, work_dir)
    per_half: list[HalfResult] = []
    for page_path in pages:
        left, right = split_halves(page_path)
        page_name = Path(page_path).name
        if left.shape != (1, 1, 3):
            per_half.append(process_half(left, f"{page_name}:L"))
        per_half.append(process_half(right, f"{page_name}:R"))
    return align_to_schema(per_half, n_expected_items)


@dataclass
class ItemResult:
    item_id: int
    code: str
    value: int | None
    confidence: str
    note: str | None
    source: str | None  # e.g. "page-3.png:R" - which rendered page/half the mark came from
    y: float | None  # y-coordinate within that half-page image, for crop generation


def align_document_to_items(pdf_path: str, items: list, work_dir: str) -> tuple[list[ItemResult] | None, AlignmentResult]:
    """items: sqlite3.Row-like objects with 'id' and 'code', in schema position
    order (as returned by db.get_items). Returns (per-item results or None if
    counts couldn't be reconciled, the raw AlignmentResult for diagnostics)."""
    result = process_document(pdf_path, len(items), work_dir)
    if result.aligned is None:
        return None, result
    item_results = [
        ItemResult(item_id=items[a.schema_index]["id"], code=items[a.schema_index]["code"],
                   value=a.value, confidence=a.confidence, note=a.note, source=a.source, y=a.y)
        for a in result.aligned
    ]
    return item_results, result


def list_rendered_pages(work_dir: str) -> list[str]:
    """Filenames (not full paths) of the rendered page PNGs in a batch's
    working directory, in page order."""
    pages = sorted(Path(work_dir).glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    return [p.name for p in pages]


def crop_source_region(work_dir: str, source: str, y: float, half_width_px: int = 130) -> Image.Image | None:
    """Re-derive the half-page image a detection came from (page filename +
    L/R side, e.g. "page-3.png:R") and crop a horizontal band around y for
    display in a review UI. Returns None if the source page is missing."""
    if not source or y is None:
        return None
    page_name, _, side = source.partition(":")
    page_path = Path(work_dir) / page_name
    if not page_path.exists():
        return None
    left, right = split_halves(str(page_path))
    rgb = left if side == "L" else right
    h = rgb.shape[0]
    y0, y1 = max(0, int(y) - half_width_px), min(h, int(y) + half_width_px)
    return Image.fromarray(rgb[y0:y1, :])
