#!/usr/bin/env python3
"""HK Disneyland wait times + history + land stats + calendar → data/hkdl.json

Source: api.themeparks.wiki (free, no key). history.json maintained across runs.
Output: {updated, parkName, openingTime, closingTime, attractions: [...], lands: [...]}
"""
import json, os, time, urllib.request, datetime
from pathlib import Path
from collections import defaultdict
import math
import sys

BASE = Path(__file__).parent
API_WAITTIME = "https://api.themeparks.wiki/preview/parks/HongKongDisneylandPark/waittime"
API_CALENDAR = "https://api.themeparks.wiki/preview/parks/HongKongDisneylandPark/calendar"
ENTERTAINMENT_URL = "https://www.hongkongdisneyland.com/finder/api/v1/explorer-service/list-ancestor-entities/hkdl/hkdl;entityType=destination/{date}/entertainment"
ENT_CACHE = BASE / "data" / "entertainment_cache.json"  # daily: refetch once per day (09:00 first run)
OUT = BASE / "data" / "hkdl.json"
HIST = BASE / "data" / "history.json"  # rolling: last ~5 weeks, 5-min samples, keyed "YYYY-MM-DD HH:MM"
MAX_HISTORY = 6000  # ≈ 38 park-days (13h/day × 12/h) — enough for weekday/weekend/holiday contrast
HOLIDAYS = BASE / "data" / "hk_holidays.json"  # HK statutory holidays (1823.gov.hk), cached per year
HOLIDAY_URL = "https://www.1823.gov.hk/common/ical/en.json"

# ── Land mapping by coordinate clustering (adjacent areas) ──
LANDS = [
    {"name": "Main Street, U.S.A.",    "nameZh": "美國小鎮大街",   "lat": 22.31315, "lon": 114.04415},
    {"name": "Adventureland",          "nameZh": "探險世界",       "lat": 22.31068, "lon": 114.04005},
    {"name": "Fantasyland",            "nameZh": "幻想世界",       "lat": 22.31235, "lon": 114.04000},
    {"name": "Toy Story Land",         "nameZh": "反斗奇兵大本營",  "lat": 22.31425, "lon": 114.04055},
    {"name": "Tomorrowland",           "nameZh": "明日世界",       "lat": 22.31455, "lon": 114.04300},
    {"name": "Grizzly Gulch",          "nameZh": "灰熊山谷",       "lat": 22.30985, "lon": 114.04185},
    {"name": "World of Frozen",        "nameZh": "魔雪奇緣世界",    "lat": 22.31260, "lon": 114.03900},
    {"name": "Mystic Point",           "nameZh": "迷離莊園",       "lat": 22.31020, "lon": 114.04230},
]
# Coords close to park (within ~800m)
PARK_LAT, PARK_LON = 22.3125, 114.0415
def haversine(lat1,lon1,lat2,lon2):
    R=6371e3
    dlat=math.radians(lat2-lat1);dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(a))
def land_for(lat,lon):
    if not lat or not lon: return "Other"
    best,best_d=None,1e9
    for L in LANDS:
        d=haversine(lat,lon,L['lat'],L['lon'])
        if d<best_d: best,best_d=L,d
    return best['nameZh'] if best and best_d<800 else "Other"

ZH = {
    "it's a small world": "小小世界",
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
    "Iron Man Experience - Presented by AIA Experience": "鐵甲奇俠飛行之旅",
    "Iron Man Tech Showcase - Presented by Stark Industries": "鐵甲奇俠裝備展",
    "Jungle River Cruise": "森林河流之旅",
    "Karibuni Marketplace": "卡麗布妮市集",
    "Liki Tikis": "利奇提奇島",
    "Mad Hatter Tea Cups": "瘋帽子旋轉杯",
    "Main Street Corner Cafe Hosted by Coca-Cola®": "市鎮會堂茶座",
    "Main Street Vehicles": "小鎮大街古董車",
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
    "Wandering Oaken's Sliding Sleighs": "魔雪奇緣世界——雪嶺滑雪橇",
    "Wild West Photo Fun": "西部拍照點",
}

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "disneyland-we1co/1.0 (+https://we1co.me)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig"))

def load_history():
    try: return json.loads(HIST.read_text(encoding='utf-8'))
    except: return {}

def save_history(hist):
    HIST.parent.mkdir(exist_ok=True)
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding='utf-8')

def load_holidays():
    """HK statutory holidays as set of 'YYYY-MM-DD'. Refetch from 1823.gov.hk when cache lacks current year."""
    today = datetime.date.today()
    need_fetch = True
    if HOLIDAYS.exists():
        try:
            data = json.loads(HOLIDAYS.read_text(encoding='utf-8'))
            if isinstance(data, list) and any(str(today.year) in d for d in data):
                return set(data)
        except Exception:
            pass
    try:
        raw = fetch(HOLIDAY_URL)
        dates = []
        for ev in (raw.get('vcalendar') or [{}])[0].get('vevent', []):
            d = (ev.get('dtstart') or [''])[0]
            if len(d) == 8 and d.isdigit():
                dates.append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
        if dates:
            HOLIDAYS.parent.mkdir(exist_ok=True)
            HOLIDAYS.write_text(json.dumps(sorted(dates), ensure_ascii=False), encoding='utf-8')
            return set(dates)
    except Exception as e:
        sys.stderr.write(f'Holiday fetch error: {e}\n')
    return set()

