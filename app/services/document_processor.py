"""帳票処理パイプライン: アップロード → OCR → AI抽出 → 確認待ち"""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Document, ExtractedField, OcrResult, RevisionLog
from app.services.ai_extractor import extract_fields_with_ai, fields_to_json
from app.services.ocr import run_ocr


def add_revision_log(
    db: Session,
    document_id: int,
    action: str,
    detail: str,
    changed_by: Optional[str] = None,
):
    log = RevisionLog(
        document_id=document_id,
        action=action,
        detail=detail,
        changed_by=changed_by,
    )
    db.add(log)


def process_document(db: Session, document: Document, ocr_engine: str = "dummy", ai_provider: str = "dummy"):
    """OCR → AI抽出 → 確認待ちステータスへ遷移する。"""
    try:
        raw_text, engine_name = run_ocr(document.file_path, engine_name=ocr_engine)

        ocr_result = OcrResult(
            document_id=document.id,
            raw_text=raw_text,
            ocr_engine=engine_name,
        )
        db.add(ocr_result)
        document.status = "ocr_done"
        add_revision_log(db, document.id, "OCR実行", f"エンジン: {engine_name}")

        extracted = extract_fields_with_ai(raw_text, provider=ai_provider)
        field_record = ExtractedField(
            document_id=document.id,
            field_data_json=fields_to_json(extracted),
        )
        db.add(field_record)

        document.document_type = extracted.get("document_type", "不明")
        document.status = "awaiting_review"
        document.updated_at = datetime.utcnow()
        add_revision_log(
            db,
            document.id,
            "AI項目抽出",
            f"帳票種別: {extracted.get('document_type', '不明')}",
        )

        db.commit()
        return True, None

    except Exception as e:
        document.status = "error"
        document.updated_at = datetime.utcnow()
        add_revision_log(
            db,
            document.id,
            "エラー",
            f"{str(e)}\n{traceback.format_exc()}",
        )
        db.commit()
        return False, str(e)


def confirm_document(
    db: Session,
    document: Document,
    confirmed_data: dict,
    confirmed_by: str = "ユーザー",
):
    """人が確認・修正したデータを確定保存する。"""
    if not document.extracted_fields:
        raise ValueError("抽出データが存在しません。")

    field_record = document.extracted_fields[-1]
    old_data = field_record.confirmed_data_json or field_record.field_data_json

    field_record.confirmed_data_json = fields_to_json(confirmed_data)
    field_record.confirmed_by = confirmed_by
    field_record.confirmed_at = datetime.utcnow()
    field_record.updated_at = datetime.utcnow()

    document.document_type = confirmed_data.get("document_type", document.document_type)
    document.status = "confirmed"
    document.updated_at = datetime.utcnow()

    add_revision_log(
        db,
        document.id,
        "確定保存",
        json.dumps(
            {"before": json.loads(old_data) if old_data else {}, "after": confirmed_data},
            ensure_ascii=False,
        ),
        changed_by=confirmed_by,
    )

    db.commit()
