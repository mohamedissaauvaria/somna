"""Adds or removes Somna's entries in ~/.claude/settings.json. Idempotent, keeps everything else."""
import json
import os
import sys

MARK = "/bin/somna"


EVENTS = {"SessionStart": "session-start", "SubagentStart": "subagent-start"}


def is_ours(cmd):
    return MARK in cmd and ("hook session-start" in cmd or "hook subagent-start" in cmd)


def load(p):
    if os.path.exists(p) and os.path.getsize(p):
        with open(p) as fh:
            return json.load(fh)
    return {}


def ok(t):
    print("  \033[32mok\033[0m   " + t)


def deny_rules(home):
    """Read-only access: agents may not edit memory, only inbox and scratch."""
    mem = os.path.join(home, "memory")
    rules = []
    if os.path.isdir(mem):
        for name in sorted(os.listdir(mem)):
            if name in ("inbox", "scratch") or name.startswith("."):
                continue
            full = os.path.join(mem, name)
            pat = "/{}/**".format(full) if os.path.isdir(full) else "/{}".format(full)
            rules += ["Edit({})".format(pat), "Write({})".format(pat)]
    for d in ("engine", "bin", "ui"):
        rules += ["Edit(/{}/{}/**)".format(home, d), "Write(/{}/{}/**)".format(home, d)]
    return rules


def ours_deny(rule, home):
    return rule.startswith(("Edit(/{}/".format(home), "Write(/{}/".format(home)))


def install(p, home, py, access="read_only"):
    try:
        cfg = load(p)
    except ValueError:
        print("  \033[31m!!\033[0m   ~/.claude/settings.json is not valid JSON. Fix it, then re-run install.sh")
        sys.exit(1)
    if "cleanupPeriodDays" not in cfg:
        cfg["cleanupPeriodDays"] = 90
        ok("kept session transcripts for 90 days (cleanupPeriodDays)")
    else:
        ok("cleanupPeriodDays already set, left as is")
    hooks = cfg.setdefault("hooks", {})
    for event, arg in EVENTS.items():
        cmd = '"{}" "{}/bin/somna" hook {}'.format(py, home, arg)
        entries = [e for e in hooks.get(event, []) if not any(is_ours(h.get("command", "")) for h in e.get("hooks", []))]
        entries.append({"hooks": [{"type": "command", "command": cmd, "timeout": 15}]})
        hooks[event] = entries
    ok("SessionStart and SubagentStart hooks inject repo context in mapped repos")
    perms = cfg.setdefault("permissions", {})
    dirs = ["{}/memory/inbox".format(home), "{}/memory/scratch".format(home)]
    rules = []
    for d in dirs:
        # a leading // makes the path absolute in Claude Code permission rules
        rules += ["Read(/{}/**)".format(d), "Edit(/{}/**)".format(d), "Write(/{}/**)".format(d)]
    perms["allow"] = [r for r in perms.get("allow", []) if "/memory/inbox/" not in r and "/memory/scratch/" not in r] + rules
    perms["additionalDirectories"] = [x for x in perms.get("additionalDirectories", []) if x not in dirs] + dirs
    ok("agents may append to inbox and scratch notes without prompts")
    deny = [r for r in perms.get("deny", []) if not ours_deny(r, home)]
    if access == "read_write":
        ok("memory left writable for agents (--agents-can-edit-memory)")
    else:
        deny += deny_rules(home)
        ok("memory is read-only for agents, only inbox and scratch are writable")
    if deny:
        perms["deny"] = deny
    elif "deny" in perms:
        del perms["deny"]
    with open(p, "w") as fh:
        json.dump(cfg, fh, indent=2)


def uninstall(p, home=None):
    try:
        cfg = load(p)
    except ValueError:
        return
    h = cfg.get("hooks", {})
    for event in EVENTS:
        if event in h:
            h[event] = [e for e in h[event] if not any(is_ours(x.get("command", "")) for x in e.get("hooks", []))]
            if not h[event]:
                del h[event]
    if "hooks" in cfg and not cfg["hooks"]:
        del cfg["hooks"]
    pm = cfg.get("permissions", {})
    if "allow" in pm:
        pm["allow"] = [r for r in pm["allow"] if "/memory/inbox/" not in r and "/memory/scratch/" not in r]
    if home and "deny" in pm:
        pm["deny"] = [r for r in pm["deny"] if not ours_deny(r, home)]
        if not pm["deny"]:
            del pm["deny"]
    if "additionalDirectories" in pm:
        pm["additionalDirectories"] = [d for d in pm["additionalDirectories"] if not d.endswith(("/memory/inbox", "/memory/scratch"))]
    with open(p, "w") as fh:
        json.dump(cfg, fh, indent=2)
    print("removed the context hook and note permissions from ~/.claude/settings.json")


if __name__ == "__main__":
    if sys.argv[1] == "install":
        install(*sys.argv[2:6])
    else:
        uninstall(*sys.argv[2:4])
