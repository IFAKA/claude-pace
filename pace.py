#!/usr/bin/env python3
"""Pace guard for the Claude Max weekly limit.

Modes (read JSON on stdin from Claude Code):
  statusline   save the official rate limits, print a one-line status
  guard-model  PreModelSwitch hook: deny a switch to Fable when ahead of pace
  prompt       UserPromptSubmit hook: tell Claude to work frugally when ahead of pace
  status       print the current pace numbers (for a terminal)

Budget rule: the week is spent evenly, 14.3 points a day. "Ahead" means the
used percentage is more than SLACK points above the elapsed share of the week.
Fable has no official bar in the status line data, so its spend is computed
from the local transcripts at list price and compared with its own half-week
cap, calibrated on 2026-10-19 (/usage showed 21% for $58.7 of list-price use).
"""
import datetime, glob, json, os, sys, time

HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, ".claude", "pace")
LIMITS = os.path.join(DIR, "limits.json")
FABLE_CACHE = os.path.join(DIR, "fable-week.json")
PROJECTS = os.path.join(HOME, ".claude", "projects")
WEEK = 7 * 86400
SLACK = 5.0                      # points over pace before the guard acts
STALE = 6 * 3600                 # ignore rate-limit data older than this
CONFIG = os.path.join(DIR, "config.json")
DEFAULT_FABLE_CAP = 272.0        # list-price $ of Fable per week; run `pace.py calibrate PCT` to fit your plan
FABLE_PRICE = (10, 20, 12.5, 0.25, 50)   # $/MTok: input, 1h write, 5m write, read, output
FABLE_RECOMPUTE = 600            # seconds between transcript scans


def cfg(key, default):
    try:
        with open(CONFIG) as f:
            return float(json.load(f).get(key, default))
    except Exception:
        return default


def read_stdin():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def load_limits():
    try:
        with open(LIMITS) as f:
            d = json.load(f)
        if time.time() - d.get("saved_at", 0) > STALE:
            return None
        return d
    except Exception:
        return None


def week_numbers(lim):
    """Return (used_pct, elapsed_pct, ahead_points, week_start) or None."""
    seven = (lim or {}).get("rate_limits", {}).get("seven_day") or {}
    if "used_percentage" not in seven or "resets_at" not in seven:
        return None
    resets = float(seven["resets_at"])
    start = resets - WEEK
    elapsed = max(0.0, min(1.0, (time.time() - start) / WEEK)) * 100
    used = float(seven["used_percentage"])
    return used, elapsed, used - elapsed, start


def fable_week_usd(week_start):
    """List-price dollars spent on Fable this week, from local transcripts (cached)."""
    try:
        with open(FABLE_CACHE) as f:
            c = json.load(f)
        if c.get("week_start") == week_start and time.time() - c.get("at", 0) < FABLE_RECOMPUTE:
            return c["usd"]
    except Exception:
        pass
    seen, usd = set(), 0.0
    for path in glob.glob(os.path.join(PROJECTS, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(path) < week_start:
                continue
            with open(path, errors="ignore") as f:
                for line in f:
                    if "claude-fable" not in line or '"assistant"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get("type") != "assistant":
                        continue
                    m = r.get("message", {})
                    u, mid = m.get("usage"), m.get("id")
                    if not u or not mid or mid in seen:
                        continue
                    if not str(m.get("model", "")).startswith("claude-fable"):
                        continue
                    ts = r.get("timestamp")
                    if ts:
                        t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        if t < week_start:
                            continue
                    seen.add(mid)
                    cc = u.get("cache_creation") or {}
                    cw1 = cc.get("ephemeral_1h_input_tokens", u.get("cache_creation_input_tokens", 0))
                    cw5 = cc.get("ephemeral_5m_input_tokens", 0)
                    p = FABLE_PRICE
                    usd += (u.get("input_tokens", 0) * p[0] + cw1 * p[1] + cw5 * p[2]
                            + u.get("cache_read_input_tokens", 0) * p[3]
                            + u.get("output_tokens", 0) * p[4]) / 1e6
        except Exception:
            continue
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(FABLE_CACHE, "w") as f:
            json.dump({"week_start": week_start, "at": time.time(), "usd": usd}, f)
    except Exception:
        pass
    return usd


def fable_pct(week_start):
    return 100.0 * fable_week_usd(week_start) / cfg("fable_week_list_usd", DEFAULT_FABLE_CAP)


def mode_statusline(d):
    os.makedirs(DIR, exist_ok=True)
    rl = d.get("rate_limits") or {}
    if rl:
        tmp = LIMITS + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"saved_at": time.time(), "rate_limits": rl}, f)
        os.replace(tmp, LIMITS)
    model = (d.get("model") or {}).get("display_name", "?")
    ctx = (d.get("context_window") or {}).get("used_percentage")
    parts = [f"[{model}]"]
    if ctx is not None:
        parts.append(f"ctx {ctx:.0f}%")
    fh = (rl.get("five_hour") or {}).get("used_percentage")
    if fh is not None:
        parts.append(f"5h {fh:.0f}%")
    wn = week_numbers({"rate_limits": rl})
    if wn:
        used, elapsed, ahead, start = wn
        flag = "ahead" if ahead > SLACK else "ok"
        parts.append(f"wk {used:.0f}% ({ahead:+.0f} vs pace, {flag})")
        try:
            parts.append(f"fable {fable_pct(start):.0f}% of its cap")
        except Exception:
            pass
    print(" · ".join(parts))


