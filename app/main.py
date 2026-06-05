import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import (
    ALLOWED_EXTENSIONS,
    BASE_DIR,
    DOCUMENT_TYPES,
    EXTRACTABLE_FIELDS,
    EXPORT_DIR,
    MAX_UPLOAD_SIZE_MB,
    STATUSES,
    UPLOAD_DIR,
)
from app.database import get_db, init_db
from app.models import Document, ExportLog, RevisionLog
from app.services.ai_extractor import fields_from_json, normalize_extracted_fields
from app.services.document_processor import confirm_document, process_document
from app.services.export import export_to_csv, export_to_excel

app = FastAPI(title="AI OCR 帳票読み取りツール", version="1.0.0")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


@app.on_event("startup")
def on_startup():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    init_db()


def _get_document_or_404(db: Session, doc_id: int) -> Document:
    doc = (
        db.query(Document)
        .options(
            joinedload(Document.ocr_results),
            joinedload(Document.extracted_fields),
            joinedload(Document.revision_logs),
        )
        .filter(Document.id == doc_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="帳票が見つかりません。")
    return doc


def _doc_summary(doc: Document) -> dict:
    fields = {}
    if doc.extracted_fields:
        latest = doc.extracted_fields[-1]
        if latest.confirmed_data_json:
            fields = fields_from_json(latest.confirmed_data_json)
        else:
            fields = fields_from_json(latest.field_data_json)

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "document_type": doc.document_type or fields.get("document_type", ""),
        "date": fields.get("date", ""),
        "person_in_charge": fields.get("person_in_charge", ""),
        "status": doc.status,
        "status_label": STATUSES.get(doc.status, doc.status),
        "uploaded_at": doc.uploaded_at,
    }


# ── ダッシュボード ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total = db.query(Document).count()
    status_counts = {
        s: db.query(Document).filter(Document.status == s).count()
        for s in STATUSES
    }
    type_counts = (
        db.query(Document.document_type, func.count(Document.id))
        .group_by(Document.document_type)
        .all()
    )
    recent = (
        db.query(Document)
        .options(joinedload(Document.extracted_fields))
        .order_by(Document.uploaded_at.desc())
        .limit(10)
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active_page": "dashboard",
            "total": total,
            "status_counts": status_counts,
            "status_labels": STATUSES,
            "type_counts": type_counts,
            "recent_docs": [_doc_summary(d) for d in recent],
        },
    )


# ── アップロード ──────────────────────────────────────────

@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "active_page": "upload"},
    )


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "active_page": "upload", "error": "ファイルが選択されていません。"},
            status_code=400,
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "active_page": "upload",
                "error": f"対応していないファイル形式です。{', '.join(ALLOWED_EXTENSIONS)} のみ対応しています。",
            },
            status_code=400,
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "active_page": "upload",
                "error": f"ファイルサイズが {MAX_UPLOAD_SIZE_MB}MB を超えています。",
            },
            status_code=400,
        )

    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        file_name=file.filename,
        file_path=str(file_path),
        file_type=ext.lstrip("."),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    success, error = process_document(db, doc)
    if success:
        return RedirectResponse(url=f"/review/{doc.id}", status_code=303)
    return RedirectResponse(url=f"/documents/{doc.id}", status_code=303)


# ── 読み取り履歴 ──────────────────────────────────────────

@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request, db: Session = Depends(get_db)):
    docs = (
        db.query(Document)
        .options(joinedload(Document.extracted_fields))
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "active_page": "history",
            "documents": [_doc_summary(d) for d in docs],
        },
    )


# ── 確認待ち ──────────────────────────────────────────

@app.get("/pending", response_class=HTMLResponse)
def pending_page(request: Request, db: Session = Depends(get_db)):
    docs = (
        db.query(Document)
        .options(joinedload(Document.extracted_fields))
        .filter(Document.status == "awaiting_review")
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "pending.html",
        {
            "request": request,
            "active_page": "pending",
            "documents": [_doc_summary(d) for d in docs],
        },
    )


# ── 確認・修正画面 ──────────────────────────────────────────

@app.get("/review/{doc_id}", response_class=HTMLResponse)
def review_page(request: Request, doc_id: int, db: Session = Depends(get_db)):
    doc = _get_document_or_404(db, doc_id)
    ocr_text = doc.ocr_results[-1].raw_text if doc.ocr_results else ""
    extracted = {}
    if doc.extracted_fields:
        extracted = fields_from_json(doc.extracted_fields[-1].field_data_json)

    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "active_page": "pending",
            "doc": doc,
            "ocr_text": ocr_text,
            "extracted": extracted,
            "fields": EXTRACTABLE_FIELDS,
            "document_types": DOCUMENT_TYPES,
            "status_label": STATUSES.get(doc.status, doc.status),
        },
    )


