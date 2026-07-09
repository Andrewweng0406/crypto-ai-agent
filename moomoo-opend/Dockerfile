# Railway 上跑 Moomoo/Futu OpenD 閘道程式，讓後端 FastAPI 服務能連進去拉期權
# 資料。基於社群維護的 image（manhinhang/futu-opend-docker），這裡只加一層
# 薄薄的 entrypoint wrapper：從環境變數 FUTU_PEM_BASE64 還原出 OpenD 需要的
# RSA 金鑰檔案，這樣金鑰內容只存在 Railway 的環境變數（機密儲存），不需要把
# 檔案 commit 進這個公開的 GitHub repo。
FROM ghcr.io/manhinhang/futu-opend-docker:ubuntu-stable

COPY --chown=futu:futu entrypoint-wrapper.sh /bin/entrypoint-wrapper.sh
RUN chmod +x /bin/entrypoint-wrapper.sh

CMD ["/bin/entrypoint-wrapper.sh"]
