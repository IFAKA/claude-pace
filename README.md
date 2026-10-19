# claude-pace: make your Claude Code weekly limit last the whole week

**claude-pace** is a small, zero-dependency add-on for [Claude Code](https://code.claude.com) on Claude Max and Pro plans. It watches your weekly usage limit and stops you from burning it by Wednesday. It is automatic: install once, then forget it.

If you keep seeing *"You've hit your weekly limit"* or *"You've hit your Opus limit"* before the week resets, this is for you.

## What it does

| Part | How it helps |
|---|---|
| **Status line** | Shows context size, the 5-hour bar, the weekly bar and how far ahead of an even pace you are, for example `wk 40% (+10 vs pace, ahead)`. Also shows how much of the Fable weekly cap is gone. |
| **Fable guard** (`PreModelSwitch` hook) | Refuses `/model fable` while your week, or Fable's own cap, is ahead of pace. On pace, the switch goes through. |
| **Frugal mode** (`UserPromptSubmit` hook) | While ahead of pace, each prompt carries a short note asking Claude to avoid re-reading files, batch tool calls and skip subagents. On pace, nothing is injected, so capability is untouched. |
| **`usage-units.py`** | Read-only report of your own transcripts: cost units per step, per day and per week. Use it to prove the savings. |

No proxy, no token rewriting, no third-party packages. It only reads the rate limits Claude Code passes to the status line and your local `~/.claude/projects/**/*.jsonl` transcripts.

## Install, update, remove

Requires Python 3 and Claude Code 2.1.251 or later.

```bash
# install
git clone https://github.com/IFAKA/claude-pace ~/.claude/pace-src
python3 -I ~/.claude/pace-src/install.py

# update
git -C ~/.claude/pace-src pull && python3 -I ~/.claude/pace-src/install.py

# remove
python3 -I ~/.claude/pace-src/install.py --remove
```

The installer backs up `settings.json` to `settings.json.bak-<timestamp>`, merges only its own keys (`statusLine`, two hooks, `promptSuggestionEnabled: false`) and is safe to run twice. Start a new session afterwards and run `/hooks` to confirm.

## Calibrate once

The Fable cap defaults to $272 of list-price Fable use per week, fitted to one Max 5x account. Fit yours: use Fable a little, read the Fable percentage in `/usage`, then run:

```bash
python3 -I ~/.claude/pace/pace.py calibrate <that percentage>
```

Check the numbers any time with `python3 -I ~/.claude/pace/pace.py status`. Bypass it for one session with `CLAUDE_PACE_OFF=1`.

## Recommended Claude Code settings (the big savings)

The measured waste on one account was context size: 67% of usage came from steps above 200k tokens of context. Two official settings fix most of it:

```json
{
  "autoCompactWindow": 200000,
  "effortLevel": "medium"
}
```

On Opus 5.5 also set `modelSettings["claude-opus-5-5"].effortLevel` to `medium`, because the top-level `effortLevel` does not apply to that model. Then use `/clear` between unrelated tasks. claude-pace does not change these for you.

## How it decides

- **Even pace** is 100% of the week divided evenly. **Ahead** means more than 5 points above the elapsed share of the week.
- Weekly numbers come from the official `rate_limits` data in the status line, so they match `/usage`.
- Fable has no official bar in that data, so its spend is computed from your transcripts at list price and compared with its own cap.

## Limits and assumptions

- It cannot change your model or effort for you. It can refuse Fable and ask Claude to be frugal.
- The weekly limit is assumed to weigh tokens roughly by list price. On one account the all-models bar matched within 2 points.
- Proof it works on your account: units per step from `python3 -I ~/.claude/pace/usage-units.py 7` should fall, and the weekly bar should end under 100%. If not, open an issue with both numbers.

## FAQ

**Does it work on Pro?** The status line data and hooks work. Fable runs on usage credits there, so the Fable guard matters less.

**Will it slow Claude down?** Each hook runs in under a quarter of a second.

**Is it safe?** It is about 250 lines of plain Python you can read. It never sends data anywhere.

Keywords: Claude Code usage limit, weekly limit, Claude Max, Opus limit, Fable, token savings, prompt caching, auto-compact, status line, hooks.

MIT licensed.