def mode_guard_model(d):
    to = str(d.get("to_model") or d.get("requested_model") or "").lower()
    if "fable" not in to:
        return
    lim = load_limits()
    wn = week_numbers(lim)
    if not wn:
        return  # no fresh data: let Claude Code's own confirmation handle it
    used, elapsed, ahead, start = wn
    reasons = []
    if ahead > SLACK:
        reasons.append(f"the week is {ahead:.0f} points ahead of pace ({used:.0f}% used, {elapsed:.0f}% of the week gone)")
    fp = fable_pct(start)
    if fp > elapsed + SLACK:
        reasons.append(f"Fable has used {fp:.0f}% of its half-week cap with {elapsed:.0f}% of the week gone")
    if reasons:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreModelSwitch",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Pace guard: " + "; ".join(reasons) + ". Stay on Opus 5.5 until the pace recovers, or run with CLAUDE_PACE_OFF=1 to bypass."}}))


def mode_prompt(d):
    lim = load_limits()
    wn = week_numbers(lim)
    if not wn:
        return
    used, elapsed, ahead, start = wn
    if ahead <= SLACK:
        return
    left_days = max(0.1, (start + WEEK - time.time()) / 86400)
    per_day = (100 - used) / left_days
    text = (f"Pace guard: the weekly usage limit is {ahead:.0f} points ahead of pace "
            f"({used:.0f}% used, {elapsed:.0f}% of the week elapsed, {per_day:.0f} points a day left for {left_days:.1f} days). "
            "Work frugally for this prompt: do not re-read files already in context; batch independent tool calls in one turn; "
            "read only the lines you need (grep, head, sed -n) instead of whole files; no subagents unless the task cannot be done without them; "
            "no exploratory browsing; keep replies short; do not switch models. Capability for the actual task is not to be cut.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))


def mode_calibrate(pct):
    lim = load_limits()
    wn = week_numbers(lim)
    if not wn:
        print("no fresh rate-limit data yet; open a session first")
        return
    usd = fable_week_usd(wn[3])
    if pct <= 0 or usd <= 0:
        print("need a Fable percentage above 0 and some Fable use this week")
        return
    cap = usd / (pct / 100.0)
    os.makedirs(DIR, exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump({"fable_week_list_usd": round(cap, 1)}, f)
    print(f"saved: Fable week cap = ${cap:.0f} list-price (from ${usd:.0f} = {pct:.0f}% in /usage)")


def mode_status():
    lim = load_limits()
    wn = week_numbers(lim)
    if not wn:
        print("no fresh rate-limit data yet (start a session so the status line records it)")
        return
    used, elapsed, ahead, start = wn
    fh = (lim.get("rate_limits", {}).get("five_hour") or {}).get("used_percentage")
    print(f"week: {used:.0f}% used, {elapsed:.0f}% elapsed, {ahead:+.0f} vs pace ({'ahead' if ahead > SLACK else 'ok'})")
    print(f"fable: {fable_pct(start):.0f}% of its half-week cap (list ${fable_week_usd(start):.0f} of ${cfg("fable_week_list_usd", DEFAULT_FABLE_CAP):.0f})")
    if fh is not None:
        print(f"5h window: {fh:.0f}% used")


if __name__ == "__main__":
    if os.environ.get("CLAUDE_PACE_OFF"):
        sys.exit(0)
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        if mode == "statusline":
            mode_statusline(read_stdin())
        elif mode == "guard-model":
            mode_guard_model(read_stdin())
        elif mode == "prompt":
            mode_prompt(read_stdin())
        elif mode == "calibrate":
            mode_calibrate(float(sys.argv[2]))
        else:
            mode_status()
    except Exception as e:  # never stall or block the session on a bug
        if mode == "status":
            print("error:", e)
        sys.exit(0)
