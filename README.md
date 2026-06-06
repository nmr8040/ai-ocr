# AI OCR 帳票読み取りツール

紙の帳票・PDF・画像をアップロードし、OCRで文字を読み取り、AIで必要項目を抽出、人が確認・修正したうえで Excel/CSV に出力する業務向けツールです。

## 業務フロー

```
アップロード → OCR読み取り → AI項目抽出 → 人が確認・修正 → 確定保存 → Excel/CSV出力
```

**重要:** OCR/AIの結果は自動確定されません。必ず人の確認工程を経てから確定されます。

## 対応帳票

- 点検表 / 作業日報 / 異常報告書 / ヒヤリハット報告書
- 請求書 / 納品書 / 検査表

## 機能一覧

| 機能 | 説明 |
|------|------|
| アップロード | JPG / PNG / PDF に対応 |
| OCR | Tesseract OCR（日本語+英語、画像/PDF対応） |
| AI項目抽出 | OpenAI API またはルールベース抽出 |
| 確認・修正 | 抽出結果を人が編集して確定 |
| 履歴管理 | アップロード済み帳票の一覧・詳細 |
| エクスポート | 確定済みデータを CSV / Excel で出力 |
| ダッシュボード | 件数集計・最近の帳票表示 |

## 起動方法

### Docker（推奨）

```bash
docker compose up --build
```

ブラウザで http://localhost:8000 を開いてください。

### ローカル（Python）

```bash
# macOS: Tesseract と日本語言語パックをインストール
brew install tesseract tesseract-lang poppler

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Render デプロイ

1. GitHub リポジトリ `nmr8040/ai-ocr` を接続
2. Language: **Docker**
3. 環境変数（任意）:
   - `OPENAI_API_KEY` — OpenAI による高精度抽出（未設定時はルールベース）
   - `AI_PROVIDER` — `auto`（デフォルト）/ `openai` / `rule`
   - `OCR_ENGINE` — `tesseract`（デフォルト）

## 使い方

### 1. 帳票をアップロード

1. 左メニュー「アップロード」を開く
2. JPG / PNG / PDF ファイルを選択（またはドラッグ＆ドロップ）
3. 「アップロードして読み取り開始」をクリック
4. 自動的に OCR → AI抽出が実行され、確認画面へ遷移

### 2. 確認・修正して確定

1. 確認画面で OCR全文と AI抽出結果を確認
2. 各項目を必要に応じて修正
3. 「確定保存」ボタンをクリック

### 3. エクスポート

1. 左メニュー「エクスポート」を開く
2. 確定済み帳票にチェックを入れる
3. CSV または Excel を選択して「エクスポート実行」

## 画面構成

- **ダッシュボード** — 件数集計・最近の帳票
- **アップロード** — ファイルアップロード
- **読み取り履歴** — 全帳票一覧
- **確認待ち** — 確認が必要な帳票
- **エクスポート** — CSV/Excel 出力
- **設定** — OCR/AI エンジン情報

## OCR / AI 設定

### 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `OCR_ENGINE` | tesseract | OCRエンジン |
| `AI_PROVIDER` | auto | auto / openai / rule |
| `OPENAI_API_KEY` | — | OpenAI APIキー |
| `OPENAI_MODEL` | gpt-4o-mini | 使用モデル |
| `TESSERACT_LANG` | jpn+eng | OCR言語 |

### OCR

`app/services/ocr.py` で Tesseract OCR を実行します。

```python
from app.services.ocr import run_ocr
raw_text, engine = run_ocr(file_path, engine_name="tesseract")
```

- 画像: Tesseract で直接 OCR
- PDF: テキスト埋め込みPDFは pypdf で抽出、スキャンPDFはページ画像化して OCR

### AI抽出

`app/services/ai_extractor.py` で項目を抽出します。

```python
from app.services.ai_extractor import extract_fields_with_ai, normalize_extracted_fields
fields = extract_fields_with_ai(raw_text)  # OPENAI_API_KEY 設定時は OpenAI を使用
normalized = normalize_extracted_fields(fields)
```

## データベース

SQLite を使用（`data/ai_ocr.db`）。

| テーブル | 説明 |
|----------|------|
| documents | 帳票メタ情報 |
| ocr_results | OCR結果 |
| extracted_fields | AI抽出・確定データ |
| revision_logs | 修正履歴 |
| export_logs | エクスポート履歴 |

## ディレクトリ構成

```
AI OCR/
├── app/
│   ├── main.py              # FastAPI アプリ
│   ├── config.py            # 設定
│   ├── models.py            # DBモデル
│   ├── database.py          # DB接続
│   ├── services/
│   │   ├── ocr.py           # OCR（差し替え可能）
│   │   ├── ai_extractor.py  # AI抽出（差し替え可能）
│   │   ├── export.py        # CSV/Excel出力
│   │   └── document_processor.py
│   ├── templates/           # HTMLテンプレート
│   └── static/              # CSS
├── uploads/                 # アップロードファイル
├── exports/                 # エクスポートファイル
├── data/                    # SQLite DB
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 将来の連携

改善活動管理システム（CAPA）との連携を想定した設計です。

```
帳票読み取り → 異常内容抽出 → 問題登録 → CAPA管理 → 効果確認
```

`abnormal_content` と `action` フィールドが連携の起点となります。

## 技術スタック

- **Backend:** FastAPI + SQLAlchemy
- **DB:** SQLite（オフライン対応）
- **Frontend:** Jinja2 テンプレート
- **Export:** openpyxl（Excel）/ csv（CSV）
- **Container:** Docker + docker-compose
