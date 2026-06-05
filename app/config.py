from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR = BASE_DIR / "data"

DATABASE_URL = f"sqlite:///{DATA_DIR / 'ai_ocr.db'}"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_UPLOAD_SIZE_MB = 20

DOCUMENT_TYPES = [
    "点検表",
    "作業日報",
    "異常報告書",
    "ヒヤリハット報告書",
    "請求書",
    "納品書",
    "検査表",
    "不明",
]

STATUSES = {
    "pending": "未処理",
    "ocr_done": "OCR済み",
    "awaiting_review": "確認待ち",
    "confirmed": "確定済み",
    "error": "エラー",
}

EXTRACTABLE_FIELDS = [
    ("document_type", "帳票種別"),
    ("date", "日付"),
    ("person_in_charge", "担当者"),
    ("department", "部署"),
    ("company_name", "会社名"),
    ("amount", "金額"),
    ("quantity", "数量"),
    ("abnormal_content", "異常内容"),
    ("note", "備考"),
    ("action", "対応内容"),
]