def day_type(holidays):
    """'weekday' | 'weekend' | 'holiday' for today."""
    today = time.strftime('%Y-%m-%d')
    if today in holidays:
        return 'holiday'
    wd = datetime.date.today().weekday()
    return 'weekend' if wd >= 5 else 'weekday'

def main():
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    wait_data = fetch(API_WAITTIME)
    cal_data = fetch(API_CALENDAR)
    
    today_str = time.strftime("%Y-%m-%d")
    cal_today = next((c for c in cal_data.get('calendar',[]) if c['date']==today_str), None)
    opening = cal_today['openingTime'] if cal_today else None
    closing = cal_today['closingTime'] if cal_today else None
    special = cal_today.get('special',[]) if cal_today else []

    atts = wait_data.get('attractions', [])
    attractions = []
    for a in atts:
        lat = (a.get('meta') or {}).get('latitude')
        lon = (a.get('meta') or {}).get('longitude')
        rid = a['id']
        name = a['name']
        if not lat: continue
        land = land_for(lat, lon)
        attractions.append({
            "id": rid,
            "name": name,
            "nameZh": ZH.get(name, name),
            "waitTime": a.get("waitTime"),
            "status": a.get("status") or "Unknown",
            "active": bool(a.get("active")),
            "lat": lat, "lon": lon,
            "type": (a.get("meta") or {}).get("type", "ATTRACTION"),
            "land": land,
        })
    
    # Land stats
    land_data = defaultdict(lambda: {"rides": 0, "waitSum": 0, "waitCount": 0})
    for a in attractions:
        if a['type'] != 'ATTRACTION': continue
        ld = land_data[a['land']]
        ld['rides'] += 1
        if a['waitTime'] is not None:
            ld['waitSum'] += a['waitTime']
            ld['waitCount'] += 1
    lands_out = []
    for L in LANDS:
        d = land_data.get(L['nameZh'], {})
        avg_wait = round(d.get('waitSum',0) / d['waitCount']) if d.get('waitCount') else 0
        lands_out.append({"nameZh": L['nameZh'], "name": L['name'], "rides": d.get('rides',0), "avgWait": avg_wait})
    lands_out.sort(key=lambda x: -x['avgWait'])

    # Daily entertainment schedule: refetch only when cache is stale (today not yet fetched)
    entertainment = []
    today = time.strftime('%Y-%m-%d')
    cache_hit = False
    if ENT_CACHE.exists():
        try:
            cache_raw = json.loads(ENT_CACHE.read_text(encoding='utf-8'))
            if cache_raw.get('date') == today and isinstance(cache_raw.get('list'), list):
                entertainment = cache_raw['list']
                cache_hit = True
        except Exception:
            pass
    if not cache_hit:
        try:
            ent_data = None
            for attempt in range(2):
                try:
                    ent_data = fetch(ENTERTAINMENT_URL.format(date=today))
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 502 or attempt == 1:
                        raise
                    time.sleep(3)
            if ent_data:
                for ent in ent_data.get('results', []):
                    name = ent.get('name', '')
                    schedules = (ent.get('schedule') or {}).get('schedules', [])
                    if not schedules:
                        continue
                    lower_name = name.lower()
                    etype = 'show'
                    if 'parade' in lower_name or '巡遊' in name:
                        etype = 'parade'
                    elif 'momentous' in lower_name or 'nighttime' in lower_name or 'spectacular' in lower_name:
                        etype = 'fireworks'
                    for sch in schedules:
                        if sch.get('isClosed'):
                            continue
                        entertainment.append({
                            'name': name,
                            'time': sch.get('startTime', ''),
                            'type': etype,
                        })
                ENT_CACHE.parent.mkdir(exist_ok=True)
                ENT_CACHE.write_text(json.dumps({'date': today, 'list': entertainment}, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            sys.stderr.write(f'Entertainment API error: {e}\n')

    # History accumulation — keyed by "YYYY-MM-DD HH:MM" so weekday/weekend/holiday
    # samples accumulate instead of overwriting each other
    hist = load_history()
    snapshot = {a['id']: a['waitTime'] for a in attractions if a['type']=='ATTRACTION'}
    h_key = time.strftime("%Y-%m-%d %H:%M")
    hist[h_key] = snapshot
    keys = sorted(hist.keys())
    if len(keys) > MAX_HISTORY: hist = {k: hist[k] for k in keys[-MAX_HISTORY:]}
    save_history(hist)
    # history snapshots as list (for frontend charting: last 12 samples)
    hist_list = []
    for h_key in keys[-12:]:
        hist_list.append({"t": h_key, "data": hist[h_key]})

    # Day-type tagging (weekday / weekend / holiday) — for trend analysis later
    holidays = load_holidays()
    d_type = day_type(holidays)

    out = {
        "updated": now_iso,
        "parkName": "Hong Kong Disneyland",
        "openingTime": opening,
        "closingTime": closing,
        "specialEvents": special,
        "dayType": d_type,
        "date": time.strftime("%Y-%m-%d"),
        "attractions": attractions,
        "lands": lands_out,
        "history": hist_list,
        "entertainment": entertainment,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    rides = [a for a in attractions if a["type"] == "ATTRACTION"]
    print(f"OK: {len(attractions)} points ({len(rides)} rides), {len(lands_out)} lands, {len(hist_list)} history samples, updated={now_iso}")

if __name__ == "__main__":
    main()