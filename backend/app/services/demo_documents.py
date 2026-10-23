"""Synthetic demonstration PDFs and SYNTHETIC issuer reference records for the demo seed.

Every generated PDF carries a banner on each page and in its metadata stating that it is a fictional
demonstration document and not a genuine certificate. All names, numbers and authorities are invented.
Documents are stored through the normal intake path (signature check, SHA-256, private storage, duplicate
detection). Reseeding is idempotent (``seed_key``) and never modifies existing records.
"""

import hashlib
from dataclasses import dataclass, field

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Application, Document, IssuerReferenceRecord
from app.models.enums import DocumentCategory as C, ReferenceAvailability
from app.services import documents as document_service
from app.services.normalize import normalize_identifier
from app.services.storage import DocumentStorage

BANNER = "FICTIONAL DEMONSTRATION DOCUMENT - NOT A GENUINE CERTIFICATE - REGULENS AI DEMO DATA"


def build_pdf(lines: list[str], *, image_only: bool = False, encrypt: bool = False, title: str = "") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 points
    page.insert_text((40, 40), BANNER, fontsize=9, color=(0.75, 0, 0))
    y = 90
    for line in lines:
        page.insert_text((60, y), line, fontsize=12 if y == 90 else 11)
        y += 22
    page.insert_text((40, 810), BANNER, fontsize=9, color=(0.75, 0, 0))
    doc.set_metadata({"title": f"Fictional demo: {title}", "producer": "ReguLens AI demo seed",
                      "creator": "ReguLens AI demo seed"})
    if image_only:
        pix = page.get_pixmap(dpi=110)
        scanned = pymupdf.open()
        sp = scanned.new_page(width=595, height=842)
        sp.insert_image(sp.rect, pixmap=pix)
        scanned.set_metadata({"title": f"Fictional demo (scanned image): {title}", "producer": "ReguLens AI demo seed"})
        doc = scanned
    if encrypt:
        return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="demo-owner", user_pw="demo-user")
    return doc.tobytes(garbage=3, deflate=True)


def _cert(title: str, *body: str) -> list[str]:
    return [title, *body, "", "This is a fictional document generated for software demonstration only."]


DECCAN = "Deccan Ridge Institute of Engineering"
DECCAN_ADDR = "Plot 14, Synthetic Knowledge Park, Hinjewadi Phase 9, Pune 411099"
HOOGHLY = "Hooghly Riverside Engineering College"
HOOGHLY_ADDR = "7 Synthetic Strand Lane, Serampore North, Hooghly 712299"
ARAVALLI = "Aravalli Foothills College of Engineering"

FIRE_A = _cert("FIRE SAFETY CERTIFICATE",
               "Issued by: Synthetic Municipal Fire Services, Pune (Fictional)",
               "Certificate No.: SYN-FSC/PUN/2026/0142", f"Name of Institution: {DECCAN}", f"Address: {DECCAN_ADDR}",
               "Survey No.: 101/2A", "Date of Issue: 14 March 2026", "Valid Until: 13 March 2029", "",
               "The fire fighting installations, fire exits and hydrants of the above premises were inspected.")
OCC_A = _cert("OCCUPANCY CERTIFICATE",
              "Issued by: Synthetic Pune Development Authority (Fictional)",
              "Certificate No.: SYN-OC/PUN/2024/0077", f"Name of Institution: {DECCAN}", f"Address: {DECCAN_ADDR}",
              "Survey No.: 101/2A", "Built-up Area: 12,450 sq. m", "Date of Issue: 22 July 2024", "",
              "The building described above is fit for occupation.")
SSC_A = _cert("STRUCTURAL STABILITY CERTIFICATE",
              "Issued by: Fictional Structural Consultants LLP (Synthetic)",
              "Certificate No.: SYN-SSC/2025/0310", f"Name of Institution: {DECCAN}", f"Address: {DECCAN_ADDR}",
              "Date of Issue: 18 August 2025", "Valid Until: 17 August 2030", "",
              "Certified structurally stable by the undersigned structural engineer (fictional).")
TRUST_A = _cert("BOARD RESOLUTION",
                "Name of Trust/Society: Deccan Ridge Education Society (Synthetic)", f"Name of Institution: {DECCAN}",
                "Date of Resolution: 15 January 2026", "",
                "RESOLVED THAT the trustees authorise the Principal to file the Extension of Approval application.")

FIRE_B = _cert("FIRE SAFETY CERTIFICATE",
               "Issued by: Synthetic Hooghly Fire Services (Fictional)",
               "Certificate No.: SYN-FSC/HGY/2023/0019", f"Name of Institution: {HOOGHLY}", f"Address: {HOOGHLY_ADDR}",
               "Survey No.: 312", "Date of Issue: 2 January 2023", "Valid Until: 31 December 2025", "",
               "The fire fighting installations of the above premises were inspected.")
