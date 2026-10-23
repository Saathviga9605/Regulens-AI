"""Explainable keyword/heading classifier.

Each category has weighted regex signals. A signal counts once; a match within the first 8 non-empty lines of
page 1 (the heading area) counts double. Category score = sum of matched weights.

Confidence (heuristic, NOT a calibrated probability):
    share = top score / sum of all category scores
    high      : top >= 8 and share >= 0.70
    medium    : top >= 4 and share >= 0.55
    uncertain : anything else, including no signals (predicted_category is then None)
"""

import re
from dataclasses import dataclass, field

from app.models.enums import DocumentCategory as C

CLASSIFIER_VERSION = "cls-1"
HEADING_LINES = 8

_S = list[tuple[str, float, str]]
SIGNALS: dict[C, _S] = {
    C.FIRE_SAFETY_CERTIFICATE: [
        (r"\bfire\s+safety\s+certificate\b", 5, "phrase 'fire safety certificate'"),
        (r"\bfire\s+(?:no[\s-]+objection|noc)\b", 4, "phrase 'fire no objection / fire NOC'"),
        (r"\bfire\s+(?:services?|department|officer|brigade)\b", 1.5, "mentions a fire service/officer"),
        (r"\bfire\s+(?:fighting|extinguish\w*|hydrants?|exits?|alarms?)\b", 1, "fire equipment terms"),
    ],
    C.OCCUPANCY_CERTIFICATE: [
        (r"\boccupancy\s+certificate\b", 5, "phrase 'occupancy certificate'"),
        (r"\boccupation\s+certificate\b", 4, "phrase 'occupation certificate'"),
        (r"\bfit\s+for\s+occupa(?:tion|ncy)\b", 2, "phrase 'fit for occupation'"),
    ],
    C.COMPLETION_CERTIFICATE: [
        (r"\bcompletion\s+certificate\b", 5, "phrase 'completion certificate'"),
        (r"\bconstruction\s+(?:has\s+been\s+|was\s+)?completed\b", 1.5, "states construction completed"),
    ],
    C.STRUCTURAL_STABILITY_CERTIFICATE: [
        (r"\bstructural\s+stability\s+certificate\b", 5, "phrase 'structural stability certificate'"),
        (r"\bstructural(?:ly)?\s+(?:stable|safe|sound)\b", 2, "states structurally stable/safe"),
        (r"\bstructural\s+engineer\b", 1.5, "mentions a structural engineer"),
    ],
    C.BUILDING_PLAN: [
        (r"\b(?:sanctioned\s+)?building\s+plan\b", 4, "phrase 'building plan'"),
        (r"\blayout\s+plan\b", 2, "phrase 'layout plan'"),
        (r"\b(?:built[\s-]*up|plinth|floor)\s+area\b", 1, "area terms"),
    ],
    C.UNIVERSITY_NOC: [
        (r"\buniversity\b.{0,60}\bno[\s-]+objection\b|\bno[\s-]+objection\b.{0,60}\buniversity\b", 5,
         "'no objection' near 'university'"),
        (r"\baffiliat\w*\b", 1.5, "affiliation terms"),
        (r"\bregistrar\b", 1, "mentions a registrar"),
    ],
    C.TRUST_RESOLUTION: [
        (r"\b(?:board\s+)?resolution\b", 3, "word 'resolution'"),
        (r"\bresolved\s+that\b", 2.5, "phrase 'resolved that'"),
        (r"\btrustees\b|\bgoverning\s+(?:body|council)\b", 2, "trustees/governing body"),
        (r"\b(?:trust|society)\b", 1, "word 'trust'/'society'"),
    ],
}
_COMPILED = {cat: [(re.compile(p, re.I | re.S), w, label) for p, w, label in sigs] for cat, sigs in SIGNALS.items()}


@dataclass
class Classification:
    predicted_category: C | None
    score: float  # share of total signal weight held by the top category, 0..1
    confidence: str  # high | medium | uncertain
    signals: list[dict] = field(default_factory=list)  # matched signals for the predicted category
    alternatives: list[dict] = field(default_factory=list)  # other categories with a non-zero score
    ambiguous: bool = False


def classify(pages: list[str]) -> Classification:
    if not any(p.strip() for p in pages):
        return Classification(None, 0.0, "uncertain", ambiguous=True)
    full = "\n".join(pages)
    heading_lines = [line for line in (pages[0] if pages else "").splitlines() if line.strip()][:HEADING_LINES]
    heading = "\n".join(heading_lines)

    scores: dict[C, float] = {}
    matched: dict[C, list[dict]] = {}
    for cat, signals in _COMPILED.items():
        total = 0.0
        for regex, weight, label in signals:
            if regex.search(full):
                in_heading = bool(regex.search(heading))
                gained = weight * (2 if in_heading else 1)
                total += gained
                matched.setdefault(cat, []).append({"signal": label, "weight": gained, "in_heading": in_heading})
        if total:
            scores[cat] = total

    if not scores:
        return Classification(None, 0.0, "uncertain", ambiguous=True)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].value))
    top_cat, top = ranked[0]
    share = top / sum(scores.values())
    if top >= 8 and share >= 0.70:
        confidence = "high"
    elif top >= 4 and share >= 0.55:
        confidence = "medium"
    else:
        confidence = "uncertain"
    alternatives = [{"category": c.value, "score": s, "signals": matched[c]} for c, s in ranked[1:]]
    return Classification(
        predicted_category=top_cat if confidence != "uncertain" else None,
        score=round(share, 3),
        confidence=confidence,
        signals=matched[top_cat],
        alternatives=([{"category": top_cat.value, "score": top, "signals": matched[top_cat]}]
                      if confidence == "uncertain" else []) + alternatives,
        ambiguous=confidence == "uncertain" or (len(ranked) > 1 and ranked[1][1] >= 0.75 * top),
    )
