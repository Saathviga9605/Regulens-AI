"""Workflow for real printed-and-photographed (or phone-scanned) evaluation pairs.

No camera or printer was available while building ReguLens, so no real captures exist. This module provides the
workflow so they can be added without code changes, and keeps real and simulated captures strictly separate:

1. ``write_capture_kit(dir)`` exports printable fictional source PDFs and ``manifest.template.json``.
2. A person prints each source, photographs or phone-scans it, saves the image as PDF/JPEG/PNG next to the
   manifest, and fills in ``capture`` (device, method, lighting, date) for each entry.
3. ``load_manifest(path)`` validates the manifest. Entries must declare ``capture.kind`` = ``real_photo`` or
   ``real_phone_scan``; files must exist. Anything else (including ``simulated``) is rejected, so a simulated image
   can never be reported as a real photograph.

Real captures are designated held-out (``split = physical_heldout``) and must not be used for threshold tuning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.services.reuse_dataset import build_dataset

REAL_KINDS = {"real_photo", "real_phone_scan"}
SOURCES = ["ho_ssc_src", "h2_occ_src", "d2_fire_src", "heldout_alt_src"]  # fictional sources to print
NEGATIVE_SOURCE = "ho_ssc_tmpl"  # same template, different critical fields (print and photograph as hard negative)


class ManifestError(ValueError):
    pass


@dataclass
class CaptureEntry:
    key: str
    source_key: str
    file: Path
    label: str  # reuse / distinct
    kind: str
    capture: dict
    sha256: str


def write_capture_kit(out: Path) -> Path:
    ds = build_dataset()
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for key in SOURCES + [NEGATIVE_SOURCE]:
        (out / f"{key}.pdf").write_bytes(ds.docs[key].pdf)
    for i, key in enumerate(SOURCES, start=1):
        entries.append({"key": f"phys_p{i}", "source_key": key, "file": f"capture_{key}.jpg", "label": "reuse",
                        "capture": {"kind": "real_photo", "device": "", "method": "printed then photographed",
                                    "lighting": "", "background": "", "captured_on": ""}})
    entries.append({"key": f"phys_p{len(SOURCES) + 1}", "source_key": SOURCES[0], "file": f"capture_{NEGATIVE_SOURCE}.jpg",
                    "label": "distinct", "negative_of": NEGATIVE_SOURCE,
                    "capture": {"kind": "real_photo", "device": "", "method": "printed then photographed",
                                "lighting": "", "background": "", "captured_on": ""}})
    manifest = {"dataset": "physical_capture_v1", "split": "physical_heldout",
                "instructions": "Print each source PDF, photograph or phone-scan it, save the file under the given name, "
                                "fill in the capture details, then rename this file to manifest.json. Do not edit labels.",
                "entries": entries}
    path = out / "manifest.template.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path) -> list[CaptureEntry]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        cap = e.get("capture") or {}
        if cap.get("kind") not in REAL_KINDS:
            raise ManifestError(f"{e.get('key')}: capture.kind must be one of {sorted(REAL_KINDS)} (got {cap.get('kind')!r}); "
                                "simulated images belong in the synthetic dataset, not here.")
        if not cap.get("device") or not cap.get("captured_on"):
            raise ManifestError(f"{e.get('key')}: record the capture device and date.")
        file = path.parent / e["file"]
        if not file.is_file():
            raise ManifestError(f"{e.get('key')}: file {e['file']} not found.")
        if e.get("label") not in ("reuse", "distinct"):
            raise ManifestError(f"{e.get('key')}: label must be reuse or distinct.")
        out.append(CaptureEntry(e["key"], e["source_key"], file, e["label"], cap["kind"], cap,
                                hashlib.sha256(file.read_bytes()).hexdigest()))
    return out


def status(manifest_path: Path) -> dict:
    try:
        entries = load_manifest(manifest_path)
    except ManifestError as exc:
        return {"status": "INVALID", "reason": str(exc), "entries": 0}
    if not entries:
        return {"status": "BLOCKED", "entries": 0,
                "reason": "No real printed-and-photographed captures exist: no camera or printer was available. "
                          "Use `python -m app.cli capture-kit --out DIR` to prepare them."}
    return {"status": "AVAILABLE", "entries": len(entries), "kinds": sorted({e.kind for e in entries})}
