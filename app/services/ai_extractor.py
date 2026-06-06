"""AI項目抽出サービス — OpenAI API またはルールベース抽出。"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from app.config import DOCUMENT_TYPES, OPENAI_API_KEY, OPENAI_MODEL, get_effective_ai_provider

EXTRACTION_SCHEMA = {
    "document_type": "帳票種別（点検表/作業日報/異常報告書/ヒヤリハット報告書/請求書/納品書/検査表/不明）",
    "date": "日付（YYYY-MM-DD形式）",
    "person_in_charge": "担当者名",
    "department": "部署名",
    "company_name": "会社名",
    "amount": "金額",
    "quantity": "数量",
    "abnormal_content": "異常内容",
    "note": "備考",
    "action": "対応内容",
}


class AiExtractor(ABC):
    @abstractmethod
    def extract_fields(self, raw_text: str) -> dict:
        ...


class RuleBasedAiExtractor(AiExtractor):
    """OCRテキストから帳票項目をルールベースで抽出する。"""

    TYPE_KEYWORDS: dict[str, list[str]] = {
        "点検表": ["点検表", "点検項目", "点検日", "点検結果"],
        "作業日報": ["作業日報", "日報", "作業内容", "作業時間"],
        "異常報告書": ["異常報告", "異常報告書", "異常内容", "異常発生"],
        "ヒヤリハット報告書": ["ヒヤリハット", "ヒヤリ・ハット", "ヒヤリハット報告"],
        "請求書": ["請求書", "請求番号", "合計金額", "税込", "御請求"],
        "納品書": ["納品書", "納品日", "納品先", "納品数量"],
        "検査表": ["検査表", "検査結果", "検査日", "検査項目"],
    }

    def extract_fields(self, raw_text: str) -> dict:
        document_type = self._detect_document_type(raw_text)
        return normalize_extracted_fields(
            {
                "document_type": document_type,
                "date": self._extract_date(raw_text),
                "person_in_charge": self._extract_field(
                    raw_text, ["担当者", "報告者", "記入者", "作成者", "氏名"]
                ),
                "department": self._extract_field(
                    raw_text, ["部署", "所属", "部門", "課名"]
                ),
                "company_name": self._extract_field(
                    raw_text, ["会社名", "取引先", "顧客名", "納品先"]
                ),
                "amount": self._extract_amount(raw_text),
                "quantity": self._extract_field(
                    raw_text, ["数量", "個数", "件数", "台数"]
                ),
                "abnormal_content": self._extract_multiline_field(
                    raw_text, ["異常内容", "異常の内容", "不具合内容", "問題内容"]
                ),
                "note": self._extract_multiline_field(
                    raw_text, ["備考", "特記事項", "メモ", "連絡事項"]
                ),
                "action": self._extract_multiline_field(
                    raw_text, ["対応内容", "処置内容", "措置内容", "対応", "処置"]
                ),
            }
        )

    def _detect_document_type(self, text: str) -> str:
        scores: dict[str, int] = {}
        for doc_type, keywords in self.TYPE_KEYWORDS.items():
            score = sum(2 if kw == doc_type else 1 for kw in keywords if kw in text)
            if score:
                scores[doc_type] = score
        if scores:
            return max(scores, key=scores.get)
        return "不明"

    def _extract_date(self, text: str) -> str:
        patterns = [
            r"(?:日付|報告日|作成日|点検日|納品日|請求日)[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)",
            r"(\d{4}年\d{1,2}月\d{1,2}日)",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_date(match.group(1))
        return ""

    def _normalize_date(self, date_str: str) -> str:
        cleaned = (
            date_str.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
        )
        parts = cleaned.split("-")
        if len(parts) == 3:
            try:
                return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            except ValueError:
                return date_str
        return date_str

    def _extract_field(self, text: str, labels: list[str]) -> str:
        for label in labels:
            pattern = rf"{label}\s*[：:：\s]\s*(.+?)(?:\n|$)"
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                if value and value not in {"—", "-", "―", "なし"}:
                    return value
        return ""

    def _extract_multiline_field(self, text: str, labels: list[str]) -> str:
        for label in labels:
            pattern = rf"{label}\s*[：:：\s]\s*(.+?)(?:\n(?:[^\n：:：]+[：:：]|\Z))"
            match = re.search(pattern, text, re.DOTALL)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"\n{3,}", "\n", value)
                if value and value not in {"—", "-", "―", "なし"}:
                    return value
        return self._extract_field(text, labels)

    def _extract_amount(self, text: str) -> str:
        for label in ["合計金額", "請求金額", "金額", "税込", "合計"]:
            pattern = rf"{label}\s*[：:：\s]\s*[¥￥]?\s*([\d,，]+)"
            match = re.search(pattern, text)
            if match:
                return match.group(1).replace("，", ",")
        return self._extract_field(text, ["金額", "合計"])


class OpenAiExtractor(AiExtractor):
    """OpenAI API で帳票項目を JSON 抽出する。"""

    SYSTEM_PROMPT = """あなたは日本語の業務帳票を解析するアシスタントです。
OCRで読み取ったテキストから、以下の項目をJSON形式で抽出してください。
読み取れない項目は空文字 "" にしてください。
document_type は次のいずれか: 点検表, 作業日報, 異常報告書, ヒヤリハット報告書, 請求書, 納品書, 検査表, 不明
date は YYYY-MM-DD 形式にしてください。"""

    def extract_fields(self, raw_text: str) -> dict:
        from openai import OpenAI

        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY が設定されていません。")

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "以下のOCRテキストから帳票項目を抽出してください。\n\n"
                        f"{raw_text[:8000]}"
                    ),
                },
            ],
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return normalize_extracted_fields(parsed)


def get_ai_extractor(provider: Optional[str] = None) -> AiExtractor:
    resolved = provider or get_effective_ai_provider()
    if resolved == "openai":
        if OPENAI_API_KEY:
            return OpenAiExtractor()
        return RuleBasedAiExtractor()
    if resolved == "rule":
        return RuleBasedAiExtractor()
    raise ValueError(f"未対応のAIプロバイダです: {resolved}")


def extract_fields_with_ai(raw_text: str, provider: Optional[str] = None) -> dict:
    extractor = get_ai_extractor(provider)
    return extractor.extract_fields(raw_text)


def normalize_extracted_fields(ai_result: dict) -> dict:
    defaults = {key: "" for key in EXTRACTION_SCHEMA}
    normalized = {**defaults, **(ai_result or {})}
    for key in defaults:
        value = normalized[key]
        normalized[key] = "" if value is None else str(value).strip()

    doc_type = normalized["document_type"]
    if doc_type and doc_type not in DOCUMENT_TYPES:
        normalized["document_type"] = "不明"
    return normalized


def fields_to_json(fields: dict) -> str:
    return json.dumps(fields, ensure_ascii=False, indent=2)


def fields_from_json(json_str: Optional[str]) -> dict:
    if not json_str:
        return normalize_extracted_fields({})
    return normalize_extracted_fields(json.loads(json_str))


def get_ai_provider_label() -> str:
    provider = get_effective_ai_provider()
    if provider == "openai":
        return f"OpenAI ({OPENAI_MODEL})"
    return "ルールベース抽出"
