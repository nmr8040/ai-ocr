"""OCRサービス — エンジン差し替え可能な設計。

将来的に以下に差し替え可能:
- Tesseract OCR
- Google Vision API
- OpenAI Vision
- ローカルOCR
"""

from abc import ABC, abstractmethod
from pathlib import Path


class OcrEngine(ABC):
    @abstractmethod
    def run_ocr(self, file_path: str) -> tuple[str, str]:
        """OCRを実行し (raw_text, engine_name) を返す。"""
        ...


class DummyOcrEngine(OcrEngine):
    """デモ用ダミーOCR。ファイル名からサンプルテキストを生成する。"""

    def run_ocr(self, file_path: str) -> tuple[str, str]:
        file_name = Path(file_path).stem
        suffix = Path(file_path).suffix.lower()

        sample_text = f"""【帳票読み取り結果 — ダミーOCR】
ファイル名: {file_name}{suffix}

点検表
日付: 2026-06-02
担当者: 山田太郎
部署: 製造1課
会社名: 株式会社サンプル

点検項目:
1. 温度センサー — 異常（基準値超過）
2. 圧力計 — 正常
3. 流量計 — 正常

異常内容: 温度が基準値を超過（設定値: 80℃ / 実測値: 92℃）
備考: 要確認。再点検を実施予定。
対応内容: 担当者へ確認、冷却装置の点検を実施

数量: 1
金額: —

※ これはダミーOCR結果です。本番では Tesseract / Google Vision / OpenAI Vision 等に差し替えてください。
"""
        return sample_text, "dummy_ocr_v1"


class TesseractOcrEngine(OcrEngine):
    """Tesseract OCR（将来実装用スタブ）。"""

    def run_ocr(self, file_path: str) -> tuple[str, str]:
        raise NotImplementedError(
            "Tesseract OCR は未実装です。pytesseract をインストールし、実装を追加してください。"
        )


def get_ocr_engine(engine_name: str = "dummy") -> OcrEngine:
    engines: dict[str, OcrEngine] = {
        "dummy": DummyOcrEngine(),
        "tesseract": TesseractOcrEngine(),
    }
    return engines.get(engine_name, DummyOcrEngine())


def run_ocr(file_path: str, engine_name: str = "dummy") -> tuple[str, str]:
    """OCRを実行する統一エントリポイント。"""
    engine = get_ocr_engine(engine_name)
    return engine.run_ocr(file_path)
