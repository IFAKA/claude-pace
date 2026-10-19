#!/usr/bin/env python3
"""Install, update or remove claude-pace.

  python3 -I install.py            install or update (idempotent)
  python3 -I install.py --remove   remove everything this installer added

Copies pace.py and usage-units.py to ~/.claude/pace/, then merges only its own
keys into ~/.claude/settings.json: statusLine, a PreModelSwitch hook, a
UserPromptSubmit hook, promptSuggestionEnabled=false. Backs the file up first.
Set CLAUDE_HOME to use another config folder (used by the tests).
"""
import collections, json, os, shutil, sys, time

HOME = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~/.claude")
SRC = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HOME, "pace")
SETTINGS = os.path.join(HOME, "settings.json")
CMD = f"python3 -I {DEST}/pace.py "
CMD = CMD.replace(os.path.expanduser("~"), "~") if not os.environ.get("CLAUDE_HOME") else CMD
MARK = "/pace/pace.py "


def mine(entry):
    return any(MARK in h.get("command", "") for h in entry.get("hooks", []))


def main():
    remove = "--remove" in sys.argv
    d = collections.OrderedDict()
    if os.path.exists(SETTINGS):
        with open(SETTINGS) as f:
            d = json.load(f, object_pairs_hook=collections.OrderedDict)
        bak = SETTINGS + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(SETTINGS, bak)
        print("backup:", bak)
    hooks = d.get("hooks") or collections.OrderedDict()
    if remove:
        if MARK in d.get("statusLine", {}).get("command", ""):
            d.pop("statusLine")
        for ev in ("PreModelSwitch", "UserPromptSubmit"):
            if ev in hooks:
                hooks[ev] = [h for h in hooks[ev] if not mine(h)]
                if not hooks[ev]:
                    hooks.pop(ev)
        if hooks:
            d["hooks"] = hooks
        else:
            d.pop("hooks", None)
        d.pop("promptSuggestionEnabled", None)
        what = "removed (scripts left in " + DEST + "; delete that folder to finish)"
    else:
        os.makedirs(DEST, exist_ok=True)
        for name in ("pace.py", "usage-units.py"):
            shutil.copy2(os.path.join(SRC, name), os.path.join(DEST, name))
        old = d.get("statusLine")
        if old and MARK not in old.get("command", ""):
            print("note: replacing your existing statusLine; --remove will not restore it (see backup)")
        d["statusLine"] = collections.OrderedDict([("type", "command"), ("command", CMD + "statusline")])
        for ev, entry in (
            ("PreModelSwitch", {"matcher": ".*fable.*", "hooks": [{"type": "command", "command": CMD + "guard-model"}]}),
            ("UserPromptSubmit", {"hooks": [{"type": "command", "command": CMD + "prompt", "timeout": 20}]}),
        ):
            hooks[ev] = [h for h in hooks.get(ev, []) if not mine(h)] + [entry]
        d["hooks"] = hooks
        d["promptSuggestionEnabled"] = False
        what = "installed. Start a new Claude Code session, then run /hooks to see them."
    os.makedirs(HOME, exist_ok=True)
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    json.load(open(tmp))
    os.replace(tmp, SETTINGS)
    print(what)


main()
