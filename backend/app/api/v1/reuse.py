"""Cross-case document reuse endpoints.

* ``router`` — any signed-in reviewer: start a scan, list scan runs (counts only), restricted case alerts.
* ``restricted_router`` — every route requires the ``cross_case_reviewer`` permission (router-level dependency,
  so no endpoint can be added without it): pair list, pair detail and evidence, page images, reviewer actions.
* ``evaluation_router`` — A0/A1/A4 evaluation on synthetic fixtures; cross-case reviewers or administrators.
"""

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    Pagination,
    get_app_settings,
    get_current_actor,
    get_db,
    get_pagination,
    get_storage,
    require_cross_case_reviewer,
)
from app.core.config import Settings
from app.core.context import Actor
from app.core.errors import AppError
from app.models import CasePair, Document
from app.models.enums import AuditOutcome, PairReviewStatus, ReuseOutcome
from app.schemas.common import Page
from app.schemas.reuse import (
    CaseAlertList,
    EvaluationDetail,
    EvaluationSummary,
    EvidenceRead,
    PairActionRead,
    PairActionRequest,
    PairDetail,
    PairSide,
    PairSummary,
    ScanRunRead,
)
from app.services import audit
from app.services import reuse as service
from app.services import reuse_engine as engine
from app.services.reuse_eval import EvalResult
from app.services.storage import DocumentStorage

router = APIRouter(tags=["cross-case reuse"])
restricted_router = APIRouter(tags=["cross-case reuse"], dependencies=[Depends(require_cross_case_reviewer)])
evaluation_router = APIRouter(tags=["cross-case reuse"])

UUID_RE = r"^[0-9a-f-]{36}$"  # each route gets its own Path() — FastAPI binds parameter objects per route

LIMITATIONS = [
    "Outcomes are matching outcomes for human review — not findings of fraud, forgery, authenticity or misconduct.",
    "Without OCR, image-only (scanned) pages have no text: text and field comparison is unavailable for them.",
    "Geometric verification compares one best-matching page pair per document pair.",
    "Thresholds were selected on a small synthetic development set; real documents may behave differently.",
]


def get_ocr(request: Request):
    return request.app.state.ocr_engine


# --- any reviewer ----------------------------------------------------------------------------------

@router.post("/applications/{application_code}/cross-case-scans", response_model=ScanRunRead, status_code=201)
def start_scan(application_code: str, request: Request, actor: Actor = Depends(get_current_actor),
               db: Session = Depends(get_db), storage: DocumentStorage = Depends(get_storage),
               settings: Settings = Depends(get_app_settings)) -> ScanRunRead:
    return ScanRunRead.model_validate(service.run_scan(db, storage, settings, get_ocr(request), application_code, actor))


@router.get("/applications/{application_code}/cross-case-scans", response_model=list[ScanRunRead])
def list_scans(application_code: str, db: Session = Depends(get_db)) -> list[ScanRunRead]:
    return [ScanRunRead.model_validate(r) for r in service.list_runs(db, application_code)]


@router.get("/applications/{application_code}/cross-case-alerts", response_model=CaseAlertList)
def case_alerts(application_code: str, actor: Actor = Depends(get_current_actor),
                db: Session = Depends(get_db)) -> CaseAlertList:
    return CaseAlertList.model_validate(service.case_alerts(db, application_code, actor), from_attributes=True)


# --- cross-case reviewers only ----------------------------------------------------------------------

def _side(db: Session, pair: CasePair, side: str) -> PairSide:
    snap = (pair.evidence.snapshot if pair.evidence else {}).get(side, {})
    doc_id = pair.document_a_id if side == "a" else pair.document_b_id
    doc = db.get(Document, doc_id) if doc_id else None
    return PairSide(document_id=doc_id or snap.get("document_id"), document_available=bool(doc and doc.storage_key),
                    filename=snap.get("filename"), category=snap.get("category"),
                    application_code=snap.get("application_code"), institution_name=snap.get("institution_name"),
                    page_count=snap.get("page_count"), sha256=pair.sha256_a if side == "a" else pair.sha256_b)


def _summary(db: Session, pair: CasePair) -> dict:
    return dict(id=pair.id, outcome=pair.outcome, outcome_meaning=engine.OUTCOME_MEANING[pair.outcome.value],
                review_status=pair.review_status, review_version=pair.review_version,
                candidate_methods=pair.candidate_methods, candidate_score=pair.candidate_score,
                pipeline_version=pair.pipeline_version, config_version=pair.config_version,
                created_at=pair.created_at, updated_at=pair.updated_at, a=_side(db, pair, "a"), b=_side(db, pair, "b"))


def _detail(db: Session, pair: CasePair) -> PairDetail:
    ev = pair.evidence
    return PairDetail(**_summary(db, pair), evidence=EvidenceRead.model_validate(ev, from_attributes=True),
                      actions=[PairActionRead.model_validate(a) for a in service.pair_actions(db, pair)],
                      notice="Document reuse is not automatically misconduct. Review the evidence and record your reasoning.",
                      limitations=LIMITATIONS)


