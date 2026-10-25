"""Evidence-grounded reviewer copilot (deterministic, retrieval-based; no LLM).

How it works: the question is matched to an intent with keyword rules; facts are retrieved ONLY from the selected
application's persisted records (latest run findings and evaluations, extracted fields, review actions, evidence
requests, simulated issuer checks); the answer is assembled from fixed templates. Document text appears only as
quoted evidence, never as instructions — answers are not generated from document text, so instructions embedded in
an uploaded document cannot change behaviour. Every factual statement carries source references; when no
supporting record exists the answer says so. It never approves/rejects, never determines fraud or authenticity,
never presents simulated verification as real, and never invents regulatory requirements.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, Document, ExtractedField, Finding, ScrutinyRun
from app.models.enums import FieldStatus, FindingKind, ReviewStatus
from app.services import audit, issuer_verification, processing as processing_service, review
from app.services.extraction import FIELD_NAMES
from app.services.normalize import is_grounded, normalize_identifier, normalize_name
from app.services.scrutiny import evaluation_rule, latest_run

DISCLAIMER = ("Reviewer aid only: answers are assembled from this application's stored records. It does not make "
              "decisions, establish authenticity or misconduct, or replace reading the documents.")
SUGGESTIONS = [
    "Summarise the latest scrutiny findings",
    "Why was the highest-severity finding raised?",
    "Which fields are missing or inconclusive?",
    "What is still unresolved?",
    "What evidence requests are outstanding?",
    "Compare the survey numbers across documents",
    "What is the status of the simulated issuer checks?",
    "What should I inspect next?",
]
FIELD_SYNONYMS = {
    "survey_number": ["survey"], "built_up_area": ["area", "built-up", "built up"], "address": ["address", "location"],
    "certificate_number": ["certificate number", "certificate no"], "valid_until": ["validity", "valid until", "expiry"],
    "issue_date": ["issue date", "date of issue", "issued on"], "institution_name": ["institution name", "name of institution"],
    "issuing_authority": ["issuing authority", "issued by", "issuer"], "trust_name": ["trust", "society"],
    "plot_number": ["plot"], "property_identifier": ["property"], "university_name": ["university"],
    "noc_reference": ["noc reference", "noc number"], "resolution_date": ["resolution date"],
}
INTENTS = [
    ("decision", r"\b(approve|approval|reject|rejection|fraud\w*|forg\w*|genuine|authentic\w*|legal(ly)?|verdict|decide|decision|should we (pass|accept))\b"),
    ("issuer", r"\b(issuer|verif\w*|simulated|registry)\b"),
    ("requests", r"\b(evidence requests?|requested|outstanding requests?|pending requests?)\b"),
    ("compare", r"\b(compare|comparison|differ\w*|mismatch|same|versus|vs\.?)\b"),
    ("missing", r"\b(missing|not found|inconclusive|ambiguous|unreadable|unclear)\b"),
    ("unresolved", r"\b(unresolved|open findings?|still open|remaining|left to review)\b"),
    ("next", r"\b(next|inspect|look at|focus|prioriti[sz]e|start with)\b"),
    ("explain", r"\b(why|explain|reason|raised|cause|where|which (document|page)|source|evidence for)\b"),
    ("summary", r"\b(summar\w*|overview|findings|results|status)\b"),
]
_CODE = re.compile(r"\bREG-EoA-\d{4}-\d{4}\b", re.I)


@dataclass
class Source:
    id: str
    kind: str  # finding | evidence | field | evidence_request | verification
    label: str
    finding_id: str | None = None
    document_id: str | None = None
    document_filename: str | None = None
    page_number: int | None = None
    quote: str | None = None


@dataclass
class Answer:
    intent: str
    lines: list[str]
    sources: list[Source] = field(default_factory=list)
    grounded: bool = True
    limitations: list[str] = field(default_factory=list)


class _Ctx:
    def __init__(self, session: Session, application: Application):
        self.session, self.application = session, application
        self.run: ScrutinyRun | None = latest_run(session, application.id)
        self.findings: list[Finding] = (session.execute(select(Finding).where(Finding.run_id == self.run.id)).scalars().all()
                                        if self.run else [])
        self.documents = session.execute(select(Document).where(Document.application_id == application.id)
                                         .order_by(Document.uploaded_at)).scalars().all()
        self._sources: list[Source] = []

    def cite_finding(self, f: Finding) -> str:
        sid = f"S{len(self._sources) + 1}"
        self._sources.append(Source(sid, "finding", f"Finding: {f.title}", finding_id=f.id))
        refs = [sid]
        for ev in f.evidence[:4]:
            if ev.get("quote") or ev.get("document_id"):
                eid = f"S{len(self._sources) + 1}"
                self._sources.append(Source(eid, "evidence", f"{ev.get('document_filename')}"
                                            + (f", page {ev['page_number']}" if ev.get("page_number") else ""),
                                            finding_id=f.id, document_id=ev.get("document_id"),
                                            document_filename=ev.get("document_filename"),
                                            page_number=ev.get("page_number"), quote=ev.get("quote")))
                refs.append(eid)
        return "[" + ", ".join(refs) + "]"

    def cite_field(self, doc: Document, f: ExtractedField) -> str:
        sid = f"S{len(self._sources) + 1}"
        self._sources.append(Source(sid, "field", f"{doc.original_filename}, page {f.page_number}", document_id=doc.id,
                                    document_filename=doc.original_filename, page_number=f.page_number,
                                    quote=f.evidence_quote))
        return f"[{sid}]"

    def cite(self, kind: str, label: str, **kw) -> str:
        sid = f"S{len(self._sources) + 1}"
        self._sources.append(Source(sid, kind, label, **kw))
        return f"[{sid}]"

    @property
    def sources(self) -> list[Source]:
        return self._sources


_SEV = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.kind != FindingKind.RULE_FINDING, f.outcome.value != "issue",
                                           _SEV[f.severity.value], f.finding_key))


def _no_run(ctx: _Ctx, intent: str) -> Answer:
    return Answer(intent, ["No scrutiny run exists for this application yet, so there are no findings to discuss. "
                           "Run preliminary scrutiny first."], grounded=False,
                  limitations=["No scrutiny results are stored for this application."])


def _match_finding(ctx: _Ctx, question: str, finding_id: str | None) -> Finding | None:
    if finding_id:
        return next((f for f in ctx.findings if f.id == finding_id), None)
    rule = re.search(r"\b([A-Z]{2,6}-\d{3})\b", question.upper())
    if rule:
        hit = [f for f in ctx.findings if f.rule_id == rule.group(1)]
        if hit:
            return _sorted(hit)[0]
    words = {w for w in normalize_name(question).split() if len(w) > 3}
    scored = [(len(words & set(normalize_name(f.title + " " + f.finding_type.replace("_", " ")).split())), f)
              for f in ctx.findings]
    scored = [(s, f) for s, f in scored if s >= 2]
    if scored:
        best = max(s for s, _ in scored)
        return _sorted([f for s, f in scored if s == best])[0]
    if re.search(r"\b(highest|most severe|top|worst)\b", question, re.I) and ctx.findings:
        return _sorted(ctx.findings)[0]
    return None


def _summary(ctx: _Ctx) -> Answer:
    if not ctx.run:
        return _no_run(ctx, "summary")
    s = ctx.run.summary or {}
    o = s.get("evaluation_outcomes", {})
    lines = [f"Latest scrutiny run #{ctx.run.run_number} ({ctx.run.status.value}, scrutiny date {ctx.run.scrutiny_date}): "
             f"{o.get('pass', 0)} pass, {o.get('issue', 0)} issue, {o.get('inconclusive', 0)} inconclusive, "
             f"{o.get('not_applicable', 0)} not applicable rule evaluations; {s.get('rule_findings', 0)} rule findings "
             f"and {s.get('anomaly_indicators', 0)} anomaly indicators."]
    for f in _sorted(ctx.findings)[:6]:
        lines.append(f"- {f.severity.value.upper()} {f.outcome.value}: {f.title} (human review: "
                     f"{f.review_status.value.replace('_', ' ')}) {ctx.cite_finding(f)}")
    if not ctx.findings:
        lines.append("There are no findings in this run.")
    return Answer("summary", lines, ctx.sources)


def _explain(ctx: _Ctx, question: str, finding_id: str | None) -> Answer:
    if not ctx.run:
        return _no_run(ctx, "explain")
    f = _match_finding(ctx, question, finding_id)
    if f is None:
        titles = "; ".join(x.title for x in _sorted(ctx.findings)[:5]) or "none"
        return Answer("explain", ["I could not tell which finding you mean. Name it (or its rule ID), or open it and ask "
                                  f"from there. Current findings: {titles}."], grounded=False,
                      limitations=["No finding matched the question."])
    lines = [f"'{f.title}' was raised by "
             + (f"rule {f.rule_id} (version {f.rule_version})" if f.rule_id else f"anomaly detector '{f.detector}'")
             + f" with outcome '{f.outcome.value}' and severity '{f.severity.value}'. {ctx.cite_finding(f)}",
             f"System explanation: {f.explanation}"]
    rule = evaluation_rule(ctx.run.rule_snapshot, f.rule_id)
    if rule:
        lines.append(f"Rule source: {rule['source']}"
                + (" — this is an unverified rule, not a confirmed AICTE requirement."
                   if rule.get("is_demo_only") else "."))
    quoted = [ev for ev in f.evidence if ev.get("quote")]
    for ev in quoted[:4]:
        lines.append(f"Quoted document text (untrusted data) from {ev.get('document_filename')}, page "
                     f"{ev.get('page_number')}: “{ev.get('quote')}”")
    if not quoted:
        lines.append("No quoted evidence is stored for this finding" + (f"; missing evidence: {f.missing_evidence}"
                                                                         if f.missing_evidence else "."))
    if f.uncertainty:
        lines.append(f"Uncertainty: {f.uncertainty}")
    lines.append(f"Current human review state: {f.review_status.value.replace('_', ' ')}.")
    return Answer("explain", lines, ctx.sources)


def _usable_fields(ctx: _Ctx):
    for d in ctx.documents:
        proc = processing_service.get_processing(ctx.session, d.id)
        if not proc or not processing_service.is_current(proc, d):
            continue
        pages = {p.page_number: p.text for p in proc.pages}
        yield d, proc, pages


def _missing(ctx: _Ctx) -> Answer:
    lines, limitations = [], []
    for d, proc, pages in _usable_fields(ctx):
        if proc.status.value == "failed":
            lines.append(f"- {d.original_filename}: not readable ({proc.failure_reason}) "
                         + ctx.cite("document", d.original_filename, document_id=d.id, document_filename=d.original_filename))
            continue
        gaps = [f for f in proc.fields if f.status in (FieldStatus.NOT_FOUND, FieldStatus.AMBIGUOUS, FieldStatus.UNVERIFIED)]
        for f in gaps:
            ref = ctx.cite_field(d, f) if f.page_number else ctx.cite("document", d.original_filename,
                                                                       document_id=d.id, document_filename=d.original_filename)
            lines.append(f"- {d.original_filename}: '{f.field_name}' is {f.status.value.replace('_', ' ')}"
                         + (f" (written as “{f.raw_value}”)" if f.raw_value else "") + f" {ref}")
    unprocessed = [d for d in ctx.documents if not processing_service.is_current(
        processing_service.get_processing(ctx.session, d.id), d)]
    if unprocessed:
        limitations.append("Not processed (fields unknown): " + ", ".join(d.original_filename for d in unprocessed))
    for f in _sorted([f for f in ctx.findings if f.outcome.value == "inconclusive" and f.kind == FindingKind.RULE_FINDING]):
        lines.append(f"- Inconclusive check: {f.title} {ctx.cite_finding(f)}")
    if not lines:
        lines = ["No missing, ambiguous or unverified fields and no inconclusive checks are recorded for processed documents."]
    return Answer("missing", ["Missing fields and inconclusive checks:"] + lines, ctx.sources, limitations=limitations)


def _unresolved(ctx: _Ctx) -> Answer:
    if not ctx.run:
        return _no_run(ctx, "unresolved")
    open_ = _sorted([f for f in ctx.findings if f.review_status in review.UNRESOLVED])
    if not open_:
        return Answer("unresolved", [f"All findings of run #{ctx.run.run_number} have been dismissed or resolved by a reviewer."])
    lines = [f"{len(open_)} finding(s) of run #{ctx.run.run_number} are unresolved:"]
    for f in open_[:10]:
        lines.append(f"- {f.severity.value.upper()}: {f.title} — review state "
                     f"{f.review_status.value.replace('_', ' ')} {ctx.cite_finding(f)}")
    return Answer("unresolved", lines, ctx.sources)


def _requests(ctx: _Ctx) -> Answer:
    open_ = review.list_requests(ctx.session, ctx.application, "open")
    if not open_:
        return Answer("requests", ["There are no open additional-evidence requests for this application."])
    lines = [f"{len(open_)} open evidence request(s):"]
    for r in open_:
        overdue = " — OVERDUE" if review.is_overdue(r) else ""
        ref = ctx.cite("evidence_request", f"Evidence request: {r.requested_evidence[:60]}", finding_id=r.finding_id)
        lines.append(f"- “{r.requested_evidence}” requested by {r.created_by}"
                     + (f", due {r.due_date}{overdue}" if r.due_date else "")
                     + f"; {len(r.documents)} linked document(s) {ref}")
    return Answer("requests", lines, ctx.sources)


def _compare(ctx: _Ctx, question: str) -> Answer:
    q = question.lower()
    names = [n for n, syns in FIELD_SYNONYMS.items() if any(s in q for s in syns)] or \
            [n for n in FIELD_NAMES if n.replace("_", " ") in q]
    if not names:
        return Answer("compare", ["Tell me which field to compare (for example survey number, built-up area, address, "
                                  "certificate number, validity date)."], grounded=False,
                      limitations=["No known field was named in the question."])
    name = names[0]
    mentioned = [d for d in ctx.documents if d.original_filename.lower().split(".")[0] in q]
    values, unclear = [], []
    for d, proc, pages in _usable_fields(ctx):
        if mentioned and d not in mentioned:
            continue
        for f in proc.fields:
            if f.field_name != name or f.status == FieldStatus.NOT_FOUND:
                continue
            if f.status == FieldStatus.EXTRACTED and is_grounded(f.evidence_quote, pages.get(f.page_number, "")):
                values.append((d, f))
            else:
                unclear.append((d, f))
    if not values and not unclear:
        return Answer("compare", [f"No processed document has an extracted '{name}' value, so there is nothing to compare."],
                      grounded=False, limitations=["The field was not found in any processed document."])
    lines = [f"Extracted '{name}' values:"]
    for d, f in values:
        lines.append(f"- {d.original_filename}, page {f.page_number}: “{f.raw_value}” {ctx.cite_field(d, f)}")
    for d, f in unclear:
        lines.append(f"- {d.original_filename}: {f.status.value} value “{f.raw_value}” — not used for comparison "
                     f"{ctx.cite_field(d, f) if f.page_number else ''}".rstrip())
    if len(values) >= 2:
        def key(f):
            if f.normalized_value and f.normalized_value.get("value_sq_m") is not None:
                return round(f.normalized_value["value_sq_m"], 1)
            return normalize_identifier(f.raw_value or "")
        distinct = {key(f) for _, f in values}
        lines.append("The values are identical after normalisation." if len(distinct) == 1 else
                     f"The values differ ({len(distinct)} distinct values). Check the scrutiny findings for whether "
                     "this exceeds the configured tolerance.")
    else:
        lines.append("Fewer than two usable values exist, so no comparison can be made.")
    return Answer("compare", lines, ctx.sources)


def _issuer(ctx: _Ctx) -> Answer:
    attempts = issuer_verification.latest_attempts(ctx.session, ctx.application.id)
    if not attempts:
        return Answer("issuer", ["No simulated issuer checks have been run for this application. Note that ReguLens has "
                                 "no real issuer integration; checks only compare against synthetic demo records."])
    lines = [f"{issuer_verification.SIMULATION_LABEL}. Latest simulated result per document:"]
    for a in attempts.values():
        ref = ctx.cite("verification", f"Simulated check: {a.document_filename}", document_id=a.document_id,
                       document_filename=a.document_filename)
        lines.append(f"- {a.document_filename}: {a.outcome.value.replace('_', ' ')} — {a.explanation} {ref}")
    lines.append("A simulated match only means the extracted fields equal a configured synthetic record; it is not "
                 "verification with the issuing authority.")
    return Answer("issuer", lines, ctx.sources)


def _next(ctx: _Ctx) -> Answer:
    if not ctx.run:
        return _no_run(ctx, "next")
    lines = ["Suggestions for what to inspect next (the decision remains yours):"]
    open_ = _sorted([f for f in ctx.findings if f.review_status in review.UNRESOLVED])
    for f in open_[:4]:
        where = ", ".join(sorted({f"{ev.get('document_filename')} p.{ev.get('page_number')}" for ev in f.evidence
                                  if ev.get("page_number")})) or (f.missing_evidence or "the finding's explanation")
        lines.append(f"- Check {where} for '{f.title}' ({f.severity.value}) {ctx.cite_finding(f)}")
    failed = [d for d, proc, _ in _usable_fields(ctx) if proc.status.value == "failed"]
    for d in failed[:3]:
        lines.append(f"- Read '{d.original_filename}' manually: it could not be processed "
                     + ctx.cite("document", d.original_filename, document_id=d.id, document_filename=d.original_filename))
    overdue = [r for r in review.list_requests(ctx.session, ctx.application, "open") if review.is_overdue(r)]
    for r in overdue:
        lines.append(f"- Follow up the overdue evidence request “{r.requested_evidence[:80]}” "
                     + ctx.cite("evidence_request", "Overdue evidence request", finding_id=r.finding_id))
    if len(lines) == 1:
        lines.append("Nothing outstanding: all findings are dismissed or resolved and no documents failed processing.")
    return Answer("next", lines, ctx.sources)


def answer_question(session: Session, application: Application, question: str, finding_id: str | None = None) -> Answer:
    ctx = _Ctx(session, application)
    other_codes = {c.upper() for c in _CODE.findall(question)} - {application.application_code.upper()}
    if other_codes:
        result = Answer("out_of_scope", ["I can only use records of the application you have open "
                                         f"({application.application_code}). Open the other application to ask about it."],
                        grounded=False, limitations=["Question referred to a different application."])
    else:
        intent = "explain" if finding_id else next((name for name, pattern in INTENTS if re.search(pattern, question, re.I)),
                                                   "unknown")
        if intent == "decision":
            result = Answer("decision", [
                "I cannot approve, reject, or determine fraud, forgery or authenticity — those are human decisions made "
                "outside ReguLens. I can summarise the findings and evidence to support your review."]
                + _summary(ctx).lines[:4], ctx.sources, grounded=bool(ctx.sources),
                limitations=["Decisions and authenticity determinations are out of scope."])
        elif re.search(r"\b(requirement|regulation|handbook|norms?)\b", question, re.I):
            result = Answer("regulatory", ["ReguLens has no verified regulatory sources configured. Its expectation rules "
                                           "are demo-only and must not be read as AICTE requirements."], grounded=False,
                            limitations=["No verified regulatory source is available."])
        elif intent == "unknown":
            result = Answer("unknown", ["I can answer questions about this application's stored findings, evidence, "
                                        "extracted fields, evidence requests and simulated issuer checks. Try: "
                                        + "; ".join(SUGGESTIONS[:4]) + "."], grounded=False,
                            limitations=["Question did not match a supported topic; nothing was looked up."])
        else:
            handlers = {"summary": lambda: _summary(ctx), "explain": lambda: _explain(ctx, question, finding_id),
                        "missing": lambda: _missing(ctx), "unresolved": lambda: _unresolved(ctx),
                        "requests": lambda: _requests(ctx), "compare": lambda: _compare(ctx, question),
                        "issuer": lambda: _issuer(ctx), "next": lambda: _next(ctx)}
            result = handlers[intent]()
    audit.record(session, "copilot.asked", "application", application.application_code, application_id=application.id,
                 details={"intent": result.intent, "sources": len(result.sources), "grounded": result.grounded,
                          "question_length": len(question)})
    session.commit()
    return result
