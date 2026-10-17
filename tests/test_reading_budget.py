"""Session sizes, shared reading budget, trimming order, full copy."""
import asyncio, json, os, re, subprocess, sys, time, urllib.request, urllib.error
from playwright.async_api import async_playwright

PY, PORT = sys.argv[1], sys.argv[2]
H = os.environ["HOME"]; M = H + "/somna"; BASE = "http://127.0.0.1:" + PORT
SHOTS = os.environ.get("SHOTS", "/tmp")
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
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (raw.decode() if path == "/" else json.loads(raw or b"{}"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


TOKEN = re.search(r'const TOKEN = "([^"]+)"', req("/")[1]).group(1)
J = lambda path, body=None: req(path, body, TOKEN)
cycle = lambda *a: subprocess.run([PY, M + "/bin/somna", *a], capture_output=True, text=True)


def last():
    out = [json.load(open(os.path.join(M, "cycles", d, "cycle.json"))) for d in os.listdir(M + "/cycles") if d.startswith("cyc_")]
    return sorted(out, key=lambda r: (r["created_at"], r.get("created_ns", 0)))[-1]


WEB = os.path.realpath(H + "/code/acme-shop")
J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})

# a 2-hour style session: decisions early, middle and late, lots of tool calls and noisy output
pdir = H + "/.claude/projects/" + re.sub(r"[^a-zA-Z0-9]", "-", WEB)
with open(pdir + "/big1.jsonl", "w") as f:
    def w(o): f.write(json.dumps(dict(o, sessionId="big1", cwd=WEB)) + "\n")
    w({"type": "user", "timestamp": "2026-10-09T07:00:00Z", "message": {"role": "user", "content": "DECISION-EARLY: we pin the aws provider to 5.x"}})
    for i in range(1200):
        if i == 600:
            w({"type": "user", "message": {"role": "user", "content": "DECISION-MIDDLE: move state to the eu-central-1 bucket"}})
        w({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "terraform plan -out plan%d.tfplan" % (i % 7), "description": "x" * 400}}]}})
        if i % 50 == 0:
            w({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True, "content": "Error: provider registry timeout " + "y" * 500}]}})
    w({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "DECISION-LATE: wave 3 cutover is done, DNS switched"}]}})

s, j = J("/api/sessions?days=7")
big = [x for x in j["sessions"] if x["id"] == "big1"][0]
check("size known per session before reading", big["size_kb"] > 300 and big["est_tokens"] > 70000, big)
check("small sessions small", all(x["size_kb"] < 5 for x in j["sessions"] if x["id"] != "big1"), [(x["id"], x["size_kb"]) for x in j["sessions"]])
check("picker gets the budget", j["budget_kb"] == 400 and j["session_max_kb"] == 250, j)
check("sessions CLI shows sizes", "KB" in cycle("sessions").stdout)

# 1. default budget: big session above the per-session max -> shortened, decisions kept
cycle("create", "--sessions", "big1,a1")
r = last()
ms = {m["id"]: m for m in [i for i in r["inputs"] if i["type"] == "sessions"][0]["sessions"]}
d = open(M + "/cycles/" + r["id"] + "/sessions/acme/big1.md").read()
check("big session shortened to fit", ms["big1"]["truncated"] and ms["big1"]["read_pct"] < 100 and len(d.encode()) <= 252 * 1024, (ms["big1"].get("read_pct"), len(d)))
check("small session read in full", not ms["a1"]["truncated"] and ms["a1"]["read_pct"] == 100, ms["a1"])
check("your words and Claude's answers kept (early, middle, late)", all(k in d for k in ("DECISION-EARLY", "DECISION-MIDDLE", "DECISION-LATE")))
check("tool noise folded, not cut blindly", ms["big1"]["trim_level"] in (2, 3, 4) and "middle of the session left out" not in d, ms["big1"]["trim_level"])
check("repeated errors folded with a count", re.search(r"\[tool_error x\d+\]", d) is not None or "[tool_error]" in d)
full = M + "/cycles/" + r["id"] + "/sessions/acme/big1.full.md"
check("full copy kept for Claude", os.path.exists(full) and "x" * 300 in open(full).read() and ms["big1"]["full_path"] == full)
check("digest header points to the full copy", "Full text: " + full in d)
prompt = open(M + "/cycles/" + r["id"] + "/prompt-acme.md").read()
check("prompt lists the shortened session and its full copy", "big1: read" in prompt and full in prompt)
check("trim logged", "sessions.trimmed" in open(M + "/logs/somna.log").read())
J("/api/discard", {"id": r["id"]})

