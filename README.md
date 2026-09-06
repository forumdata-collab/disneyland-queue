# 香港迪士尼樂園即時等候時間 | HK Disneyland Live Wait Times

> 免費、無廣告、免安裝 — 香港迪士尼樂園各設施即時排隊等候時間，地圖 + 清單兩種顯示。

🌐 **Live site:** https://disneyland.we1co.me/

## 功能

- 🗺️ **互動地圖** — 49 個景點（遊樂設施 / 角色會面 / 餐飲）按真實座標顯示，badge 直接顯示等候分鐘
- 📋 **等候時間清單** — 按等候時間由短至長排序，一眼睇晒邊個玩先
- 🔄 **自動更新** — 每日 09:00–22:00 每 5 分鐘同步一次（公園開放時段）
- 🟢🟡🔴 **狀態顏色** — 營運中（綠）/ 維修中（黃）/ 已關閉（紅）
- 🌐 繁體中文為主，設施保留英文原名對照

## 數據源

[themeparks.wiki API](https://api.themeparks.wiki/)（免費、免 key、非官方）— 提供香港迪士尼樂園各設施即時等候時間、狀態（Operating / Closed / Refurbishment）及地理座標。

## 架構

```
disneyland-map/
├── index.html          地圖 + 清單前端（Leaflet + 原生 JS，無框架）
├── fetch_hkdl.py       抓取 API → data/hkdl.json（含中文名對照）
├── disney_sync.sh      抓取 + wrangler deploy（cron 用，成功靜默）
└── data/hkdl.json      即時狀態（由 fetch_hkdl.py 生成，gitignored）
```

## 部署

```bash
# 抓取數據（本地）
python3 fetch_hkdl.py

# 部署到 Cloudflare Pages
CLOUDFLARE_API_TOKEN=$CF_WORKERS_TOKEN npx wrangler pages deploy . --project-name disneyland-queue --branch=main
```

Cron：`*/5 9-22 * * *` 執行 `disney_sync.sh`（成功靜默，失敗先出聲）。

## 免責聲明

本網站為非官方、非牟利社區工具。等候時間由第三方 API 提供，僅供參考，實際以樂園現場及官方 App 為準。
