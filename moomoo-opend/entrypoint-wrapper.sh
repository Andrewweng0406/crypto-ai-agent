#!/bin/bash
# 從 FUTU_PEM_BASE64 環境變數還原 RSA 金鑰檔案（如果有設定的話），再照原本
# image 的方式啟動 OpenD。金鑰內容不進 git，只存在 Railway 的環境變數。
set -e

if [ -n "$FUTU_PEM_BASE64" ]; then
  mkdir -p "$(dirname "${FUTU_OPEND_RSA_FILE_PATH:-/.futu/futu.pem}")"
  echo "$FUTU_PEM_BASE64" | base64 -d > "${FUTU_OPEND_RSA_FILE_PATH:-/.futu/futu.pem}"
fi

exec /bin/start.sh
