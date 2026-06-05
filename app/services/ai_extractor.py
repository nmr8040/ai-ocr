"""AI項目抽出サービス — プロバイダ差し替え可能な設計。

将来的に以下に差し替え可能:
- OpenAI API
- Anthropic API
- ローカルLLM
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional


class AiExtractor(ABC):
    @abstractmethod
    def extract_fields(self, raw_text: str) -> dict:
        """OCRテキストから項目を抽出する。"""
        ...


class DummyAiExtractor(AiExtractor):
    """デモ用ダミーAI抽出。キーワードマッチングで項目を推定する。"""

    TYPE_KEYWORDS: dict[str, list[str]] = {
        "点検表": ["点検", "点検表", "点検項目"],
        "作業日報": ["作業日報", "日報", "作業内容"],
        "異常報告書": ["異常報告", "異常内容", "異常"],
        "ヒヤリハット報告書": ["ヒヤリハット", "ヒヤリ", "ハット"],
        "請求書": ["請求書", "請求", "合計金額", "税込"],
        "納品書": ["納品書", "納品", "納品日"],
        "検査表": ["検査表", "検査", "検査結果"],
    }

    def extract_fields(self, raw_text: str) -> dict:
        document_type = self._detect_document_type(raw_text)
        return normalize_extracted_fields(
            {
                "document_type": document_type,
                "date": self._extract_date(raw_text),
                "person_in_charge": self._extract_field(raw_text, ["担当者", "報告者", "記入者"]),
                "department": self._extract_field(raw_text, ["部署", "所属", "部門"]),
                "company_name": self._extract_field(raw_text, ["会社名", "会社", "取引先"]),
                "amount": self._extract_field(raw_text, ["金額", "合計", "請求額", "税込"]),
                "quantity": self._extract_field(raw_text, ["数量", "個数", "件数"]),
                "abnormal_content": self._extract_field(
                    raw_text, ["異常内容", "異常", "不具合", "問題"]
                ),
                "note": self._extract_field(raw_text, ["備考", "メモ", "特記事項"]),
                "action": self._extract_field(
                    raw_text, ["対応内容", "対応", "処置", "措置"]
                ),
            }
        )

    def _detect_document_type(self, text: str) -> str:
        for doc_type, keywords in self.TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return doc_type
        return "不明"

    def _extract_date(self, text: str) -> str:
        patterns = [
            r"日付[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}年\d{1,2}月\d{1,2}日)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_date(match.group(1))
        return str(date.today())

    def _normalize_date(self, date_str: str) -> str:
        cleaned = (
            date_str.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
        )
        parts = cleaned.split("-")
        if len(parts) == 3:
            return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        return date_str

    def _extract_field(self, text: str, labels: list[str]) -> str:
        for label in labels:
            pattern = rf"{label}[：:\s]+(.+?)(?:\n|$)"
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                if value and value != "—" and value != "-":
                    return value
        return ""


class OpenAiExtractor(AiExtractor):
    """OpenAI API（将来実装用スタブ）。"""

    def extract_fields(self, raw_text: str) -> dict:
        raise NotImplementedError(
            "OpenAI API は未実装です。OPENAI_API_KEY を設定し、実装を追加してください。"
        )


def get_ai_extractor(provider: str = "dummy") -> AiExtractor:
    providers: dict[str, AiExtractor] = {
        "dummy": DummyAiExtractor(),
        "openai": OpenAiExtractor(),
    }
    return providers.get(provider, DummyAiExtractor())


def extract_fields_with_ai(raw_text: str, provider: str = "dummy") -> dict:
    """AI項目抽出の統一エントリポイント。"""
    extractor = get_ai_extractor(provider)
    return extractor.extract_fields(raw_text)


def normalize_extracted_fields(ai_result: dict) -> dict:
    """AI抽出結果を正規化する。"""
    defaults = {
        "document_type": "",
        "date": "",
        "person_in_charge": "",
        "department": "",
        "company_name": "",
        "amount": "",
        "quantity": "",
        "abnormal_content": "",
        "note": "",
        "action": "",
    }
    normalized = {**defaults, **ai_result}
    for key in defaults:
        if normalized[key] is None:
            normalized[key] = ""
        else:
            normalized[key] = str(normalized[key]).strip()
    return normalized


def fields_to_json(fields: dict) -> str:
    return json.dumps(fields, ensure_ascii=False, indent=2)


def fields_from_json(json_str: Optional[str]) -> dict:
    if not json_str:
        return normalize_extracted_fields({})
    return normalize_extracted_fields(json.loads(json_str))
