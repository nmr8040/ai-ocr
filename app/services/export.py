"""確定済みデータの Excel / CSV エクスポートサービス。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook

from app.config import EXTRACTABLE_FIELDS, EXPORT_DIR
from app.services.ai_extractor import fields_from_json


def _build_export_rows(documents: list) -> tuple[list[str], list[list]]:
    headers = [
        "ID",
        "ファイル名",
        "帳票種別",
        "ステータス",
        "アップロード日時",
        "確定日時",
        "確定者",
    ]
    for _, label in EXTRACTABLE_FIELDS:
        headers.append(label)

    rows: list[list] = []
    for doc in documents:
        extracted = doc.extracted_fields[-1] if doc.extracted_fields else None
        if not extracted or not extracted.confirmed_data_json:
            continue

        fields = fields_from_json(extracted.confirmed_data_json)
        row = [
            doc.id,
            doc.file_name,
            doc.document_type or fields.get("document_type", ""),
            doc.status,
            doc.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if doc.uploaded_at else "",
            extracted.confirmed_at.strftime("%Y-%m-%d %H:%M:%S")
            if extracted.confirmed_at
            else "",
            extracted.confirmed_by or "",
        ]
        for key, _ in EXTRACTABLE_FIELDS:
            row.append(fields.get(key, ""))
        rows.append(row)

    return headers, rows


def export_to_csv(documents: list, filename: Optional[str] = None) -> str:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    file_path = EXPORT_DIR / filename
    headers, rows = _build_export_rows(documents)

    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return str(file_path)


def export_to_excel(documents: list, filename: Optional[str] = None) -> str:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    file_path = EXPORT_DIR / filename
    headers, rows = _build_export_rows(documents)

    wb = Workbook()
    ws = wb.active
    ws.title = "確定済み帳票"
    ws.append(headers)
    for row in rows:
        ws.append(row)

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[column].width = min(max_length + 4, 50)

    wb.save(file_path)
    return str(file_path)
