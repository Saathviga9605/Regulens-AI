"""Visual stages of the cross-case reuse cascade: page rendering, perceptual hashing (L2) and geometric
verification with a residual difference map (L3).

L2 — ``phash_dct_v2``: the page is rendered in greyscale; if it looks like a photographed sheet (a bright
quadrilateral covering 30–97 % of the frame on a darker background) it is rectified to a rectangle; it is then
cropped to its content box, resized to 32×32 with area averaging, transformed
with a 2-D DCT, and the 8×8 low-frequency block (DC excluded from the median) is thresholded at its median → 64
bits. Hashes are computed for the page rotated by 0/90/180/270°, so a rotated scan can still be retrieved.
Hamming distance between hashes is the raw metric. It is a *candidate-retrieval* signal only.

L3 — ``orb_ransac_v1``: ORB keypoints/descriptors (OpenCV) on both rendered pages, brute-force Hamming kNN
matching with Lowe's ratio test, then a RANSAC homography. Reported: keypoints, tentative correspondences,
inliers, inlier ratio, spatial coverage of inliers over the content area, the transform, and a status of
``verified`` / ``not_verified`` / ``inconclusive`` / ``unavailable``. When verified, page B is warped onto page A
and ink masks are compared cell by cell to locate *localized differences* (e.g. a changed certificate number on
an otherwise identical layout). Nothing here establishes authenticity or intent.

OpenCV is optional at import time: if it is missing, L3 reports ``unavailable`` and L2 falls back to a NumPy
area resize. A pHash result is never reported as geometric verification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pymupdf

try:  # pragma: no cover - exercised implicitly; absence is reported, not hidden
    import cv2

    CV2_VERSION: str | None = cv2.__version__
except Exception:  # noqa: BLE001
    cv2 = None
    CV2_VERSION = None

PHASH_VERSION = "phash_dct_v2"  # v2: photographed pages are rectified (page quad → rectangle) before hashing
GEOMETRIC_VERSION = "orb_ransac_v1"
RENDER_VERSION = "render_gray_v1"


@dataclass(frozen=True)
class VisualParams:
    """Rendering and verification parameters. Part of the versioned reuse configuration."""

    hash_dpi: int = 36
    verify_dpi: int = 150
    verify_max_side: int = 2000
    orb_features: int = 3000
    ratio_test: float = 0.75
    ransac_reproj_px: float = 5.0
    min_keypoints: int = 40
    coverage_grid: int = 6
    content_cell_ink: float = 0.03  # a coverage cell counts as content when ≥3% of its pixels are ink
    diff_grid: int = 12  # judged-cell bookkeeping
    diff_sigma: float = 2.0  # Gaussian blur (px) before differencing: tolerates sub-pixel shifts and scan noise
    diff_threshold: float = 70.0  # absolute intensity difference (0–255, after percentile normalisation)
    diff_min_region_px: int = 60  # a connected area of differing pixels at least this large is a localized difference
    diff_min_cell_ink: int = 40  # pixels of ink before a cell is judged


# --- rendering -----------------------------------------------------------------------------------

def render_gray(page: pymupdf.Page, dpi: int, max_side: int | None = None) -> np.ndarray:
    zoom = dpi / 72.0
    if max_side:
        longest = max(page.rect.width, page.rect.height) * zoom
        if longest > max_side:
            zoom *= max_side / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def render_png(pdf_bytes: bytes, page_number: int, dpi: int = 90, max_side: int = 1200) -> bytes:
    """PNG of one page (1-based) for the authorised comparison view."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_number < 1 or page_number > doc.page_count:
            raise IndexError(page_number)
        page = doc[page_number - 1]
        zoom = dpi / 72.0
        longest = max(page.rect.width, page.rect.height) * zoom
        if longest > max_side:
            zoom *= max_side / longest
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")


# --- L2 perceptual hash --------------------------------------------------------------------------

