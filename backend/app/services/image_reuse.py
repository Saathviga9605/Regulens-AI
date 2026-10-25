"""Advisory campus-photo reuse experiment (separate from certificate/document reuse).

Scope: indicate whether two photographs may show the *same underlying image* (e.g. one campus photo cropped and
colour-shifted and submitted again). The indicator is ``POTENTIAL_IMAGE_REUSE`` / ``NOT_INDICATED`` /
``INCONCLUSIVE`` — a prompt for human review only. It never establishes institution identity, that a facility
exists or is available today, fraud, or regulatory non-compliance. No OCR or certificate fields are used.

Fixtures are synthetic: procedurally drawn building facades (``synthetic_building``), so no real campus photos are
used. Positives are the same rendered image under crop / colour shift / JPEG; hard negatives are different but
similar-looking buildings from the same generator (same style, different proportions, window grids and colours).

Method (``image_reuse_v1``): DCT pHash distance (retrieval signal only) and ORB + RANSAC homography on the greyscale
images (reusing ``reuse_visual``); the indicator requires a geometrically consistent match, not hash similarity.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from app.services import reuse_visual as visual
from app.services.reuse_visual import cv2

METHOD_VERSION = "image_reuse_v1"
DATASET_VERSION = "campus_ds_v1"
POTENTIAL = "POTENTIAL_IMAGE_REUSE"
NOT_INDICATED = "NOT_INDICATED"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ImageParams:
    """Selected on the campus *dev* pairs only (see docs); frozen before the campus held-out pairs were run."""

    version: str = "campus_thr_v1"
    # Campus dev pairs: positives 167–223 inliers, ratio ≥0.71, coverage 0.44–0.47; negatives ≤13 inliers, ratio ≤0.34,
    # coverage ≤0.19. Midpoints chosen. pHash distances overlapped (10–24 vs 24–32), so pHash is not used to decide.
    min_inliers: int = 90
    min_inlier_ratio: float = 0.50
    min_coverage: float = 0.32


def synthetic_building(seed: int, *, size=(640, 480)) -> np.ndarray:
    """A fictional building facade photo (BGR): sky gradient, lawn, building with windows, door, trees, texture."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = np.zeros((h, w, 3), np.float32)
    sky_top, sky_bottom = np.array([235, 200, 150]), np.array([250, 235, 210])
    for y in range(h):
        img[y] = sky_top + (sky_bottom - sky_top) * (y / h)
    ground_y = int(h * rng.uniform(0.72, 0.8))
    img[ground_y:] = np.array([70, 140, 80]) + rng.normal(0, 6, (h - ground_y, w, 3))
    bx0, bx1 = int(w * rng.uniform(0.08, 0.2)), int(w * rng.uniform(0.75, 0.92))
    by0 = int(h * rng.uniform(0.18, 0.35))
    wall = rng.uniform(120, 220, 3)
    img[by0:ground_y, bx0:bx1] = wall
    rows, cols = int(rng.integers(3, 6)), int(rng.integers(5, 10))
    ww, wh = (bx1 - bx0) / (cols * 1.6), (ground_y - by0) / (rows * 1.9)
    glass = rng.uniform(60, 120, 3)
    for r in range(rows):
        for c in range(cols):
            x = int(bx0 + (c + 0.3) * (bx1 - bx0) / cols)
            y = int(by0 + (r + 0.25) * (ground_y - by0) / rows)
            img[y:y + int(wh), x:x + int(ww)] = glass + rng.normal(0, 10, 3)
    dx = int((bx0 + bx1) / 2 + rng.uniform(-40, 40))
    img[ground_y - int(wh * 1.6):ground_y, dx - 18:dx + 18] = rng.uniform(40, 90, 3)
    img[by0 - 12:by0, bx0 - 10:bx1 + 10] = wall * 0.6  # roof band
    for _ in range(int(rng.integers(2, 5))):  # trees
        tx, ty, rad = int(rng.uniform(0, w)), int(ground_y + rng.uniform(-10, 10)), int(rng.uniform(25, 50))
        cv2.circle(img, (tx, ty - rad), rad, tuple(float(v) for v in rng.uniform([30, 90, 30], [60, 140, 60])), -1)
    img += rng.normal(0, 4, img.shape)  # sensor texture gives keypoints on walls and sky
    return np.clip(img, 0, 255).astype(np.uint8)


def crop_shift(img: np.ndarray, *, crop: float, hue: int, sat: float, bright: int, jpeg: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    x0, y0 = int(w * crop * rng.uniform(0.3, 1)), int(h * crop * rng.uniform(0.3, 1))
    out = img[y0:h - int(h * crop * rng.uniform(0.3, 1)), x0:w - int(w * crop * rng.uniform(0.3, 1))]
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + hue) % 180
    hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2] + bright, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


