#!/usr/bin/env python3 -I
"""Cost units per day/week/step from ~/.claude/projects transcripts (last N days, default 30).
Units: input 1, output 5, cache read 0.1, cache write 1.25 (assumed ratios). Assistant messages deduplicated by id.
Run: python3 -I ~/.claude/usage-units.py [days]"""
import os, sys, json, glob, collections, zoneinfo
from datetime import datetime as dt, timedelta, timezone
TZ = zoneinfo.ZoneInfo("Europe/Madrid"); days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
now = dt.now(timezone.utc); cutoff = now - timedelta(days=days); msgs = {}
for f in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True):
    if dt.fromtimestamp(os.stat(f).st_mtime, timezone.utc) < cutoff: continue
    for line in open(f, "rb"):
        try: d = json.loads(line)
        except Exception: continue
        if d.get("type") != "assistant" or not d.get("timestamp"): continue
        m = d.get("message") or {}; u = m.get("usage"); mid = m.get("id")
        if not u or not mid: continue
        t = dt.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
        if t < cutoff: continue
        cr = u.get("cache_read_input_tokens", 0) or 0; cw = u.get("cache_creation_input_tokens", 0) or 0
        inp = u.get("input_tokens", 0) or 0; out = u.get("output_tokens", 0) or 0
        msgs[mid] = (t, m.get("model") or "", inp + cr + cw, inp + out * 5 + cr * 0.1 + cw * 1.25)
def week(t):
    d = (t.astimezone(TZ) - timedelta(hours=7)).date(); return d - timedelta(days=(d.weekday() - 5) % 7)
day = collections.defaultdict(lambda: [0, 0.0]); wk = collections.defaultdict(lambda: [0, 0.0, 0.0])
for t, model, ctx, cost in msgs.values():
    k = day[t.astimezone(TZ).date()]; k[0] += 1; k[1] += cost
    w = wk[week(t)]; w[0] += 1; w[1] += cost; w[2] += cost if "fable" not in model else 0
print("day         steps  Munits  units/step"); 
for d in sorted(day): print(f"{d}  {day[d][0]:5d}  {day[d][1]/1e6:6.1f}  {day[d][1]/day[d][0]/1e3:6.1f}k")
print("\nweek(Sat 07:00) steps  Munits  units/step  non-Fable Munits")
for w in sorted(wk): print(f"{w}      {wk[w][0]:5d}  {wk[w][1]/1e6:6.1f}  {wk[w][1]/wk[w][0]/1e3:6.1f}k  {wk[w][2]/1e6:6.1f}")
n = len(msgs); print(f"\n{days} days: {n} steps, {sum(v[3] for v in msgs.values())/1e6:.1f}M units, {sum(v[3] for v in msgs.values())/n/1e3:.1f}k units/step, steps with context >200k: {sum(1 for v in msgs.values() if v[2] > 200e3)/n*100:.0f}%")