def _resize_area(img: np.ndarray, size: int) -> np.ndarray:
    if cv2 is not None:
        return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA).astype(np.float64)
    h, w = img.shape
    ys = np.linspace(0, h, size + 1).astype(int)
    xs = np.linspace(0, w, size + 1).astype(int)
    out = np.empty((size, size))
    for i in range(size):
        for j in range(size):
            block = img[ys[i]:max(ys[i + 1], ys[i] + 1), xs[j]:max(xs[j + 1], xs[j] + 1)]
            out[i, j] = block.mean()
    return out


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)[:, None]
    i = np.arange(n)[None, :]
    m = np.cos(np.pi * (2 * i + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
    m[0, :] = np.sqrt(1.0 / n)
    return m


_DCT32 = _dct_matrix(32)


def phash(img: np.ndarray) -> int:
    small = _resize_area(img, 32)
    coeffs = _DCT32 @ small @ _DCT32.T
    block = coeffs[:8, :8].flatten()
    median = np.median(block[1:])
    bits = 0
    for value in block:
        bits = (bits << 1) | int(value > median)
    return bits


def page_hashes(img: np.ndarray) -> list[str]:
    """Hex pHash for the page at 0°, 90°, 180°, 270° (clockwise)."""
    return [f"{phash(np.rot90(img, k=-k)):016x}" for k in range(4)]


def rectify_page(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Undo perspective for a photographed sheet: largest bright 4-point contour → rectangle. No-op otherwise."""
    if cv2 is None:
        return img, False
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img, False
    c = max(contours, key=cv2.contourArea)
    h, w = img.shape
    area = cv2.contourArea(c)
    if area < 0.3 * h * w or area > 0.97 * h * w:
        return img, False
    approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
    if len(approx) != 4:
        return img, False
    pts = approx.reshape(4, 2).astype(np.float32)
    s_, d_ = pts.sum(1), np.diff(pts, axis=1).ravel()
    tl, br, tr, bl = pts[np.argmin(s_)], pts[np.argmax(s_)], pts[np.argmin(d_)], pts[np.argmax(d_)]
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if out_w < 16 or out_h < 16:
        return img, False
    m = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]]))
    return cv2.warpPerspective(img, m, (out_w, out_h)), True


def content_box(img: np.ndarray, threshold: int = 200, pad: float = 0.01) -> np.ndarray:
    """Crop to the bounding box of visible content so margins added by rescaling or cropping matter less."""
    ys, xs = np.nonzero(img < threshold)
    if len(ys) < 20:
        return img
    h, w = img.shape
    py, px = int(h * pad), int(w * pad)
    return img[max(ys.min() - py, 0):min(ys.max() + py + 1, h), max(xs.min() - px, 0):min(xs.max() + px + 1, w)]


def ink_fraction(img: np.ndarray) -> float:
    return round(float((img < 160).mean()), 4)


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


@dataclass
class PageDescriptor:
    page_number: int
    width: float
    height: float
    hashes: list[str]  # [0°, 90°, 180°, 270°]
    ink: float
    rectified: bool = False


def describe_pages(pdf_bytes: bytes, params: VisualParams, max_pages: int) -> tuple[list[PageDescriptor], str | None]:
    """Per-page pHash descriptors. Returns (descriptors, failure_reason)."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.needs_pass:
                return [], "encrypted_pdf"
            out = []
            for index in range(min(doc.page_count, max_pages)):
                page = doc[index]
                img = render_gray(page, params.hash_dpi)
                flat, rectified = rectify_page(img)
                out.append(PageDescriptor(index + 1, round(page.rect.width, 1), round(page.rect.height, 1),
                                          page_hashes(content_box(flat)), ink_fraction(img), rectified))
            return out, None
    except Exception as exc:  # noqa: BLE001 - malformed input is reported, never raised into the scan
        return [], f"render_failed:{type(exc).__name__}"


def best_page_match(a: list[PageDescriptor], b: list[PageDescriptor], min_ink: float) -> dict | None:
    """Smallest Hamming distance between any page of A (0°) and any rotation of any page of B.

    Pages with almost no ink (blank or unreadable) are skipped: two blank pages hash alike and that is not
    evidence of shared content.
    """
    best = None
    for pa in a:
        if pa.ink < min_ink:
            continue
        for pb in b:
            if pb.ink < min_ink:
                continue
            for rotation, hb in enumerate(pb.hashes):
                d = hamming(pa.hashes[0], hb)
                if best is None or d < best["distance"]:
                    best = {"page_a": pa.page_number, "page_b": pb.page_number, "distance": d,
                            "rotation_b_degrees": rotation * 90}
    return best


# --- L3 geometric verification ---------------------------------------------------------------------

def _ink_mask(img: np.ndarray) -> np.ndarray:
    _, mask = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def _content_cells(mask: np.ndarray, grid: int, min_fraction: float) -> list[tuple[int, int]]:
    """Cells dense enough to be content (text, seals); thin rules and borders alone do not qualify."""
    h, w = mask.shape
    cells = []
    for i in range(grid):
        for j in range(grid):
            cell = mask[i * h // grid:(i + 1) * h // grid, j * w // grid:(j + 1) * w // grid]
            if cell.size and (cell > 0).mean() >= min_fraction:
                cells.append((i, j))
    return cells


def _estimate(img_a: np.ndarray, img_b: np.ndarray, params: VisualParams) -> dict:
    """One ORB → ratio test → RANSAC pass. Returns metrics plus private arrays (prefixed ``_``)."""
    orb = cv2.ORB_create(nfeatures=params.orb_features)
    kp_a, des_a = orb.detectAndCompute(img_a, None)
    kp_b, des_b = orb.detectAndCompute(img_b, None)
    out: dict = {"keypoints_a": len(kp_a), "keypoints_b": len(kp_b)}
    if des_a is None or des_b is None or len(kp_a) < params.min_keypoints or len(kp_b) < params.min_keypoints:
        return {**out, "status": "inconclusive", "tentative_matches": 0, "inliers": 0,
                "reason": "Too few keypoints (text-sparse, blank, low-resolution or degraded page)."}
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_a, des_b, k=2)
    good = [m for m, *rest in knn if rest and m.distance < params.ratio_test * rest[0].distance]
    out["tentative_matches"] = len(good)
    if len(good) < 8:
        return {**out, "status": "not_verified", "inliers": 0, "inlier_ratio": 0.0,
                "reason": "Too few tentative correspondences for a homography."}
    src = np.float32([kp_a[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_b[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, params.ransac_reproj_px)
    if homography is None or inlier_mask is None:
        return {**out, "status": "not_verified", "inliers": 0, "inlier_ratio": 0.0,
                "reason": "RANSAC found no consistent transformation."}
    det = float(np.linalg.det(homography[:2, :2]))
    scale = abs(det) ** 0.5
    out.update(inliers=int(inlier_mask.sum()), inlier_ratio=round(int(inlier_mask.sum()) / len(good), 4),
               transform={"type": "homography", "scale": round(scale, 4), "determinant": round(det, 4),
                          "plausible": det > 0 and 0.2 <= scale <= 5.0,
                          "matrix": [[round(v, 5) for v in row] for row in homography]},
               _src=src, _mask=inlier_mask, _h=homography, _scale=scale)
    out["status"] = "estimated"
    return out


def geometric_verify(pdf_a: bytes, page_a: int, pdf_b: bytes, page_b: int, params: VisualParams) -> dict:
    """ORB + RANSAC homography between page A and page B, plus a residual difference map when plausible.

    When the first pass finds a scale difference (e.g. a rescaled copy), page B is re-rendered at the matching
    resolution and the estimate repeated, so the residual comparison is not dominated by resampling artefacts.
    """
    result: dict = {"method": GEOMETRIC_VERSION, "detector": "ORB", "opencv_version": CV2_VERSION,
                    "page_a": page_a, "page_b": page_b}
    if cv2 is None:
        return {**result, "status": "unavailable", "reason": "OpenCV is not installed; geometric verification did not run."}
    started = time.perf_counter()
    elapsed = lambda: round((time.perf_counter() - started) * 1000, 1)  # noqa: E731
    try:
        with pymupdf.open(stream=pdf_a, filetype="pdf") as da, pymupdf.open(stream=pdf_b, filetype="pdf") as db:
            img_a = render_gray(da[page_a - 1], params.verify_dpi, params.verify_max_side)
            img_b = render_gray(db[page_b - 1], params.verify_dpi, params.verify_max_side)
            est = _estimate(img_a, img_b, params)
            if est["status"] == "estimated" and est["transform"]["plausible"] and abs(est["_scale"] - 1) > 0.06:
                dpi_b = params.verify_dpi / est["_scale"]
                img_b2 = render_gray(db[page_b - 1], dpi_b, int(params.verify_max_side / est["_scale"]))
                est2 = _estimate(img_a, img_b2, params)
                if est2["status"] == "estimated" and est2["transform"]["plausible"]:
                    result["scale_matched_pass"] = {"first_pass_scale": round(est["_scale"], 4),
                                                    "page_b_render_dpi": round(dpi_b, 1)}
                    est, img_b = est2, img_b2
    except Exception as exc:  # noqa: BLE001
        return {**result, "status": "inconclusive", "reason": f"Page could not be rendered ({type(exc).__name__})."}

    if est["status"] != "estimated":
        return {**result, **est, "elapsed_ms": elapsed()}
    mask_a = _ink_mask(img_a)
    content = _content_cells(mask_a, params.coverage_grid, params.content_cell_ink)
    h, w = img_a.shape
    covered = set()
    for (x, y), keep in zip(est["_src"].reshape(-1, 2), est["_mask"].ravel()):
        if keep:
            covered.add((min(int(y * params.coverage_grid / h), params.coverage_grid - 1),
                         min(int(x * params.coverage_grid / w), params.coverage_grid - 1)))
    coverage = len(covered & set(content)) / len(content) if content else 0.0
    homography = est["_h"]
    result.update({k: v for k, v in est.items() if not k.startswith("_") and k != "status"},
                  coverage=round(coverage, 4), content_cells=len(content))
    if not est["transform"]["plausible"]:
        result.update(status="not_verified", reason="Estimated transformation is degenerate or implausible.")
    else:
        result["status"] = "candidate_geometry"  # final verified/not_verified decided against thresholds
        result["differences"] = _residual_differences(img_a, img_b, homography, params)
    result["elapsed_ms"] = elapsed()
    return result


def _normalize_intensity(img: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(img, 1), np.percentile(img, 99)
    return np.clip((img.astype(np.float32) - lo) * 255.0 / max(float(hi - lo), 1.0), 0, 255)


def _refine_ecc(norm_a: np.ndarray, norm_b: np.ndarray, homography: np.ndarray) -> tuple[np.ndarray, float | None]:
    """Sub-pixel refinement of the A→B homography with ECC at half resolution. Falls back to the RANSAC estimate."""
    s = 0.5
    scale = np.diag([s, s, 1.0])
    init = (scale @ homography @ np.linalg.inv(scale)).astype(np.float32)
    try:
        cc, refined = cv2.findTransformECC(cv2.resize(norm_a, None, fx=s, fy=s), cv2.resize(norm_b, None, fx=s, fy=s),
                                           init, cv2.MOTION_HOMOGRAPHY,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 3)
    except cv2.error:
        return homography, None
    return np.linalg.inv(scale) @ refined.astype(np.float64) @ scale, round(float(cc), 4)


def _residual_differences(img_a: np.ndarray, img_b: np.ndarray, homography: np.ndarray, params: VisualParams) -> dict:
    """Align B to A (RANSAC homography refined with ECC), then report connected areas whose blurred, normalised
    intensities differ by more than ``diff_threshold``. Boxes are normalised to A's frame."""
    h, w = img_a.shape
    norm_a, norm_b = _normalize_intensity(img_a), _normalize_intensity(img_b)
    refined, ecc = _refine_ecc(norm_a, norm_b, homography)
    inv = np.linalg.inv(refined)
    warped = cv2.warpPerspective(norm_b, inv, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
    valid = cv2.warpPerspective(np.full(img_b.shape, 255, np.uint8), inv, (w, h), flags=cv2.INTER_NEAREST,
                                borderValue=0)
    valid = cv2.erode(valid, np.ones((9, 9), np.uint8)) > 0  # ignore the warped frame edge
    diff = np.abs(cv2.GaussianBlur(norm_a, (0, 0), params.diff_sigma) - cv2.GaussianBlur(warped, (0, 0), params.diff_sigma))
    mask = ((diff > params.diff_threshold) & valid).astype(np.uint8) * 255
    merged = cv2.dilate(mask, np.ones((5, 9), np.uint8))  # join the strokes of one changed word/number
    count, labels, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    regions = []
    for idx in range(1, count):
        x, y, bw, bh, _area = stats[idx]
        px = int((mask[labels == idx] > 0).sum())
        if px >= params.diff_min_region_px:
            regions.append({"box": [round(float(x) / w, 4), round(float(y) / h, 4), round(float(x + bw) / w, 4),
                                    round(float(y + bh) / h, 4)], "differing_px": px})
    regions.sort(key=lambda r: -r["differing_px"])
    ink_a = _ink_mask(img_a) > 0
    grid = params.diff_grid
    judged = outside = 0
    for i in range(grid):
        for j in range(grid):
            ys, ye, xs, xe = i * h // grid, (i + 1) * h // grid, j * w // grid, (j + 1) * w // grid
            has_ink = int(ink_a[ys:ye, xs:xe].sum()) >= params.diff_min_cell_ink
            if valid[ys:ye, xs:xe].mean() < 0.5:
                outside += int(has_ink)  # A's content not present in B's frame (e.g. cropped away)
            elif has_ink:
                judged += 1
    return {"method": "aligned_intensity_residual_v1", "ecc_refined": ecc is not None, "ecc_correlation": ecc,
            "cells_judged": judged, "cells_outside_overlap": outside, "cells_different": len(regions),
            "regions": regions[:40],
            "note": "'cells_different' is the number of localized difference regions after alignment."}
