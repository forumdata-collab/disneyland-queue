#!/usr/bin/env python3
"""HK Disneyland queue-trend analysis + best playing-sequence planner.

Reads data/history.json (date-keyed, day-tagged) + hk_holidays.json + hkdl.json,
builds per-ride wait curves by dayType (weekday/weekend/holiday) and time bucket,
then plans the optimal ride order for a given arrival time.

Usage:
  python3 analyze_hkdl.py                     # trend report + 10:30 plan (today's dayType)
  python3 analyze_hkdl.py --arrive 10:30 --type weekend --rides 10
  python3 analyze_hkdl.py --json              # machine-readable output

Outputs: stdout report; data/analysis.json when --json.
Confidence flags: LOW when a bucket has <3 samples — improves automatically as
history.json accumulates (target: 2+ weeks per dayType).
"""
import argparse, json, math, random, sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, date

BASE = Path(__file__).parent
DATA = BASE / "data"

# ── ride duration estimates (min) — API has no duration field; approx, editable ──
DURATIONS = {
    "Hyperspace Mountain": 3, "Big Grizzly Mountain Runaway Mine Cars": 4,
    "Mystic Manor": 5, "Iron Man Experience": 5, "Ant-Man and The Wasp: Nano Battle!": 5,
    "Toy Soldier Parachute Drop": 3, "RC Racer": 2, "Slinky Dog Spin": 2,
    "Buzz Lightyear Astro Blasters": 4, "It's a Small World": 9,
    "Winnie the Pooh": 4, "Frozen Ever After": 6, "Wandering Oaken's Sliding Sleighs": 3,
    "Jungle River Cruise": 8, "Mickey's PhilharMagic": 12, "Orbitron": 2,
    "Mad Hatter Tea Cups": 2, "Cinderella Carousel": 2, "Dumbo the Flying Elephant": 2,
    "Fairy Tale Forest": 5, "The Many Adventures of Winnie the Pooh": 4,
    "Hong Kong Disneyland Railroad": 20, "Tarzan's Treehouse": 6,
    "Fantasy Gardens": 5, "Dapper Dans": 5, "Main Street Vehicles": 8,
}
DUR_DEFAULT = 5  # fallback for unknown rides

WALK_MPS = 1.2          # park walking pace incl. crowds (m/s)
MAX_RIDES_DEFAULT = 8
HIST_MIN_BUCKET = 3     # min samples per bucket for confidence
BUCKET_MIN = 30         # bucket size in minutes

def load():
    hist = json.loads((DATA / "history.json").read_text(encoding="utf-8"))
    try: holidays = set(json.loads((DATA / "hk_holidays.json").read_text(encoding="utf-8")))
    except Exception: holidays = set()
    out = json.loads((DATA / "hkdl.json").read_text(encoding="utf-8"))
    rides = {a["id"]: a for a in out["attractions"] if a.get("type") == "ATTRACTION"}
    return hist, holidays, out, rides

def day_type_of(ts, holidays):
    d, _ = ts.split()
    if d in holidays: return "holiday"
    wd = date.fromisoformat(d).weekday()
    return "weekend" if wd >= 5 else "weekday"

def haversine_m(a, b):
    import math
    R = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"]); dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def walk_min(a, b):
    if not a or not b: return 2.0
    return max(1.5, haversine_m(a, b) / (WALK_MPS * 60))

def bucket_of(hhmm):
    h, m = map(int, hhmm.split(":"))
    return f"{h:02d}:{(m // BUCKET_MIN) * BUCKET_MIN:02d}"

def buckets_between(start, end):
    """list of bucket labels from start (HH:MM) to end, step BUCKET_MIN."""
    s = datetime.strptime(start, "%H:%M"); e = datetime.strptime(end, "%H:%M")
    out, cur = [], s
    while cur <= e:
        out.append(cur.strftime("%H:%M")); cur = cur.replace(minute=cur.minute + BUCKET_MIN)
    return out

