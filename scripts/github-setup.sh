#!/bin/bash
# GitHub CLI の設定保存先（~/.config が root 所有の場合の回避策）
export GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.local/gh-config}"
mkdir -p "$GH_CONFIG_DIR"

cd "$(dirname "$0")/.."

echo "GH_CONFIG_DIR=$GH_CONFIG_DIR"
echo ""
echo "1. 未ログインの場合:"
echo "   gh auth login"
echo ""
echo "2. リポジトリ作成＆push:"
echo "   gh repo create ai-ocr --public --source=. --remote=origin --push --description \"AI OCR帳票読み取りツール\""
echo ""

if ! gh auth status &>/dev/null; then
  echo "→ 先に gh auth login を実行してください"
  exit 1
fi

gh repo create ai-ocr --public --source=. --remote=origin --push \
  --description "AI OCR帳票読み取りツール"
