"""OCRサービス — エンジン差し替え可能な設計。"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.config import TESSERACT_LANG


class OcrEngine(ABC):
    @abstractmethod
    def run_ocr(self, file_path: str) -> tuple[str, str]:
        """OCRを実行し (raw_text, engine_name) を返す。"""
        ...


class TesseractOcrEngine(OcrEngine):
    """Tesseract OCR — 画像・PDFから実際に文字を読み取る。"""

    def run_ocr(self, file_path: str) -> tuple[str, str]:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            text = self._ocr_pdf(path, pytesseract, Image, ImageEnhance, ImageFilter)
        elif suffix in {".jpg", ".jpeg", ".png"}:
            text = self._ocr_image(path, pytesseract, Image, ImageEnhance, ImageFilter)
        else:
            raise ValueError(f"対応していないファイル形式です: {suffix}")

        cleaned = text.strip()
        if not cleaned:
            raise ValueError(
                "OCRでテキストを読み取れませんでした。画像の解像度や文字の鮮明さを確認してください。"
            )
        return cleaned, f"tesseract ({TESSERACT_LANG})"

    def _preprocess_image(self, img, ImageEnhance, ImageFilter):
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = img.filter(ImageFilter.SHARPEN)
        return img

    def _ocr_image(self, path, pytesseract, Image, ImageEnhance, ImageFilter) -> str:
        img = Image.open(path)
        img = self._preprocess_image(img, ImageEnhance, ImageFilter)
        return pytesseract.image_to_string(img, lang=TESSERACT_LANG)

    def _ocr_pdf(self, path, pytesseract, Image, ImageEnhance, ImageFilter) -> str:
        # テキスト埋め込みPDFは pypdf で直接抽出（精度が高い）
        embedded = self._extract_embedded_pdf_text(path)
        if embedded and len(embedded.strip()) >= 10:
            return embedded

        # スキャンPDFはページ画像化して OCR
        from pdf2image import convert_from_path

        pages = convert_from_path(str(path), dpi=300)
        texts = []
        for page in pages:
            processed = self._preprocess_image(page, ImageEnhance, ImageFilter)
            page_text = pytesseract.image_to_string(processed, lang=TESSERACT_LANG)
            if page_text.strip():
                texts.append(page_text.strip())
        return "\n\n".join(texts)

    def _extract_embedded_pdf_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text.strip())
            return "\n".join(parts)
        except Exception:
            return ""


def get_ocr_engine(engine_name: str = "tesseract") -> OcrEngine:
    if engine_name == "tesseract":
        return TesseractOcrEngine()
    raise ValueError(f"未対応のOCRエンジンです: {engine_name}")


def run_ocr(file_path: str, engine_name: str = "tesseract") -> tuple[str, str]:
    """OCRを実行する統一エントリポイント。"""
    engine = get_ocr_engine(engine_name)
    return engine.run_ocr(file_path)


def is_tesseract_available() -> bool:
    try:
        import pytesseract
        from PIL import Image

        pytesseract.get_tesseract_version()
        Image.new("RGB", (1, 1))
        return True
    except Exception:
        return False