OCC_B = _cert("OCCUPANCY CERTIFICATE",
              "Issued by: Synthetic Hooghly Development Authority (Fictional)",
              "Certificate No.: SYN-OC/HGY/2022/0450", f"Name of Institution: {HOOGHLY}", f"Address: {HOOGHLY_ADDR}",
              "Survey No.: 318", "Built-up Area: 9,500 sq. m", "Date of Issue: 19 September 2022", "",
              "The building described above is fit for occupation.")
PLAN_B = _cert("SANCTIONED BUILDING PLAN",
               "Issued by: Synthetic Hooghly Zilla Planning Cell (Fictional)", f"Name of Institution: {HOOGHLY}",
               f"Address: {HOOGHLY_ADDR}", "Survey No.: 312", "Built-up Area: 86,000 sq. ft",
               "Date of Issue: 27 June 2021", "", "Layout plan and floor plans are annexed (fictional).")

FIRE_C_SCAN = _cert("FIRE SAFETY CERTIFICATE",
                    "Issued by: Synthetic Jaipur Fire Services (Fictional)", "Certificate No.: SYN-FSC/JPR/2025/0921",
                    f"Name of Institution: {ARAVALLI}", "Date of Issue: 21 November 2025", "Valid Until: 20 November 2028")
TRUST_AS_NOC_C = _cert("BOARD RESOLUTION",
                       "Name of Trust/Society: Aravalli Foothills Shiksha Parishad (Synthetic)",
                       f"Name of Institution: {ARAVALLI}", "Date of Resolution: 17 February 2026", "",
                       "RESOLVED THAT the trustees approve the introduction of a new course.")
NOC_C = _cert("NO OBJECTION CERTIFICATE",
              "Name of the University: Synthetic Rajasthan Technical University (Fictional)",
              f"Name of Institution: {ARAVALLI}", "Date of Issue: 05/06/2026", "",
              "The University has no objection to the proposed new course, subject to affiliation norms (fictional).")
COMPLETION_C = _cert("COMPLETION CERTIFICATE", "Certificate No.: SYN-CC/JPR/2024/0055", f"Name of Institution: {ARAVALLI}")


@dataclass(frozen=True)
class DemoDoc:
    seed_key: str
    application_seed_key: str
    filename: str
    category: C
    description: str
    lines: list
    image_only: bool = False
    encrypt: bool = False
    copy_of: str | None = None  # seed_key of a demo document whose exact bytes are re-uploaded


DEMO_DOCUMENTS: list[DemoDoc] = [
    # Clean example: seed-app-01 (Deccan Ridge) — consistent documents.
    DemoDoc("demo-doc-a1", "seed-app-01", "fire-safety-certificate.pdf", C.FIRE_SAFETY_CERTIFICATE,
            "Demo: clean example", FIRE_A),
    DemoDoc("demo-doc-a2", "seed-app-01", "occupancy-certificate.pdf", C.OCCUPANCY_CERTIFICATE,
            "Demo: clean example", OCC_A),
    DemoDoc("demo-doc-a3", "seed-app-01", "structural-stability-certificate.pdf",
            C.STRUCTURAL_STABILITY_CERTIFICATE, "Demo: clean example", SSC_A),
    DemoDoc("demo-doc-a4", "seed-app-01", "trust-resolution.pdf", C.TRUST_RESOLUTION, "Demo: clean example", TRUST_A),
    # Inconsistent example: seed-app-06 (Hooghly) — survey/area conflicts, expired validity, duplicate,
    # missing structural stability certificate.
    DemoDoc("demo-doc-b1", "seed-app-06", "fire-certificate-2023.pdf", C.FIRE_SAFETY_CERTIFICATE,
            "Demo: stated validity has passed", FIRE_B),
    DemoDoc("demo-doc-b2", "seed-app-06", "occupancy-certificate.pdf", C.OCCUPANCY_CERTIFICATE,
            "Demo: survey number and area conflict", OCC_B),
    DemoDoc("demo-doc-b3", "seed-app-06", "building-plan.pdf", C.BUILDING_PLAN, "Demo: building plan", PLAN_B),
    DemoDoc("demo-doc-b4", "seed-app-06", "building-plan-copy.pdf", C.BUILDING_PLAN,
            "Demo: exact duplicate re-upload", PLAN_B, copy_of="demo-doc-b3"),
    # Unreadable/ambiguous example: seed-app-09 (Aravalli).
    DemoDoc("demo-doc-c1", "seed-app-09", "scanned-fire-certificate.pdf", C.FIRE_SAFETY_CERTIFICATE,
            "Demo: image-only scan (needs OCR)", FIRE_C_SCAN, image_only=True),
    DemoDoc("demo-doc-c2", "seed-app-09", "university-noc.pdf", C.UNIVERSITY_NOC,
            "Demo: wrong category selected (content is a resolution)", TRUST_AS_NOC_C),
    DemoDoc("demo-doc-c3", "seed-app-09", "university-noc-2026.pdf", C.UNIVERSITY_NOC,
            "Demo: ambiguous date, missing NOC reference", NOC_C),
    DemoDoc("demo-doc-c4", "seed-app-09", "completion-certificate-protected.pdf", C.COMPLETION_CERTIFICATE,
            "Demo: password-protected PDF", COMPLETION_C, encrypt=True),
]