def build_curves(hist, holidays):
    """curves[dayType][rideId][bucket] = median wait; counts[dayType][rideId][bucket] = n."""
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for ts, snap in hist.items():
        dt = day_type_of(ts, holidays)
        b = bucket_of(ts.split()[1])
        for rid, w in snap.items():
            if w is not None:
                agg[dt][rid][b].append(w)
    curves = defaultdict(lambda: defaultdict(dict))
    counts = defaultdict(lambda: defaultdict(dict))
    for dt in agg:
        for rid in agg[dt]:
            for b, ws in agg[dt][rid].items():
                ws.sort()
                curves[dt][rid][b] = ws[len(ws)//2]
                counts[dt][rid][b] = len(ws)
    return curves, counts

def park_avg_curve(curves, counts, dt, rides):
    """avg wait across rides per bucket — the 'busy curve' of the park."""
    avg = {}
    for rid in curves[dt]:
        for b, w in curves[dt][rid].items():
            if w is None: continue
            avg.setdefault(b, []).append(w)
    return {b: round(sum(ws)/len(ws)) for b, ws in avg.items()}

def expected_wait(curves, counts, park_avg, dt, rid, b):
    """bucket median → park avg → global ride median → 35 fallback."""
    v = curves[dt].get(rid, {}).get(b)
    if v is not None: return v, counts[dt][rid][b]
    if b in park_avg: return park_avg[b], 0
    g = [w for ws in curves[dt].get(rid, {}).values() for w in ([ws] if isinstance(ws, (int,float)) else [ws])]
    flat = [w for w in [curves[dt][rid][bb] for bb in curves[dt][rid]] if w is not None]
    if flat: return round(sum(flat)/len(flat)), 0
    return 35, 0

def simulate_order(order, rides, curves, counts, park_avg, dt, arrive, closing):
    """walk the plan: returns list of (ride, arrive_time, wait, done_time) or None if busts closing."""
    import datetime as _dt
    t = _dt.datetime.strptime(arrive, "%H:%M")
    close = _dt.datetime.strptime(closing, "%H:%M")
    plan, prev = [], None
    for rid in order:
        b = bucket_of(t.strftime("%H:%M"))
        w, n = expected_wait(curves, counts, park_avg, dt, rid, b)
        dur = DURATIONS.get(rides[rid]["name"], DUR_DEFAULT)
        walk = walk_min(rides.get(prev, {}), rides.get(rid, {})) if prev else 1.0
        t = t + _dt.timedelta(minutes=round(walk))
        arrive_t = t.strftime("%H:%M")
        t = t + _dt.timedelta(minutes=int(w + dur))
        if t > close: return None
        plan.append({"ride": rid, "name": rides[rid]["name"], "land": rides[rid]["land"],
                     "arrive": arrive_t, "wait": w, "dur": dur, "walk": round(walk,1),
                     "finish": t.strftime("%H:%M"), "samples": n})
        prev = rid
    return plan

def plan_sequence(rides, curves, counts, park_avg, dt, arrive, closing, n_rides, rng):
    """greedy popular-first + 2-opt-ish local improvement; returns best plan."""
    # candidate pool: rides with any curve data, ranked by typical peak wait
    pool = []
    for rid in rides:
        prof = curves[dt].get(rid, {})
        if not prof: continue
        ws = [w for w in prof.values() if w is not None]
        if not ws: continue
        pool.append((rid, max(ws)))
    pool.sort(key=lambda x: -x[1])
    pool = [r for r, _ in pool[:max(n_rides * 3, 12)]]
    if len(pool) < n_rides: n_rides = len(pool)
    best_plan, best_order = None, None
    # random restarts: greedy by (urgency = typical wait − current wait) + order swap hill-climb
    for _ in range(40):
        order = list(pool)
        rng.shuffle(order)
        order = order[:n_rides]
        # hill-climb: swap adjacent pairs, keep if better (min total finish)
        improved = True
        while improved:
            improved = False
            for i in range(len(order) - 1):
                cand = order[:i] + [order[i+1], order[i]] + order[i+2:]
                p = simulate_order(cand, rides, curves, counts, park_avg, dt, arrive, closing)
                if not p: continue
                pb = simulate_order(order, rides, curves, counts, park_avg, dt, arrive, closing)
                if pb and p[-1]["finish"] < pb[-1]["finish"]:
                    order, improved = cand, True
                    break
        plan = simulate_order(order, rides, curves, counts, park_avg, dt, arrive, closing)
        if plan and (best_plan is None or plan[-1]["finish"] < best_plan[-1]["finish"]):
            best_plan, best_order = plan, order
    return best_plan, best_order

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arrive", default="10:30", help="arrival time HH:MM (default 10:30)")
    ap.add_argument("--type", choices=["weekday","weekend","holiday"], default=None)
    ap.add_argument("--rides", type=int, default=MAX_RIDES_DEFAULT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    hist, holidays, out, rides = load()
    curves, counts = build_curves(hist, holidays)

    # dayType: requested or today's
    today_ts = out.get("date") + " 12:00"
    dt = args.type or day_type_of(today_ts, holidays)
    closing = (out.get("closingTime") or "").split("T")[-1][:5] or "20:30"

    # ── trend report ──
    park_avg = park_avg_curve(curves, counts, dt, rides)
    per_type = defaultdict(set)
    for ts in hist: per_type[day_type_of(ts, holidays)].add(ts.split()[0])
    total_days = len({ts.split()[0] for ts in hist})

    lines = []
    lines.append(f"HK Disneyland queue analysis — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Data: {total_days} day(s) | {len(hist)} samples | by type: "
                 + ", ".join(f"{k}={len(v)}d" for k, v in sorted(per_type.items())))
    lines.append(f"Scenario: arrive {args.arrive}, dayType={dt}, park closes {closing}")
    if len(per_type.get(dt, set())) < 3:
        lines.append(f"⚠️ LOW CONFIDENCE: only {len(per_type.get(dt, set()))} day(s) of {dt} data — "
                     f"curves are provisional; re-run as history grows (target 2+ wks).")
    lines.append("")

    if park_avg:
        peak = max(park_avg, key=park_avg.get)
        lines.append(f"Park busy curve ({dt}): quietest ~{min(park_avg, key=park_avg.get)}, "
                     f"peak ~{peak} ({park_avg[peak]}′ avg). "
                     f"Best rope-drop: do the top rides before ~{peak}.")
        lines.append("")

    # ride profiles sorted by typical peak wait
    prof_rows = []
    for rid, a in rides.items():
        prof = curves[dt].get(rid, {})
        if not prof: continue
        ws = {b: w for b, w in prof.items() if w is not None}
        if not ws: continue
        peak_b, peak_w = max(ws.items(), key=lambda kv: kv[1])
        quiet_b, quiet_w = min(ws.items(), key=lambda kv: kv[1])
        prof_rows.append((a["name"], a["land"], peak_w, peak_b, quiet_w, quiet_b, len(ws)))
    prof_rows.sort(key=lambda r: -r[2])
    if prof_rows:
        lines.append("Ride wait profiles (sorted by peak wait):")
        for name, land, pw, pb, qw, qb, nb in prof_rows:
            flag = " ⚠️low-n" if nb < 3 else ""
            lines.append(f"  {name:<45} peak {pw:>3}′@{pb}  quiet {qw:>3}′@{qb}{flag}")
        lines.append("")

    # ── sequence plan ──
    rng = random.Random(args.seed)
    plan, _ = plan_sequence(rides, curves, counts, park_avg, dt, args.arrive, closing,
                            args.rides, rng)
    if plan:
        lines.append(f"Recommended playing sequence ({len(plan)} rides, arrive {args.arrive}):")
        for p in plan:
            src = "data" if p["samples"] >= HIST_MIN_BUCKET else "est."
            lines.append(f"  {p['arrive']}  {p['name']:<42} wait {p['wait']:>3}′ + ride {p['dur']}′ "
                         f"(walk {p['walk']}′) → {p['finish']}  [{src}]")
        lines.append(f"  Done by {plan[-1]['finish']} — {len(plan)} rides before close.")
        lines.append("  Tip: queue dips during parade/fireworks — schedule long-wait rides then.")
    else:
        lines.append("No feasible plan within closing time — try fewer rides or earlier arrival.")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    if args.json:
        payload = {
            "generated": datetime.now().isoformat(),
            "dayType": dt, "arrive": args.arrive, "closing": closing,
            "daysByType": {k: len(v) for k, v in per_type.items()},
            "parkAvg": park_avg, "plan": plan,
            "profiles": [{"name": n, "land": l, "peakWait": pw, "peakBucket": pb,
                          "quietWait": qw, "quietBucket": qb} for n, l, pw, pb, qw, qb, _ in prof_rows],
        }
        (DATA / "analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()