"""Cross-case reuse: scans, persistence, restricted alerts, authorised pair access and reviewer dispositions.

Access model (enforced in the API layer and re-checked here where identities are assembled):

* Any signed-in reviewer may start a scan for an application and see a **restricted alert** for that case: the
  local document, the matching outcome and the review state — never the linked application, institution,
  filename, document id, page text, field values, metrics or images.
* Linked-case identities, documents, page images and match evidence require ``cross_case_reviewer`` (granted by
  an administrator; the admin role alone does not include it). Every successful and refused access is audited
  with the actor, pair id and action — never with document content.

Scans run synchronously inside the request (no job queue in this prototype); a running scan for the same
application blocks a concurrent one (409). Pair evaluations are stored once per ``input_key`` and reused.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import Actor
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    Application,
    CasePair,
    CasePairReviewAction,
    Document,
    DocumentFingerprint,
    Institution,
    MatchEvidence,
    ReuseEvaluationRun,
    ReuseScanRun,
)
from app.models.enums import (
    AuditOutcome,
    DocumentStatus,
    PairActionType,
    PairReviewStatus,
    ProcessingStatus,
    ReuseOutcome,
    ReuseScanStatus,
)
from app.services import alerts, audit, pdf_text, processing
from app.services import reuse_engine as engine
from app.services import reuse_visual as visual
from app.services.storage import DocumentStorage
from app.db.types import utcnow

logger = logging.getLogger("regulens.reuse")

SURFACED = (ReuseOutcome.MATCH_CONFIRMED_FOR_REVIEW, ReuseOutcome.CANDIDATE)
MAX_OTHER_DOCUMENTS = 500  # bound on documents compared per scan (most recent first)
STALE_RUN_MINUTES = 15
MIN_REASON = 10

ACTION_TARGET = {
    PairActionType.CONFIRM_CANDIDATE: PairReviewStatus.CONFIRMED_CANDIDATE,
    PairActionType.DISMISS: PairReviewStatus.DISMISSED,
    PairActionType.ESCALATE: PairReviewStatus.ESCALATED,
}


def feature_version(config: engine.ReuseConfig) -> str:
    return (f"{visual.PHASH_VERSION}+{visual.RENDER_VERSION}+dpi{config.visual.hash_dpi}+p{config.max_pages}"
            f"+{engine.TEXT_NORM_VERSION}")


def input_key(doc_a: Document, doc_b: Document, config: engine.ReuseConfig) -> str:
    first, second = sorted([(doc_a.id, doc_a.sha256), (doc_b.id, doc_b.sha256)])
    raw = f"{first[0]}:{first[1]}|{second[0]}:{second[1]}|{engine.pipeline_version(config)}|{config.version}"
    return hashlib.sha256(raw.encode()).hexdigest()


# --- building engine inputs ------------------------------------------------------------------------

def _eligible(doc: Document) -> bool:
    return doc.status != DocumentStatus.INTAKE_FAILED and bool(doc.storage_key)


def _ensure_processed(session: Session, storage: DocumentStorage, settings: Settings, ocr, doc: Document):
    proc = processing.get_processing(session, doc.id)
    if processing.is_current(proc, doc):
        return proc
    try:
        proc, _ = processing.process_document(session, storage, settings, ocr, doc)
        return proc
    except AppError as exc:  # processing failure is recorded; the scan continues without text
        logger.warning("Processing before reuse scan failed", extra={"code": exc.code})
        return processing.get_processing(session, doc.id)


def _input_for(session: Session, storage: DocumentStorage, settings: Settings, ocr, doc: Document,
               config: engine.ReuseConfig) -> engine.DocumentInput | None:
    path = storage.open_path(doc.storage_key)
    if path is None:
        return None
    pdf = pdf_text.as_pdf_bytes(path.read_bytes())  # standalone images: in-memory PDF wrapper
    proc = _ensure_processed(session, storage, settings, ocr, doc)
    pages: list[engine.PageText] = []
    fields: list[engine.FieldEvidence] = []
    text_status = "not_processed"
    if proc is not None and processing.is_current(proc, doc):
        text_status = "failed" if proc.status == ProcessingStatus.FAILED else "available"
        pages = [engine.PageText(p.page_number, p.text, p.status.value, p.method.value, p.ocr_confidence)
                 for p in proc.pages]
        fields = [engine.FieldEvidence(f.field_name, f.raw_value, f.normalized_value, f.page_number, f.evidence_quote,
                                       f.status.value, f.evidence_source, f.evidence_box, f.ocr_confidence)
                  for f in proc.fields]
    inp = engine.DocumentInput(doc.id, doc.application_id, doc.sha256, pdf, pages, fields, text_status=text_status)
    _attach_descriptors(session, doc, inp, config)
    return inp


def _attach_descriptors(session: Session, doc: Document, inp: engine.DocumentInput, config: engine.ReuseConfig) -> None:
    version = feature_version(config)
    fp = session.execute(select(DocumentFingerprint).where(DocumentFingerprint.document_id == doc.id,
                                                           DocumentFingerprint.feature_version == version)
                         ).scalar_one_or_none()
    if fp is not None and fp.sha256 == doc.sha256:
        inp._descriptors = [visual.PageDescriptor(**p) for p in fp.pages]
        inp._descriptor_error = fp.failure_reason
        return
    descriptors = inp.descriptors(config)
    text = "\n".join(p.text for p in inp.pages)
    values = dict(sha256=doc.sha256, pages=[vars(d) for d in descriptors], failure_reason=inp._descriptor_error,
                  text_fingerprint=engine.text_fingerprint(text) if text.strip() else None,
                  text_chars=len(inp.normalized_text()), created_at=utcnow())
    if fp is None:
        session.add(DocumentFingerprint(document_id=doc.id, feature_version=version, **values))
    else:
        for key, value in values.items():
            setattr(fp, key, value)


def _snapshot(session: Session, doc: Document, inp: engine.DocumentInput) -> dict:
    app = session.get(Application, doc.application_id)
    inst = session.get(Institution, app.institution_id) if app else None
    return {"document_id": doc.id, "filename": doc.original_filename, "category": doc.category.value,
            "sha256": doc.sha256, "application_id": doc.application_id,
            "application_code": app.application_code if app else None,
            "institution_name": inst.name if inst else None, "page_count": len(inp.descriptors(engine.DEFAULT_CONFIG))}


# --- scans ---------------------------------------------------------------------------------------

def _application(session: Session, code: str) -> Application:
    app = session.execute(select(Application).where(Application.application_code == code)).scalar_one_or_none()
    if app is None:
        raise NotFoundError(f"Application '{code}' was not found.")
    return app


def run_scan(session: Session, storage: DocumentStorage, settings: Settings, ocr, application_code: str, actor: Actor,
             config: engine.ReuseConfig = engine.DEFAULT_CONFIG) -> ReuseScanRun:
    app = _application(session, application_code)
    cutoff = utcnow() - timedelta(minutes=STALE_RUN_MINUTES)
    running = session.execute(select(ReuseScanRun.id).where(ReuseScanRun.application_id == app.id,
                                                            ReuseScanRun.status == ReuseScanStatus.RUNNING,
                                                            ReuseScanRun.started_at >= cutoff)).first()
    if running:
        raise ConflictError("scan_in_progress", "A cross-case scan for this application is already running.")
    run = ReuseScanRun(application_id=app.id, status=ReuseScanStatus.RUNNING,
                       pipeline_version=engine.pipeline_version(config), config_version=config.version,
                       config=config.snapshot(), triggered_by=actor.username, outcome_counts={})
    session.add(run)
    session.commit()  # visible to concurrent requests
    run_id = run.id
    try:
        _scan(session, storage, settings, ocr, app, run, config)
        audit.record(session, "cross_case.scan_completed", "reuse_scan_run", run.id, application_id=app.id,
                     details={"documents_scanned": run.documents_scanned, "comparisons": run.comparisons,
                              "candidates": run.candidates, "pairs_created": run.pairs_created,
                              "pairs_reused": run.pairs_reused, "config_version": config.version})
        session.commit()
        return run
    except Exception as exc:
        session.rollback()
        failed = session.get(ReuseScanRun, run_id)
        failed.status = ReuseScanStatus.FAILED
        failed.finished_at = utcnow()
        failed.failure_reason = f"{type(exc).__name__}"[:500]
        audit.record(session, "cross_case.scan_failed", "reuse_scan_run", run_id, application_id=app.id,
                     outcome=AuditOutcome.FAILURE, details={"error_type": type(exc).__name__})
        session.commit()
        logger.exception("Cross-case scan failed")
        raise AppError(500, "scan_failed", "The cross-case scan failed. It was recorded; please retry.") from exc


def _scan(session: Session, storage: DocumentStorage, settings: Settings, ocr, app: Application, run: ReuseScanRun,
          config: engine.ReuseConfig) -> None:
    subject = [d for d in session.execute(select(Document).where(Document.application_id == app.id)
                                          .order_by(Document.uploaded_at)).scalars() if _eligible(d)]
    others = [d for d in session.execute(select(Document).where(Document.application_id != app.id)
                                         .order_by(Document.uploaded_at.desc()).limit(MAX_OTHER_DOCUMENTS)).scalars()
              if _eligible(d)]
    cache: dict[str, engine.DocumentInput | None] = {}

    def get(doc: Document):
        if doc.id not in cache:
            cache[doc.id] = _input_for(session, storage, settings, ocr, doc, config)
        return cache[doc.id]

    counts = {o.value: 0 for o in ReuseOutcome}
    for s_doc in subject:
        s_in = get(s_doc)
        if s_in is None:
            continue
        run.documents_scanned += 1
        for o_doc in others:
            o_in = get(o_doc)
            if o_in is None:
                continue
            run.comparisons += 1
            retrieval = engine.is_candidate(s_in, o_in, config)
            if not retrieval[0]:
                continue
            run.candidates += 1
            key = input_key(s_doc, o_doc, config)
            pair = session.execute(select(CasePair).where(CasePair.input_key == key)).scalar_one_or_none()
            if pair is not None:
                pair.last_run_id = run.id
                run.pairs_reused += 1
                counts[pair.outcome.value] += 1
                continue
            result = engine.compare(s_in, o_in, config, retrieval=retrieval)
            pair = _persist_pair(session, s_doc, o_doc, s_in, o_in, result, run, key, config)
            run.pairs_created += 1
            counts[result.outcome] += 1
            if pair.outcome in SURFACED:
                _raise_alerts(session, pair, s_doc, o_doc)
    run.outcome_counts = counts
    run.status = ReuseScanStatus.COMPLETED
    run.finished_at = utcnow()


def _persist_pair(session: Session, a_doc: Document, b_doc: Document, a_in, b_in, result: engine.PairResult,
                  run: ReuseScanRun, key: str, config: engine.ReuseConfig) -> CasePair:
    now = utcnow()
    pair = CasePair(input_key=key, document_a_id=a_doc.id, document_b_id=b_doc.id,
                    application_a_id=a_doc.application_id, application_b_id=b_doc.application_id,
                    sha256_a=a_doc.sha256, sha256_b=b_doc.sha256, candidate_methods=result.candidate_methods,
                    outcome=ReuseOutcome(result.outcome), candidate_score=result.candidate_score,
                    pipeline_version=engine.pipeline_version(config), config_version=config.version,
                    first_run_id=run.id, last_run_id=run.id, created_at=now, updated_at=now)
    pair.evidence = MatchEvidence(
        exact=result.exact, text=result.text, visual=result.visual, geometric=result.geometric, fields=result.fields,
        matched_pages=result.matched_pages, reasons=result.reasons, uncertainties=result.uncertainties,
        stage_status=result.stage_status, snapshot={"a": _snapshot(session, a_doc, a_in), "b": _snapshot(session, b_doc, b_in)},
        config=config.snapshot(), latency_ms=result.latency_ms, fusion=result.fusion, explanation=result.explanation,
        created_at=now)
    session.add(pair)
    session.flush()
    return pair


def _raise_alerts(session: Session, pair: CasePair, a_doc: Document, b_doc: Document) -> None:
    # Alerts are visible to all staff, so they name only the local document — never the linked case.
    for doc in (a_doc, b_doc):
        alerts.raise_alert(
            session, dedup_key=f"cross_case:{pair.id}:{doc.application_id}", application_id=doc.application_id,
            event_type="cross_case_match", severity="medium" if pair.outcome == ReuseOutcome.MATCH_CONFIRMED_FOR_REVIEW else "low",
            document_id=doc.id, title="Possible cross-case document reuse",
            message=(f"'{doc.original_filename}' may share content with a document in another case "
                     f"({pair.outcome.value}). Details are restricted to cross-case reviewers. "
                     "This is a prompt for review, not a finding of misconduct."))


def list_runs(session: Session, application_code: str, limit: int = 10) -> list[ReuseScanRun]:
    app = _application(session, application_code)
    return list(session.execute(select(ReuseScanRun).where(ReuseScanRun.application_id == app.id)
                                .order_by(ReuseScanRun.started_at.desc()).limit(limit)).scalars())


# --- restricted alerts and authorised views ------------------------------------------------------

def _current(stmt, config: engine.ReuseConfig = engine.DEFAULT_CONFIG):
    return stmt.where(CasePair.pipeline_version == engine.pipeline_version(config),
                      CasePair.config_version == config.version)


def case_alerts(session: Session, application_code: str, actor: Actor) -> dict:
    """Pairs touching this case with a surfaced outcome. Linked-case details only for cross-case reviewers."""
    app = _application(session, application_code)
    pairs = session.execute(_current(select(CasePair).where(
        or_(CasePair.application_a_id == app.id, CasePair.application_b_id == app.id),
        CasePair.outcome.in_(SURFACED))).order_by(CasePair.created_at.desc())).scalars().all()
    items = []
    for pair in pairs:
        local_side = "a" if pair.application_a_id == app.id else "b"
        snap = pair.evidence.snapshot if pair.evidence else {}
        local = snap.get(local_side, {})
        item = {"pair_id": pair.id, "outcome": pair.outcome.value, "review_status": pair.review_status.value,
                "detected_at": pair.created_at,
                "local_document": {"document_id": local.get("document_id"), "filename": local.get("filename")},
                "restricted": not actor.cross_case_reviewer, "linked": None}
        if actor.cross_case_reviewer:
            other = snap.get("b" if local_side == "a" else "a", {})
            item["linked"] = {"application_code": other.get("application_code"),
                              "institution_name": other.get("institution_name"), "filename": other.get("filename")}
        items.append(item)
    latest = session.execute(select(ReuseScanRun).where(ReuseScanRun.application_id == app.id)
                             .order_by(ReuseScanRun.started_at.desc()).limit(1)).scalar_one_or_none()
    return {"items": items, "can_view_details": actor.cross_case_reviewer, "latest_scan": latest,
            "notice": "A possible match is a prompt for human review. Document reuse is not automatically misconduct."}


def list_pairs(session: Session, *, page: int, page_size: int, application_code: str | None = None,
               outcome: ReuseOutcome | None = None, review_status: PairReviewStatus | None = None,
               include_superseded: bool = False) -> tuple[list[CasePair], int]:
    stmt = select(CasePair)
    if not include_superseded:
        stmt = _current(stmt)
    if application_code:
        app = _application(session, application_code)
        stmt = stmt.where(or_(CasePair.application_a_id == app.id, CasePair.application_b_id == app.id))
    if outcome:
        stmt = stmt.where(CasePair.outcome == outcome)
    if review_status:
        stmt = stmt.where(CasePair.review_status == review_status)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(stmt.order_by(CasePair.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
                           ).scalars().all()
    return list(rows), total


def get_pair(session: Session, pair_id: str) -> CasePair:
    pair = session.get(CasePair, pair_id)
    if pair is None:
        raise NotFoundError("Case pair was not found.")
    return pair


def record_access(session: Session, pair: CasePair, action: str, **details) -> None:
    audit.record(session, f"cross_case.{action}", "case_pair", pair.id, application_id=pair.application_a_id,
                 details={"pair_id": pair.id, "action": action, **details})
    session.commit()


def pair_page_png(session: Session, storage: DocumentStorage, pair: CasePair, side: str, page_number: int) -> bytes:
    doc_id = pair.document_a_id if side == "a" else pair.document_b_id
    doc = session.get(Document, doc_id) if doc_id else None
    path = storage.open_path(doc.storage_key) if doc and doc.storage_key else None
    if path is None:
        raise AppError(410, "document_unavailable", "This document is no longer stored; only the recorded evidence remains.")
    try:
        return visual.render_png(pdf_text.as_pdf_bytes(path.read_bytes()), page_number)
    except IndexError:
        raise NotFoundError("That page does not exist in this document.") from None


def review_action(session: Session, pair: CasePair, actor: Actor, action: PairActionType, note: str | None,
                  expected_version: int) -> CasePair:
    if pair.review_version != expected_version:
        raise ConflictError("stale_review", "Someone else updated this pair. Reload and try again.")
    note = (note or "").strip() or None
    if action in ACTION_TARGET and (not note or len(note) < MIN_REASON):
        raise AppError(422, "reason_required", f"A reason of at least {MIN_REASON} characters is required.",
                       [{"loc": ["body", "note"], "msg": "Reason required."}])
    if action == PairActionType.NOTE and not note:
        raise AppError(422, "note_required", "Enter the observation.", [{"loc": ["body", "note"], "msg": "Required."}])
    previous = pair.review_status
    new = ACTION_TARGET.get(action, previous)
    session.add(CasePairReviewAction(pair_id=pair.id, action_type=action, previous_status=previous, new_status=new,
                                     actor_user_id=actor.user_id, actor_username=actor.username, note=note))
    pair.review_status = new
    pair.review_version += 1
    pair.updated_at = utcnow()
    audit.record(session, "cross_case.review_action", "case_pair", pair.id, application_id=pair.application_a_id,
                 details={"pair_id": pair.id, "action": action.value, "from": previous.value, "to": new.value})
    session.commit()
    return pair


def pair_actions(session: Session, pair: CasePair) -> list[CasePairReviewAction]:
    return list(session.execute(select(CasePairReviewAction).where(CasePairReviewAction.pair_id == pair.id)
                                .order_by(CasePairReviewAction.created_at)).scalars())


# --- evaluation ----------------------------------------------------------------------------------

_EVAL_LOCK = threading.Lock()


def run_evaluation(session: Session, actor: Actor, ocr=None) -> ReuseEvaluationRun:
    from app.services import reuse_eval

    if not _EVAL_LOCK.acquire(blocking=False):
        raise ConflictError("evaluation_in_progress", "An evaluation is already running.")
    try:
        started = time.perf_counter()
        result = reuse_eval.evaluate(ocr=ocr)
        d = result.data
        row = ReuseEvaluationRun(created_by=actor.username, eval_version=d["eval_version"],
                                 dataset_version=d["dataset_version"], dataset_digest=d["dataset_digest"],
                                 config_version=d["config_version"], pipeline_version=d["pipeline_version"],
                                 duration_ms=round((time.perf_counter() - started) * 1000, 1), results=d)
        session.add(row)
        session.flush()
        audit.record(session, "cross_case.evaluation_run", "reuse_evaluation_run", row.id,
                     details={"dataset_version": row.dataset_version, "config_version": row.config_version})
        session.commit()
        return row
    finally:
        _EVAL_LOCK.release()


def list_evaluations(session: Session, limit: int = 20) -> list[ReuseEvaluationRun]:
    return list(session.execute(select(ReuseEvaluationRun).order_by(ReuseEvaluationRun.created_at.desc()).limit(limit))
                .scalars())


def get_evaluation(session: Session, evaluation_id: str) -> ReuseEvaluationRun:
    row = session.get(ReuseEvaluationRun, evaluation_id)
    if row is None:
        raise NotFoundError("Evaluation was not found.")
    return row
