#!/usr/bin/env python3
"""HK Disneyland wait times fetcher → data/hkdl.json (for disneyland.we1co.me).

Source: https://api.themeparks.wiki (free, no key). Polled by cron.
Output shape: {updated, parkName, attractions: [{name, waitTime, status, active, lat, lon, type}]}
"""
import json, os, time, urllib.request
from pathlib import Path

API = "https://api.themeparks.wiki/preview/parks/HongKongDisneylandPark/waittime"
OUT = Path(__file__).parent / "data" / "hkdl.json"

# 中文名映射（API 係英文名）— 常用設施；未覆蓋嘅回退英文名
ZH = {
    '"it\'s a small world"': "小小世界",
    "Animation Academy": "動畫藝術教室",
    "Ant-Man and The Wasp: Nano Battle!": "蟻俠與黃蜂女：擊戰特攻！",
    "Barrel of Fun": "轉轉彈弓狗",
    "Big Grizzly Mountain Runaway Mine Cars": "灰熊山極速礦車",
    "Castle of Magical Dreams": "奇妙夢想城堡",
    "Cinderella Carousel": "灰姑娘旋轉木馬",
    "Duffy and Friends Play House": "Duffy 與好友遊玩屋",
    "Dumbo the Flying Elephant": "小飛象旋轉世界",
    "Fairy Tale Forest": "童話藝坊",
    "Fantasy Gardens": "夢想花園",
    "Frozen Ever After - Presented by Blue Cross": "魔雪奇緣世界——雪嶺滑雪橇",
    "Frozen Ever After – Presented by Blue Cross": "魔雪奇緣世界——雪嶺滑雪橇",
    "Garden of Wonders": "迷離莊園——奇幻庭園",
    "Geyser Gulch": "灰熊山谷——噴泉山谷",
    "Hyperspace Mountain": "星戰極速穿梭",
    "Iron Man Experience - Presented by AIA": "鐵甲奇俠飛行之旅",
    "Iron Man Tech Showcase - Presented by Stark Industries": "鐵甲奇俠裝備展",
    "Jungle River Cruise": "森林河流之旅",
    "Karibuni Marketplace": "卡麗布妮市集",
    "Liki Tikis": "利奇提奇島",
    "Mad Hatter Tea Cups": "瘋帽子旋轉杯",
    "Main Street Vehicles": "小鎮大街古董車",
    "Main Street Corner Cafe Hosted by Coca-Cola®": "市鎮會堂茶座",
    "Meet CookieAnn at Duffy and Friends Play House": "CookieAnn 會面",
    "Meet Duffy at Duffy and Friends Play House": "Duffy 會面",
    "Meet Gelatoni at Duffy and Friends Play House": "Gelatoni 會面",
    "Meet LinaBell at Duffy and Friends Play House": "LinaBell 會面",
    "Meet ShellieMay at Duffy and Friends Play House": "ShellieMay 會面",
    "Meet StellaLou at Duffy and Friends Play House": "StellaLou 會面",
    "Meet ‘Olu Mel at Duffy and Friends Play House": "Olu Mel 會面",
    "Mickey's PhilharMagic": "米奇幻想曲",
    "Mystic Manor": "迷離莊園",
    "Mystic Point Freight Depot": "迷離莊園——倉庫",
    "Orbitron": "UFO 地帶",
    "Playhouse in the Woods": "魔雪奇緣世界——森林小天地",
    "Plaza Inn": "廣場飯店",
    "RC Racer": "反斗奇兵大本營——沖天遙控車",
    "Rafts to Tarzan's Treehouse": "泰山樹屋木筏",
    "River View Cafe": "河景餐廳",
    "Slinky Dog Spin": "玩具兵團跳降傘",
    "Tarzan's Treehouse": "泰山樹屋",
    "The Many Adventures of Winnie the Pooh": "小熊維尼歷險之旅",
    "The Royal Reception Hall": "皇室宴會廳",
    "Toy Soldier Parachute Drop": "玩具兵團跳降傘",
    "Wandering Oaken's Sliding Sleighs": "魔雪奇緣世界——雪嶺滑雪橇",
    "Wandering Oaken’s Sliding Sleighs": "魔雪奇緣世界——雪嶺滑雪橇",
    "Wild West Photo Fun": "西部拍照點",
}


def fetch():
    req = urllib.request.Request(API, headers={"User-Agent": "disneyland-we1co/1.0 (+https://we1co.me)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    data = fetch()
    atts = data.get("attractions", [])
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "parkName": "Hong Kong Disneyland",
        "attractions": [
            {
                "name": a["name"],
                "nameZh": ZH.get(a["name"], a["name"]),
                "waitTime": a.get("waitTime"),
                "status": a.get("status") or "Unknown",
                "active": bool(a.get("active")),
                "lat": (a.get("meta") or {}).get("latitude"),
                "lon": (a.get("meta") or {}).get("longitude"),
                "type": (a.get("meta") or {}).get("type", "ATTRACTION"),
            }
            for a in sorted(atts, key=lambda x: ZH.get(x["name"], x["name"]))
            if a.get("meta") and a["meta"].get("latitude")
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    rides = [a for a in out["attractions"] if a["type"] == "ATTRACTION"]
    print(f"OK: {len(out['attractions'])} points ({len(rides)} rides), updated={out['updated']}")


if __name__ == "__main__":
    main()