ISSUER_REFERENCES = [
    dict(seed_key="demo-ref-1", reference_code="SYN-REF-0001", document_category=C.FIRE_SAFETY_CERTIFICATE,
         issuing_authority="Synthetic Municipal Fire Services, Pune (Fictional)",
         certificate_number="SYN-FSC/PUN/2026/0142", institution_name=DECCAN, issue_date="2026-03-14",
         valid_until="2029-03-13", availability=ReferenceAvailability.AVAILABLE),
    dict(seed_key="demo-ref-2", reference_code="SYN-REF-0002", document_category=C.OCCUPANCY_CERTIFICATE,
         issuing_authority="Synthetic Pune Development Authority (Fictional)",
         certificate_number="SYN-OC/PUN/2024/0077", institution_name=DECCAN, issue_date="2024-07-22",
         valid_until=None, availability=ReferenceAvailability.UNAVAILABLE),
    dict(seed_key="demo-ref-3", reference_code="SYN-REF-0003", document_category=C.FIRE_SAFETY_CERTIFICATE,
         issuing_authority="Synthetic Hooghly Fire Services (Fictional)",
         certificate_number="SYN-FSC/HGY/2023/0019", institution_name=HOOGHLY, issue_date="2023-01-02",
         valid_until="2025-12-31", availability=ReferenceAvailability.AVAILABLE),
    dict(seed_key="demo-ref-4", reference_code="SYN-REF-0004", document_category=C.OCCUPANCY_CERTIFICATE,
         issuing_authority="Synthetic Hooghly Development Authority (Fictional)",
         certificate_number="SYN-OC/HGY/2022/0450", institution_name="Hooghly Riverbank Polytechnic (Synthetic)",
         issue_date="2022-09-19", valid_until=None, availability=ReferenceAvailability.AVAILABLE),
]


@dataclass
class DemoSeedResult:
    documents_created: int = 0
    documents_skipped: int = 0
    references_created: int = 0
    notes: list[str] = field(default_factory=list)


def seed_issuer_references(session: Session, result: DemoSeedResult) -> None:
    for ref in ISSUER_REFERENCES:
        if session.execute(select(IssuerReferenceRecord.id).where(
                IssuerReferenceRecord.seed_key == ref["seed_key"])).first():
            continue
        session.add(IssuerReferenceRecord(**ref, certificate_number_normalized=normalize_identifier(
            ref["certificate_number"])))
        result.references_created += 1
    session.commit()


def seed_demo_documents(session: Session, storage: DocumentStorage, max_upload_bytes: int) -> DemoSeedResult:
    result = DemoSeedResult()
    seed_issuer_references(session, result)
    for demo in DEMO_DOCUMENTS:
        if session.execute(select(Document.id).where(Document.seed_key == demo.seed_key)).first():
            result.documents_skipped += 1
            continue
        application = session.execute(select(Application).where(
            Application.seed_key == demo.application_seed_key)).scalar_one_or_none()
        if application is None:
            result.notes.append(f"{demo.seed_key}: demo application {demo.application_seed_key} not found; skipped.")
            continue
        if demo.copy_of:
            # PDF writers embed a unique file ID, so an exact duplicate must reuse the stored bytes.
            source = session.execute(select(Document).where(Document.seed_key == demo.copy_of)).scalar_one_or_none()
            path = storage.open_path(source.storage_key) if source else None
            if path is None:
                result.notes.append(f"{demo.seed_key}: source document {demo.copy_of} unavailable; skipped.")
                continue
            content = path.read_bytes()
        else:
            content = build_pdf(demo.lines, image_only=demo.image_only, encrypt=demo.encrypt, title=demo.filename)
        if len(content) > max_upload_bytes:
            result.notes.append(f"{demo.seed_key}: larger than the upload limit; skipped.")
            continue
        temp = storage.new_temp_path()
        temp.write_bytes(content)
        received = document_service.ReceivedFile(temp, len(content), hashlib.sha256(content).hexdigest())
        try:
            document_service.store_document(
                session, storage, application_code=application.application_code, received=received,
                filename=demo.filename, category=demo.category, description=demo.description,
                seed_key=demo.seed_key)
        except AppError as exc:
            result.notes.append(f"{demo.seed_key}: not added to {application.application_code} ({exc.message})")
            continue
        result.documents_created += 1
    return result
