"""Instructions, model and session ids, cancel, live events, store limits, versions, redact."""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error
KIT = os.environ.get("KIT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PY, PORT = sys.argv[1], sys.argv[2]
H = os.environ["HOME"]; M = H + "/somna"; BASE = "http://127.0.0.1:" + PORT
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "   -> " + str(extra)[:400]))
    if not cond:
        FAILS.append(name)


def req(path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method="POST" if data is not None else "GET")
    if token: r.add_header("X-Somna-Token", token)
    if data is not None: r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (raw.decode() if path == "/" else json.loads(raw or b"{}"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


TOKEN = re.search(r'const TOKEN = "([^"]+)"', req("/")[1]).group(1)
J = lambda path, body=None: req(path, body, TOKEN)


def cycle(*a, env=None, stdin=None):
    return subprocess.run([PY, M + "/bin/somna", *a], capture_output=True, text=True, env=dict(os.environ, **(env or {})), input=stdin)


def git(*a):
    return subprocess.run(["git", "-C", M, *a], capture_output=True, text=True).stdout


def wait_idle(t=90):
    for _ in range(int(t / 0.3)):
        if not J("/api/progress")[1].get("running"):
            return True
        time.sleep(0.3)
    return False


def last():
    return json.load(open(sorted([os.path.join(M, "cycles", d, "cycle.json") for d in os.listdir(M + "/cycles") if d.startswith("cyc_")],
                                 key=lambda p: (json.load(open(p))["created_at"], json.load(open(p)).get("created_ns", 0)))[-1]))


def calls():
    return [json.loads(l) for l in open(H + "/mock-calls.log")] if os.path.exists(H + "/mock-calls.log") else []


WEB = os.path.realpath(H + "/code/acme-shop"); GLOBEX = os.path.realpath(H + "/code/globex-infra")
J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme"]})
J("/api/client", {"id": "globex", "name": "Globex", "markers": ["globex"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})
J("/api/assign", {"path": GLOBEX, "client": "globex"})

# ---------- D3 sessions listing ----------
s, j = J("/api/sessions?days=7")
ids = sorted(x["id"] for x in j.get("sessions", []))
check("D3 sessions API lists recent sessions with ids", ids == ["a1", "b1", "c1"], j)
a1 = [x for x in j["sessions"] if x["id"] == "a1"][0]
check("D3 session list shows repo, client and first line", a1["repo"] == "shop" and a1["client"] == "acme" and "provider pin" in a1["title"], a1)
check("D3 sessions CLI", "a1" in cycle("sessions").stdout)

# ---------- D1 D2 D3 D5 D6 M5: create with instructions, model, explicit sessions ----------
state_before = json.load(open(M + "/cycles/state.json")) if os.path.exists(M + "/cycles/state.json") else {}
instr = "Focus on the provider pin decision. Keep the ADR list as it is."
s, j = J("/api/run", {"instructions": instr, "model": "claude-sonnet-5-5", "session_ids": ["a1"]})
check("D1 run with instructions accepted", s == 200, j)
check("finished", wait_idle())
r = last()
check("D1 instructions stored on the cycle", r.get("instructions") == instr, r.get("instructions"))
check("D2 model stored on the cycle", r["model"]["id"] == "claude-sonnet-5-5", r["model"])
c = calls()[-1]
check("D2 model passed to Claude Code", c["model"] == "claude-sonnet-5-5", c)
check("D1 instructions reached the prompt", c["instructions"] == instr, c)
sess = [i for i in r["inputs"] if i["type"] == "sessions"][0]
check("D3 only the chosen session was read", sess["session_ids"] == ["a1"] and sess.get("selected") is True, sess)
check("D3 chosen sessions do not move the since-last marker",
      (json.load(open(M + "/cycles/state.json")) if os.path.exists(M + "/cycles/state.json") else {}) == state_before)
ddir = M + "/cycles/" + r["id"]
ev = [json.loads(l) for l in open(ddir + "/events.jsonl")]
check("D5 event stream written", any(e["kind"] == "init" for e in ev) and any(e["kind"] == "result" for e in ev), ev[:3])
check("M5 memory reads visible", any(e.get("memory") == "read" and e["target"] == "memory/index.md" for e in ev), ev)
check("M5 memory writes visible", any(e.get("memory") == "write" and e["target"].startswith("memory/clients/acme/repos/") for e in ev), ev)
check("D5 Claude's own words in the stream", any(e["kind"] == "text" and "Verifying" in e["text"] for e in ev))
check("D6 token usage recorded", (r["usage"].get("tokens") or {}).get("input_tokens", 0) > 0 and r["usage"]["memory_writes"] >= 1, r["usage"])
u = json.load(open(ddir + "/usage.json"))
check("D6 usage.json per scope", "acme" in u and u["acme"]["tokens"]["output_tokens"] > 0 and u["acme"]["final"], u)
s, d = J("/api/cycle?id=" + r["id"])
check("M5 review shows memory activity", any(p.startswith("memory/clients/acme") for p, n in d["memory_activity"]["write"]), d.get("memory_activity"))
check("summary carries model and instructions flag", d["summary"]["model"] == "claude-sonnet-5-5" and d["summary"]["instructions"] is True)
J("/api/discard", {"id": r["id"]})

# ---------- D1 D3 validation ----------
s, j = J("/api/run", {"instructions": "x" * 4097})
check("D1 instructions over 4,096 chars rejected", s == 400 and "4096" in j["error"], j)
s, j = J("/api/run", {"session_ids": ["s%d" % i for i in range(101)]})
check("D3 more than 100 sessions rejected", s == 400 and "100" in j["error"], j)
s, j = J("/api/run", {"session_ids": ["../etc"]})
check("D3 bad session id rejected", s == 400, j)
check("D1 CLI rejects long instructions", cycle("create", "--instructions", "y" * 5000).returncode == 1)

# ---------- D7 typed errors ----------
r0 = cycle("create", "--sessions", "nope1,a1")
r = last()
check("D7 input_session_unavailable", r["status"] == "failed" and r["error"]["type"] == "input_session_unavailable" and "nope1" in r["error"]["message"], r.get("error"))
cycle("create", "--sessions", "a1", env={"MOCK_MODE": "fail"})
r = last()
check("D7 engine crash is internal_error", r["status"] == "failed" and r["error"]["type"] == "internal_error", r.get("error"))
check("D7 per run error type", r["runs"][0].get("error_type") == "internal_error", r["runs"])
cycle("create", "--sessions", "a1", env={"MOCK_IS_ERROR": "1"})
r = last()
check("D7 engine is_error result is internal_error", r["status"] == "failed" and r["error"]["type"] == "internal_error", r.get("error"))
cfg = json.load(open(M + "/engine/config.json")); cfg["timeout_minutes"] = 0.03; json.dump(cfg, open(M + "/engine/config.json", "w"))
t0 = time.time()
cycle("create", "--sessions", "a1", env={"MOCK_SLOW": "8"})
r = last()
check("D7 timeout type", r["status"] == "failed" and r["error"]["type"] == "timeout", r.get("error"))
check("D7 timeout kills the engine quickly", time.time() - t0 < 7, time.time() - t0)
cfg["timeout_minutes"] = 30; json.dump(cfg, open(M + "/engine/config.json", "w"))
check("D7 error type shown in summary", J("/api/cycle?id=" + r["id"])[1]["summary"]["error_type"] == "timeout")

# ---------- D4 cancel + live progress ----------
p = subprocess.Popen([PY, M + "/bin/somna", "create", "--since-hours", "48"], env=dict(os.environ, MOCK_STEP_DELAY="1.2"),
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
live = None
for _ in range(60):
    pr = J("/api/progress")[1]
    if pr.get("running") and pr.get("live"):
        live = pr
        break
    time.sleep(0.25)
check("D5 progress shows live engine events", bool(live) and any(e["kind"] in ("tool", "text", "init") for e in live["live"]), live)
check("D6 progress shows live tokens", bool(live) and live["tokens"]["input"] > 0, live and live.get("tokens"))
running_id = live["id"] if live else None
s, j = J("/api/cancel", {"id": running_id})
check("D4 cancel accepted", s == 200 and "anceled" in j["message"], j)
out, err = p.communicate(timeout=30)
r = json.load(open(M + "/cycles/" + running_id + "/cycle.json"))
check("D4 status canceled", r["status"] == "canceled" and r["review"]["decision"] == "canceled", r["status"])
check("D4 no output branch left", "cycle/" + running_id not in git("branch", "--list", "cycle/*"))
check("D4 no worktree left", not os.path.exists(M + "/.somna-worktrees/" + running_id))
check("D4 lock released", not J("/api/progress")[1]["running"])
check("D4 process exited cleanly", p.returncode == 0, err)
s, j = J("/api/cancel", {"id": running_id})
check("D4 cancel of finished run refused", s == 400, j)
check("D4 canceled logged", "cycle.canceled" in open(M + "/logs/somna.log").read())

# ---------- D8 pipeline prompt ----------
prompt = open(M + "/engine/prompt.md").read()
check("D8 prompt follows the five pipeline steps", all(k in prompt for k in ("1. Verify", "2. Deduplicate and merge", "3. Replace stale or contradicted", "4. Reorganize", "5. Surface insights")))
check("D8 report has Replaced and Insights sections", "## Replaced" in prompt and "## Insights" in prompt)

# ---------- D9 list ----------
recs = [x for x in os.listdir(M + "/cycles") if x.startswith("cyc_")]
cycle("archive", recs[0])
lst = cycle("list", "--limit", "2").stdout.strip().splitlines()
check("D9 list --limit", len(lst) == 2, lst)
n_all = len(cycle("list", "--include-archived", "--limit", "100").stdout.strip().splitlines())
n_def = len(cycle("list", "--limit", "100").stdout.strip().splitlines())
check("D9 list --include-archived shows archived", n_all == n_def + 1, (n_all, n_def))

# ---------- M3 instructions per context ----------
s, j = J("/api/instructions", {"kind": "repo", "key": WEB, "text": "Use envs/ for anything per account. Ask before touching modules/net."})
check("M3 repo instructions saved", s == 200, j)
s, j = J("/api/instructions", {"kind": "client", "key": "acme", "text": "Acme prefers small PRs with an ADR link."})
check("M3 client instructions saved", s == 200, j)
s, j = J("/api/instructions", {"kind": "client", "key": "acme", "text": "z" * 4097})
check("M3 instructions over 4,096 rejected", s == 400, j)
hook = lambda env=None: json.loads(cycle("hook", "session-start", stdin=json.dumps({"cwd": WEB + "/envs"}), env=env).stdout or "{}") \
    .get("hookSpecificOutput", {}).get("additionalContext", "")
h = hook()
check("M3 hook injects repo instructions", "How to use this repo context" in h and "Ask before touching modules/net" in h, h[:600])
check("M3 hook injects client instructions", "How to use this client context" in h and "small PRs" in h)
check("M2 hook marks context read-only and as data", "Access: read-only" in h)
check("M3 CLI shows instructions", "small PRs" in cycle("instructions", "acme").stdout)
cycle("instructions", "shop", "--clear")
check("M3 clear works", "Ask before touching" not in hook())

# ---------- M4 try a proposal ----------
r = cycle("map", WEB); mid = re.search(r"somna review (cyc_\w+)", r.stdout).group(1)
s, d = J("/api/cycle?id=" + mid)
tt = d.get("try_targets") or []
check("M4 proposal lists repos to try it in", len(tt) == 1 and tt[0]["path"] == WEB and "SOMNA_TRY=" + mid in tt[0]["command"], tt)
check("M4 map events show repo reads", any(e.get("target", "").startswith("repo/") for e in map(json.loads, open(M + "/cycles/" + mid + "/events.jsonl"))))
h_main, h_try = hook(), hook({"SOMNA_TRY": mid})
check("M4 normal session does not see the proposal", "Terraform for the shop stack" not in h_main, h_main[:300])
check("M4 trial session sees the proposal", "TRIAL SESSION" in h_try and "Terraform for the shop stack" in h_try, h_try[:400])
check("M4 bad trial id falls back to normal context", "TRIAL" not in hook({"SOMNA_TRY": "cyc_nope"}))
check("M4 try CLI prints the command", "SOMNA_TRY=" + mid in cycle("try", mid).stdout)
s, j = J("/api/try", {"id": mid})
check("M4 try API returns the command", s == 200 and "SOMNA_TRY=" + mid in j["message"], j)
check("M4 trial logged", '"trial": "' + mid + '"' in open(M + "/logs/somna.jsonl").read())

# ---------- M1 versions and redact ----------
f = "memory/me/writing-style.md"
s, fj = J("/api/file?path=" + f)
s, j = J("/api/file", {"path": f, "content": fj["content"] + "\naws_secret=AKIAIOSFODNN7EXAMPLE\n", "sha": fj["sha"]})
s, fj = J("/api/file?path=" + f)
s, j = J("/api/file", {"path": f, "content": fj["content"].replace("aws_secret=AKIAIOSFODNN7EXAMPLE\n", ""), "sha": fj["sha"]})
s, v = J("/api/versions?path=" + f)
vs = v["versions"]
check("M1 versions listed newest first with current flag", len(vs) >= 3 and vs[0]["current"] and not vs[1]["current"], vs[:3])
leak = vs[1]["version"]
s, j = J("/api/redact", {"path": f, "version": vs[0]["version"]})
check("M1 current version cannot be redacted", s == 400 and "current version" in j["error"], j)
s, j = J("/api/redact", {"path": f, "version": leak})
check("M1 redact refused while a proposal waits", s == 400 and "waiting proposal" in j["error"], j)
J("/api/discard", {"id": mid})
os.makedirs(M + "/cycles/" + mid, exist_ok=True)
with open(M + "/cycles/" + mid + "/report.md", "a") as fh:
    fh.write("copied: aws_secret=AKIAIOSFODNN7EXAMPLE\n")
s, j = J("/api/redact", {"path": f, "version": leak})
check("M1 redact succeeds", s == 200 and "Redacted" in j["message"], j)
allrev = git("rev-list", "--all").split()
hits = subprocess.run(["git", "-C", M, "grep", "-l", "AKIAIOSFODNN7EXAMPLE", *allrev], capture_output=True, text=True).stdout
check("M1 secret gone from every commit", hits.strip() == "", hits[:300])
check("M1 secret gone from git objects", "AKIAIOSFODNN7EXAMPLE" not in subprocess.run("cd '%s' && git cat-file --batch-all-objects --batch" % M, shell=True, capture_output=True, text=True, errors="replace").stdout)
check("M1 audit trail kept (commit count unchanged)", len(git("log", "--oneline", "--", f).splitlines()) >= 3)
vs2 = J("/api/versions?path=" + f)[1]["versions"]
check("M1 version shows as redacted", any(x.get("redacted") for x in vs2), vs2[:3])
check("M1 local run copies scrubbed", "AKIAIOSFODNN7EXAMPLE" not in open(M + "/cycles/" + mid + "/report.md").read())
check("M1 current file intact", "aws_secret" not in open(M + "/" + f).read() and len(open(M + "/" + f).read()) > 20)
check("M1 changelog entry", "redacted an old version of " + f in open(M + "/CHANGELOG.md").read())
check("M1 redact logged without the secret", "memory.redacted" in open(M + "/logs/somna.log").read() and "AKIAIOSFODNN7EXAMPLE" not in open(M + "/logs/somna.log").read())
check("M1 working tree clean after redact", git("status", "--porcelain", "--untracked-files=no").strip() == "", git("status", "--porcelain"))
check("M1 cycles still work after history rewrite", cycle("create", "--sessions", "b1").returncode == 0 and last()["status"] == "completed")

# ---------- M6 limits ----------
big = "memory/work/huge.md"
s, j = J("/api/file", {"path": big, "content": "x" * 101 * 1024, "sha": "e3b0c44298fc1c14"})
check("M6 editor refuses files over 100 kB", s == 400 and "100 kB" in j["error"], j)
open(M + "/" + big, "w").write("y" * 120 * 1024)
hl = J("/api/state")[1]["health"]
lim = [c for c in hl["checks"] if c["title"] == "Memory limits"][0]
check("M6 health flags files over 100 kB", lim["status"] == "warn" and "huge.md" in lim["detail"], lim)
cycle("create", "--sessions", "c1")
r = last()
check("M6 cycle records files over 100 kB", "huge.md" in json.dumps(r.get("limits")), r.get("limits"))
os.remove(M + "/" + big)

# ---------- M2 read-only for agents ----------
st = json.load(open(H + "/.claude/settings.json"))
deny = st["permissions"].get("deny", [])
check("M2 deny rules for me/, work/, clients/, index.md", all(any(("/memory/" + k) in r for r in deny) for k in ("me/**", "work/**", "clients/**", "index.md")), deny)
check("M2 inbox and scratch stay writable", not any("/memory/inbox" in r or "/memory/scratch" in r for r in deny)
      and any("/memory/inbox/**" in r for r in st["permissions"]["allow"]))
ro = [c for c in J("/api/state")[1]["health"]["checks"] if c["title"] == "Memory read-only for agents"][0]
check("M2 health confirms read-only", ro["status"] == "ok", ro)
subprocess.run(["bash", KIT + "/uninstall.sh"], capture_output=True, text=True)
st = json.load(open(H + "/.claude/settings.json"))
check("M2 uninstall removes the deny rules", not st.get("permissions", {}).get("deny"), st.get("permissions"))
r2 = subprocess.run(["bash", KIT + "/install.sh", "--no-schedule", "--force-non-mac", "--agents-can-edit-memory"], capture_output=True, text=True)
st = json.load(open(H + "/.claude/settings.json"))
check("M2 --agents-can-edit-memory leaves memory writable", r2.returncode == 0 and not st.get("permissions", {}).get("deny"), r2.stdout[-400:])
subprocess.run(["bash", KIT + "/install.sh", "--no-schedule", "--force-non-mac"], capture_output=True, text=True)
st = json.load(open(H + "/.claude/settings.json"))
check("M2 re-install does not duplicate rules", len(st["permissions"]["deny"]) == len(set(st["permissions"]["deny"])) and len(st["permissions"]["deny"]) > 4)

check("doctor runs", cycle("doctor").returncode in (0, 1))
check("version", "1." in cycle("--version").stdout)
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