# 2. small budget: small ones still full, big takes the rest
J("/api/settings", {"settings": {"run_digest_budget_kb": 100}})
cycle("create", "--sessions", "big1,a1")
r = last()
ms = {m["id"]: m for m in [i for i in r["inputs"] if i["type"] == "sessions"][0]["sessions"]}
d = open(M + "/cycles/" + r["id"] + "/sessions/acme/big1.md").read()
check("budget shared: small session still full", ms["a1"]["read_pct"] == 100, ms["a1"])
check("budget shared: big session gets the rest", len(d.encode()) <= 101 * 1024 and ms["big1"]["read_pct"] < 40, (len(d), ms["big1"]["read_pct"]))
check("decisions survive a tight budget", all(k in d for k in ("DECISION-EARLY", "DECISION-MIDDLE", "DECISION-LATE")))
J("/api/discard", {"id": r["id"]})

# 3. tiny budget: last resort middle cut keeps start and end
J("/api/settings", {"settings": {"run_digest_budget_kb": 50, "session_max_kb": 10}})
cycle("create", "--sessions", "big1")
r = last()
d = open(M + "/cycles/" + r["id"] + "/sessions/acme/big1.md").read()
check("last resort keeps start and end", "DECISION-EARLY" in d and "DECISION-LATE" in d and len(d.encode()) <= 12 * 1024, len(d))
J("/api/discard", {"id": r["id"]})

# 4. plenty of budget: nothing shortened
J("/api/settings", {"settings": {"run_digest_budget_kb": 4000, "session_max_kb": 2000}})
cycle("create", "--sessions", "big1,a1")
r = last()
ms = {m["id"]: m for m in [i for i in r["inputs"] if i["type"] == "sessions"][0]["sessions"]}
check("everything fits: read in full, no full copy", not ms["big1"]["truncated"] and ms["big1"]["read_pct"] == 100
      and not os.path.exists(M + "/cycles/" + r["id"] + "/sessions/acme/big1.full.md"), ms["big1"])
J("/api/discard", {"id": r["id"]})
s, j = J("/api/settings", {"settings": {"run_digest_budget_kb": 10}})
check("budget below the minimum rejected", s == 400, j)
J("/api/settings", {"settings": {"run_digest_budget_kb": 400, "session_max_kb": 250}})
cycle("create", "--sessions", "big1,a1")


async def ui():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); errs = []
        pg = await b.new_page(viewport={"width": 1360, "height": 900})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1000)
        if not await pg.is_visible("#pendingPill"):
            check("UI proposal waiting", False)
        await pg.click("#pendingPill"); await pg.wait_for_timeout(900)
        t = await pg.inner_text("main")
        check("UI banner says a session was shortened", "shortened to fit the reading budget" in t, t[:400])
        check("UI sessions table with sizes and read %", "Sessions read" in t and "shortened" in t and "KB" in t)
        await pg.screenshot(path=SHOTS + "/sessions-read.png", full_page=True)
        await pg.click("#runBtn"); await pg.check('input[name="shSrc"][value="pick"]'); await pg.wait_for_timeout(1000)
        lt = await pg.inner_text("#shList")
        check("UI picker shows size and tokens", "KB" in lt and "tokens" in lt, lt[:300])
        check("UI picker flags the very long session", "larger than one session may take" in lt)
        await pg.locator("#shList .srow", has_text="big1").locator("input").check()
        check("UI picker sums what will be read", "KB to read" in await pg.inner_text("#shSel"))
        await pg.screenshot(path=SHOTS + "/picker-sizes.png")
        await pg.keyboard.press("Escape")
        await pg.click('nav button[data-tab="settings"]'); await pg.wait_for_timeout(1000)
        st = await pg.inner_text("main")
        check("UI settings show the reading budget", "Reading budget per client run" in st and "Most one session can take" in st)
        check("UI no page errors", not errs, errs)
        await b.close()

asyncio.run(ui())
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
