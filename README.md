# Health_risk_app

智慧健康日誌與風險評估系統。這是期末挑戰任務題目 A 的實作：Python 標準函式庫 HTTP API、SQLite 資料庫、原生 HTML/CSS/JS 前端。

## 執行方式

```powershell
python server.py
```

開啟瀏覽器：

```text
http://127.0.0.1:8000
```

## API

- `GET /health-logs`：取得所有健康日誌紀錄
- `POST /health-logs`：新增一筆健康日誌，並寫入決策樹分類出的 `risk_level`
- `PUT /health-logs/:id`：修改指定日誌，並重新分類
- `DELETE /health-logs/:id`：刪除指定日誌
- `GET /health-logs/risk`：依最新紀錄回傳目前風險等級與資料筆數統計

程式也保留 `/api/health-logs` 這組相容路徑。

## 決策樹

分類邏輯在 `server.py` 的 `classify_risk()`：

1. 先判斷睡眠時數。
2. 再依睡眠分支判斷步數。
3. 最後用心情分數處理高、中、低風險。

這不是單一 if 判斷，而是符合題目要求的多層分支。

## 資料庫

第一次啟動時會建立 `health_logs.db`，並自動產生 90 筆種子資料：

- 約 25 筆高風險訊號：睡眠少、步數少、心情差
- 約 40 筆中間混合資料
- 約 25 筆低風險訊號：睡眠足、步數多、心情好
