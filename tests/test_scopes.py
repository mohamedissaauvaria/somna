import json, os, re, subprocess, sys, time, urllib.request, urllib.error

PY, PORT = sys.argv[1], sys.argv[2]
H = os.environ["HOME"]
M = H + "/somna"
BASE = "http://127.0.0.1:" + PORT
FAILS = []


def check(name, cond, extra=None):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or extra is None else "   -> " + str(extra)[:300]))
    if not cond:
        FAILS.append(name)


def req(path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method="POST" if data is not None else "GET")
    if token:
        r.add_header("X-Somna-Token", token)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read() or b"{}") if path != "/" else resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


TOKEN = re.search(r'const TOKEN = "([^"]+)"', req("/")[1]).group(1)
J = lambda path, body=None: req(path, body, TOKEN)


def cycle(*a, env=None, stdin=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([PY, M + "/bin/somna", *a], capture_output=True, text=True, env=e, input=stdin)


def wait_idle():
    for _ in range(120):
        if not J("/api/state")[1]["health"]["running_pid"]:
            return
        time.sleep(0.5)


def add_session(repo, sid, text):
    d = H + "/.claude/projects/" + re.sub(r"[^a-zA-Z0-9]", "-", repo)
    os.makedirs(d, exist_ok=True)
    with open(d + "/" + sid + ".jsonl", "w") as f:
        f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": repo, "message": {"role": "user", "content": text}}) + "\n")


def mem(p):
    return open(M + "/" + p).read() if os.path.exists(M + "/" + p) else None


Acme, GLOBEX, LEG = H + "/code/acme-shop", H + "/code/globex-infra", H + "/code/acme-legacy"

# ---- install effects
st = json.load(open(H + "/.claude/settings.json"))
hook_cmds = [h["command"] for e in st["hooks"]["SessionStart"] for h in e["hooks"]]
check("settings: SessionStart hook installed once", len([c for c in hook_cmds if "hook session-start" in c]) == 1, hook_cmds)
check("settings: inbox permission rule uses absolute //path", any(r.startswith("Edit(//") and r.endswith("/memory/inbox/**)") for r in st["permissions"]["allow"]))
check("settings: inbox in additionalDirectories", M + "/memory/inbox" in st["permissions"]["additionalDirectories"])

# ---- 1. first cycle discovers repos, everything goes to general
r = cycle("create", "--since-hours", "72")
check("first cycle completes", r.returncode == 0, r.stderr)
did1 = r.stdout.split()[0]
s, R = J("/api/repos")
paths = {x["path"]: x for x in R["repos"]}
check("3 repos discovered from session cwd (git top-level)", set(paths) == {os.path.realpath(p) for p in (Acme, GLOBEX, LEG)}, list(paths))
check("unmapped repos ask which client", all(any(c["code"] == "unmapped" for c in x["checks"]) for x in R["repos"]))
rec = json.load(open(M + "/cycles/" + did1 + "/cycle.json"))
check("without clients all sessions go to general run", [x["group"] for x in rec["runs"]] == ["general"], rec["runs"])
J("/api/adopt", {"id": did1})

# ---- 2. clients + assignment + ownership checks
check("add client acme", J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme", "acme-corp"]})[0] == 200)
check("add client globex", J("/api/client", {"id": "globex", "name": "Globex", "markers": ["globex"]})[0] == 200)
check("client context stub created", "Acme Corp" in (mem("memory/clients/acme/context.md") or ""))
s, R = J("/api/repos")
leg = [x for x in R["repos"] if x["path"].endswith("acme-legacy")][0]
check("legacy repo flagged ambiguous (acme path, globex remote)", any(c["code"] == "ambiguous" for c in leg["checks"]), leg["checks"])
RP = {k: os.path.realpath(v) for k, v in (("acme", Acme), ("globex", GLOBEX), ("leg", LEG))}
check("assign acme-shop", J("/api/assign", {"path": RP["acme"], "client": "acme", "name": "shop"})[0] == 200)
check("assign globex-infra", J("/api/assign", {"path": RP["globex"], "client": "globex"})[0] == 200)
check("assign legacy to acme", J("/api/assign", {"path": RP["leg"], "client": "acme"})[0] == 200)
s, R = J("/api/repos")
leg = [x for x in R["repos"] if x["path"] == RP["leg"]][0]
check("mismatch question when remote points to another client", any(c["code"] == "mismatch" for c in leg["checks"]), leg["checks"])
check("inbox created on confirm", os.path.exists(M + "/memory/inbox/acme/shop.md"))
check("unknown client rejected", J("/api/assign", {"path": RP["leg"], "client": "nope"})[0] == 400)
check("assign unknown path rejected", J("/api/assign", {"path": "/etc", "client": "acme"})[0] == 404)

# ---- 3. map (read-only) via UI
before = subprocess.run(["git", "-C", Acme, "status", "--porcelain"], capture_output=True, text=True).stdout
s, j = J("/api/map", {"path": RP["acme"]})
check("map starts in background", s == 200, j)
wait_idle()
st_ = J("/api/state")[1]
mp = [d for d in st_["cycles"] if d["type"] == "map"][0]
check("map proposal waiting for review", mp["needs_review"], mp)
calls = [json.loads(l) for l in open(H + "/mock-calls.log")]
mapcall = [c for c in calls if c["kind"] == "map"][-1]
check("map ran inside the repo with read-only tools", mapcall["cwd"] == RP["acme"] and mapcall["tools"] == "Read,Glob,Grep" and mapcall["perm"] == "default", mapcall)
check("client repo untouched by map", subprocess.run(["git", "-C", Acme, "status", "--porcelain"], capture_output=True, text=True).stdout == before)
s, det = J("/api/cycle?id=" + mp["id"])
check("map diff writes only the context file", "memory/clients/acme/repos/shop.md" in det["diff"] and det["diff"].count("diff --git") == 1)
check("map surfaces the owner question", "really a Acme repo" in det["report"])
check("adopt map", J("/api/adopt", {"id": mp["id"]})[0] == 200)
reg = json.load(open(M + "/engine/repos.json"))
check("registry records mapped head", reg["repos"][RP["acme"]].get("mapped_head") == subprocess.run(["git", "-C", Acme, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
check("map refused for unconfirmed repo", True)

# ---- 4. session-start hook
out = cycle("hook", "session-start", stdin=json.dumps({"cwd": Acme + "/envs/web", "source": "startup", "session_id": "x"}))
ok = out.returncode == 0 and out.stdout.strip()
ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if ok else ""
check("hook injects repo context from a subfolder", "shop" in ctx and "Terraform for the shop stack" in ctx, out.stdout[:200] + out.stderr[:200])
check("hook names the inbox path", M + "/memory/inbox/acme/shop.md" in ctx)
check("hook adds client context", "Acme Corp" in ctx)
check("hook stays under 10,000 characters", len(ctx) <= 9500)
o2 = cycle("hook", "session-start", stdin=json.dumps({"cwd": H + "/Desktop"}))
check("hook silent outside mapped repos", o2.returncode == 0 and o2.stdout.strip() == "")
o3 = cycle("hook", "session-start", stdin="not json at all")
check("hook never fails on bad input", o3.returncode == 0)
os.rename(M + "/engine/repos.json", M + "/engine/repos.json.bak"); open(M + "/engine/repos.json", "w").write("{broken")
o4 = cycle("hook", "session-start", stdin=json.dumps({"cwd": Acme}))
check("hook never fails on a broken registry", o4.returncode == 0)
os.replace(M + "/engine/repos.json.bak", M + "/engine/repos.json")

# ---- 5. per-client cycles with scope enforcement
with open(M + "/memory/inbox/acme/shop.md", "a") as f:
    f.write("- 2026-10-09: switched state to S3 native locking\n")
add_session(Acme, "a2", "deploy wave 2"); add_session(GLOBEX, "b2", "queue alarms done"); add_session(H + "/Desktop", "g1", "general question")
os.makedirs(H + "/Desktop", exist_ok=True)
r = cycle("create", "--since-last", env={"MOCK_VIOLATE": "1"})
check("scoped cycle completes", r.returncode == 0, r.stderr)
did = r.stdout.split()[0]
rec = json.load(open(M + "/cycles/" + did + "/cycle.json"))
check("one run per client plus general", sorted(x["group"] for x in rec["runs"]) == ["acme", "general", "globex"], rec["runs"])
rv = rec.get("guardrail", {}).get("reverted_outside_scope", [])
check("client run edits to general memory reverted", "memory/me/preferences.md" in rv, rv)
check("cross-client file reverted", "memory/clients/other-client.md" in rv, rv)
check("general run writing into a client folder reverted", "memory/clients/acme/leak.md" in rv, rv)
check("README edits reverted", "README.md" in rv)
s, det = J("/api/cycle?id=" + did)
d = det["diff"]
check("diff touches acme context, globex context and general", "clients/acme/repos/shop.md" in d and "clients/globex/repos/globex-infra.md" in d and "work/releases.md" in d)
check("no leaked files in diff", "leak.md" not in d and "other-client" not in d and "preferences.md" not in d)
check("inbox merged into context and cleared in proposal", "S3 native locking" in d)
check("report has a section per scope", all(x in det["report"] for x in ("# Client: Acme Corp", "# Client: Globex", "# General memory")))
with open(M + "/memory/inbox/acme/shop.md", "a") as f:
    f.write("- 2026-10-09: note written after the cycle started\n")
s, j = J("/api/adopt", {"id": did})
check("adopt scoped cycle with fresh inbox note", s == 200, j)
ib = mem("memory/inbox/acme/shop.md")
check("merged inbox line removed, fresh line kept", "S3 native locking" not in ib and "after the cycle started" in ib, ib)
check("context now has the inbox fact", "S3 native locking" in mem("memory/clients/acme/repos/shop.md"))
check("hook now injects the updated context", "S3 native locking" in cycle("hook", "session-start", stdin=json.dumps({"cwd": Acme})).stdout)

# ---- 6. partial failure
add_session(Acme, "a3", "more work"); add_session(H + "/Desktop", "g2", "general again")
r = cycle("create", "--since-last", env={"MOCK_MODE": "failclient"})
did = r.stdout.split()[0]
rec = json.load(open(M + "/cycles/" + did + "/cycle.json"))
check("client part fails, general part still ready", rec["status"] == "completed" and rec["partial_failures"] == ["acme"], (rec["status"], rec.get("partial_failures")))
s, det = J("/api/cycle?id=" + did)
check("partial failure shows engine log", "client part crashed" in det["engine_log"])
J("/api/discard", {"id": did})

# ---- 7. logs
ev = [json.loads(l) for l in open(M + "/logs/somna.jsonl")]
names = {e["event"] for e in ev}
for need in ("cycle.start", "sessions.collected", "engine.start", "engine.done", "guardrail.revert", "adopt.done", "repo.discovered",
             "repo.mapped", "client.saved", "map.start", "map.done", "hook.context", "hook.error", "engine.failed", "cycle.done", "ui.started_job"):
    check("log has " + need, need in names)
check("every event has ts, level, actor", all("ts" in e and "level" in e and "actor" in e for e in ev))
check("actors recorded (cli, ui, hook)", {"cli", "ui", "hook"} <= {e["actor"] for e in ev}, {e["actor"] for e in ev})
s, j = J("/api/logs?level=warn")
check("logs API filters by level", s == 200 and j["events"] and all(e["level"] in ("warn", "error") for e in j["events"]))
s, j = J("/api/logs?level=debug&event=hook")
check("logs API filters by event prefix", j["events"] and all(e["event"].startswith("hook") for e in j["events"]))
check("per-cycle run.log written", os.path.exists(M + "/cycles/" + did + "/run.log"))
r = cycle("logs", "--level", "warn", "-n", "5")
check("somna logs CLI works", r.returncode == 0 and "WARN" in r.stdout or "ERROR" in r.stdout, r.stderr)
check("no prompt text leaked into logs", "MAP REPO" not in open(M + "/logs/somna.log").read())

# ---- 8. health
s, st_ = J("/api/state")
hc = {c["title"]: c for c in st_["health"]["checks"]}
check("health: hook installed", hc["Repo context hook"]["status"] == "ok")
check("health: repos needing answers flagged", hc["Repos"]["status"] == "warn" and "need your answer" in hc["Repos"]["detail"], hc["Repos"])
check("health: errors in last 24h counted", hc["Errors in the last 24 h"]["status"] == "warn")

print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