@restricted_router.get("/case-pairs", response_model=Page[PairSummary])
def list_pairs(pagination: Pagination = Depends(get_pagination),
               application_code: str | None = Query(None, max_length=40), outcome: ReuseOutcome | None = None,
               review_status: PairReviewStatus | None = None, include_superseded: bool = False,
               db: Session = Depends(get_db)) -> Page[PairSummary]:
    rows, total = service.list_pairs(db, page=pagination.page, page_size=pagination.page_size,
                                     application_code=application_code, outcome=outcome, review_status=review_status,
                                     include_superseded=include_superseded)
    return Page.build([PairSummary(**_summary(db, p)) for p in rows], total, pagination.page, pagination.page_size)


@restricted_router.get("/case-pairs/{pair_id}", response_model=PairDetail)
def get_pair(pair_id: str = Path(pattern=UUID_RE), db: Session = Depends(get_db)) -> PairDetail:
    pair = service.get_pair(db, pair_id)
    service.record_access(db, pair, "pair_viewed")
    return _detail(db, pair)


@restricted_router.get("/case-pairs/{pair_id}/pages/{side}/{page_number}", response_class=Response,
                       responses={200: {"content": {"image/png": {}}}})
def pair_page(pair_id: str = Path(pattern=UUID_RE), side: str = Path(pattern="^(a|b)$"), page_number: int = Path(ge=1, le=500),
              db: Session = Depends(get_db), storage: DocumentStorage = Depends(get_storage)) -> Response:
    pair = service.get_pair(db, pair_id)
    png = service.pair_page_png(db, storage, pair, side, page_number)
    service.record_access(db, pair, "page_image_viewed", side=side, page=page_number)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


@restricted_router.get("/case-pairs/{pair_id}/review-actions", response_model=list[PairActionRead])
def list_actions(pair_id: str = Path(pattern=UUID_RE), db: Session = Depends(get_db)) -> list[PairActionRead]:
    pair = service.get_pair(db, pair_id)
    return [PairActionRead.model_validate(a) for a in service.pair_actions(db, pair)]


@restricted_router.post("/case-pairs/{pair_id}/review-actions", response_model=PairDetail, status_code=201)
def add_action(body: PairActionRequest, pair_id: str = Path(pattern=UUID_RE), actor: Actor = Depends(get_current_actor),
               db: Session = Depends(get_db)) -> PairDetail:
    pair = service.get_pair(db, pair_id)
    service.review_action(db, pair, actor, body.action, body.note, body.expected_version)
    return _detail(db, pair)


# --- evaluation (synthetic fixtures only) -------------------------------------------------------------

async def _evaluation_access(request: Request, actor: Actor = Depends(get_current_actor)) -> Actor:
    if not (actor.cross_case_reviewer or actor.is_admin):
        audit.record_now(request.app.state.session_factory, "authorization.denied", "endpoint",
                         f"{request.method} {request.url.path}"[:64], outcome=AuditOutcome.DENIED,
                         details={"required": "cross_case_reviewer or admin"}, actor=actor)
        raise AppError(403, "forbidden", "Evaluations require the cross-case reviewer permission or the administrator role.")
    return actor


@evaluation_router.post("/reuse-evaluations", response_model=EvaluationDetail, status_code=201)
def run_evaluation(request: Request, actor: Actor = Depends(_evaluation_access),
                   db: Session = Depends(get_db)) -> EvaluationDetail:
    return EvaluationDetail.model_validate(service.run_evaluation(db, actor, ocr=get_ocr(request)))


@evaluation_router.get("/reuse-evaluations", response_model=list[EvaluationSummary],
                       dependencies=[Depends(_evaluation_access)])
def list_evaluations(db: Session = Depends(get_db)) -> list[EvaluationSummary]:
    return [EvaluationSummary.model_validate(e) for e in service.list_evaluations(db)]


@evaluation_router.get("/reuse-evaluations/{evaluation_id}", response_model=EvaluationDetail,
                       dependencies=[Depends(_evaluation_access)])
def get_evaluation(evaluation_id: str = Path(pattern=UUID_RE), db: Session = Depends(get_db)) -> EvaluationDetail:
    return EvaluationDetail.model_validate(service.get_evaluation(db, evaluation_id))


@evaluation_router.get("/reuse-evaluations/{evaluation_id}/export", response_class=Response,
                       dependencies=[Depends(_evaluation_access)])
def export_evaluation(evaluation_id: str = Path(pattern=UUID_RE), format: str = Query("csv", pattern="^(csv|md|json)$"),
                      db: Session = Depends(get_db)) -> Response:
    import json

    row = service.get_evaluation(db, evaluation_id)
    result = EvalResult(row.results)
    if format == "json":
        body, media, ext = json.dumps(row.results, indent=2, default=str), "application/json", "json"
    elif format == "md":
        body, media, ext = result.to_markdown(), "text/markdown; charset=utf-8", "md"
    else:
        body, media, ext = result.to_csv(), "text/csv; charset=utf-8", "csv"
    name = f"reuse-evaluation-{row.created_at:%Y%m%d-%H%M%S}.{ext}"
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