@app.post("/review/{doc_id}/confirm")
async def confirm_review(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
):
    doc = _get_document_or_404(db, doc_id)
    form = await request.form()

    confirmed_data = normalize_extracted_fields(
        {key: form.get(key, "") for key, _ in EXTRACTABLE_FIELDS}
    )
    confirmed_by = form.get("confirmed_by", "ユーザー")

    try:
        confirm_document(db, doc, confirmed_data, confirmed_by=confirmed_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(url=f"/documents/{doc_id}", status_code=303)


# ── 詳細画面 ──────────────────────────────────────────

@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_detail(request: Request, doc_id: int, db: Session = Depends(get_db)):
    doc = _get_document_or_404(db, doc_id)
    ocr_text = doc.ocr_results[-1].raw_text if doc.ocr_results else ""
    ocr_engine = doc.ocr_results[-1].ocr_engine if doc.ocr_results else ""

    extracted = {}
    confirmed = {}
    if doc.extracted_fields:
        latest = doc.extracted_fields[-1]
        extracted = fields_from_json(latest.field_data_json)
        if latest.confirmed_data_json:
            confirmed = fields_from_json(latest.confirmed_data_json)

    revisions = sorted(doc.revision_logs, key=lambda r: r.created_at, reverse=True)

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "active_page": "history",
            "doc": doc,
            "ocr_text": ocr_text,
            "ocr_engine": ocr_engine,
            "extracted": extracted,
            "confirmed": confirmed,
            "fields": EXTRACTABLE_FIELDS,
            "revisions": revisions,
            "status_label": STATUSES.get(doc.status, doc.status),
        },
    )


@app.get("/documents/{doc_id}/file")
def serve_document_file(doc_id: int, db: Session = Depends(get_db)):
    doc = _get_document_or_404(db, doc_id)
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません。")

    media_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "pdf": "application/pdf",
    }
    media_type = media_types.get(doc.file_type, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=doc.file_name)


# ── エクスポート ──────────────────────────────────────────

@app.get("/export", response_class=HTMLResponse)
def export_page(request: Request, db: Session = Depends(get_db)):
    docs = (
        db.query(Document)
        .options(joinedload(Document.extracted_fields))
        .filter(Document.status == "confirmed")
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    export_logs = (
        db.query(ExportLog).order_by(ExportLog.exported_at.desc()).limit(20).all()
    )
    return templates.TemplateResponse(
        "export.html",
        {
            "request": request,
            "active_page": "export",
            "documents": [_doc_summary(d) for d in docs],
            "export_logs": export_logs,
        },
    )


@app.post("/export")
async def export_documents(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    export_type = form.get("export_type", "csv")
    selected_ids = form.getlist("selected_ids")

    if not selected_ids:
        return RedirectResponse(url="/export?error=no_selection", status_code=303)

    doc_ids = [int(i) for i in selected_ids]
    docs = (
        db.query(Document)
        .options(joinedload(Document.extracted_fields))
        .filter(Document.id.in_(doc_ids), Document.status == "confirmed")
        .all()
    )

    if not docs:
        return RedirectResponse(url="/export?error=no_confirmed", status_code=303)

    if export_type == "excel":
        file_path = export_to_excel(docs)
        export_type_label = "excel"
    else:
        file_path = export_to_csv(docs)
        export_type_label = "csv"

    log = ExportLog(
        export_type=export_type_label,
        file_path=file_path,
        document_count=len(docs),
    )
    db.add(log)
    db.commit()

    return FileResponse(
        file_path,
        filename=Path(file_path).name,
        media_type="application/octet-stream",
    )


# ── 設定 ──────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "document_types": DOCUMENT_TYPES,
            "extractable_fields": EXTRACTABLE_FIELDS,
        },
    )


# ── 再処理 ──────────────────────────────────────────

@app.post("/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: int, db: Session = Depends(get_db)):
    doc = _get_document_or_404(db, doc_id)
    doc.status = "pending"
    db.commit()
    process_document(db, doc)
    return RedirectResponse(url=f"/review/{doc_id}", status_code=303)