@dataclass
class CampusPair:
    key: str
    a: np.ndarray
    b: np.ndarray
    label: str  # same_image / different_building
    split: str  # campus_dev / campus_heldout
    recipe: str


def campus_dataset() -> list[CampusPair]:
    pairs = []
    for split, seeds in (("campus_dev", (101, 102, 103)), ("campus_heldout", (201, 202, 203))):
        for i, s in enumerate(seeds):
            base = synthetic_building(s)
            crop, hue = (0.08, 8) if i % 2 == 0 else (0.15, -12)
            pairs.append(CampusPair(f"{split}_pos{i + 1}", base,
                                    crop_shift(base, crop=crop, hue=hue, sat=0.8, bright=20, jpeg=60, seed=s),
                                    "same_image", split, f"same image: crop ≤{int(crop * 100)}%/side, hue {hue:+d}, "
                                    "saturation ×0.8, brightness +20, JPEG q60"))
            pairs.append(CampusPair(f"{split}_neg{i + 1}", base, synthetic_building(s + 50), "different_building", split,
                                    "different synthetic building, same generator style"))
    return pairs


def compare_images(a: np.ndarray, b: np.ndarray, params: ImageParams = ImageParams()) -> dict:
    ga, gb = (cv2.cvtColor(x, cv2.COLOR_BGR2GRAY) for x in (a, b))
    distance = visual.hamming(visual.page_hashes(ga)[0], visual.page_hashes(gb)[0])
    est = visual._estimate(ga, gb, visual.VisualParams(min_keypoints=40))
    out = {"method": METHOD_VERSION, "thresholds": dataclasses.asdict(params), "phash_distance": distance,
           "keypoints_a": est.get("keypoints_a"), "keypoints_b": est.get("keypoints_b"),
           "tentative_matches": est.get("tentative_matches"), "inliers": est.get("inliers", 0),
           "inlier_ratio": est.get("inlier_ratio", 0.0)}
    if est["status"] == "inconclusive":
        return {**out, "indicator": INCONCLUSIVE, "reason": est.get("reason")}
    if est["status"] != "estimated" or not est["transform"]["plausible"]:
        return {**out, "indicator": NOT_INDICATED, "coverage": 0.0,
                "reason": est.get("reason", "No plausible geometric transformation between the images.")}
    h, w = ga.shape
    cells = {(min(int(y * 6 / h), 5), min(int(x * 6 / w), 5))
             for (x, y), keep in zip(est["_src"].reshape(-1, 2), est["_mask"].ravel()) if keep}
    coverage = len(cells) / 36
    ok = est["inliers"] >= params.min_inliers and est["inlier_ratio"] >= params.min_inlier_ratio and coverage >= params.min_coverage
    return {**out, "coverage": round(coverage, 4), "transform_scale": est["transform"]["scale"],
            "indicator": POTENTIAL if ok else NOT_INDICATED,
            "reason": "Geometrically consistent correspondences across much of the image." if ok
            else "Correspondences do not meet the inlier, ratio and coverage thresholds.",
            "note": "Potential image-reuse indicator for human review only; it does not establish institution identity, "
                    "facility existence or availability, fraud, or non-compliance."}


def evaluate_campus(params: ImageParams = ImageParams()) -> dict:
    rows = []
    for p in campus_dataset():
        r = compare_images(p.a, p.b, params)
        rows.append({"pair": p.key, "split": p.split, "label": p.label, "recipe": p.recipe,
                     **{k: v for k, v in r.items() if k not in ("thresholds", "note")}})
    metrics = {}
    for split in ("campus_dev", "campus_heldout"):
        sr = [r for r in rows if r["split"] == split]
        tp = sum(r["label"] == "same_image" and r["indicator"] == POTENTIAL for r in sr)
        fn = sum(r["label"] == "same_image" and r["indicator"] != POTENTIAL for r in sr)
        fp = sum(r["label"] == "different_building" and r["indicator"] == POTENTIAL for r in sr)
        tn = sum(r["label"] == "different_building" and r["indicator"] != POTENTIAL for r in sr)
        metrics[split] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "pairs": len(sr),
                          "inconclusive": sum(r["indicator"] == INCONCLUSIVE for r in sr)}
    return {"dataset_version": DATASET_VERSION, "method": METHOD_VERSION, "thresholds": dataclasses.asdict(params),
            "synthetic": True, "metrics": metrics, "pairs": rows,
            "note": "Synthetic procedurally drawn facades, not real campus photographs. Advisory indicator only."}
