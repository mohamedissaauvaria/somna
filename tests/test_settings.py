"""First-use guide, help, settings, schedule tick, models from the provider, model check."""
import asyncio, datetime as dt, json, os, re, stat, subprocess, sys, time, urllib.request, urllib.error
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


def cycle(*a, env=None):
    return subprocess.run([PY, M + "/bin/somna", *a], capture_output=True, text=True, env=dict(os.environ, **(env or {})))


def recs():
    out = [json.load(open(os.path.join(M, "cycles", d, "cycle.json"))) for d in os.listdir(M + "/cycles") if d.startswith("cyc_")]
    return sorted(out, key=lambda r: (r["created_at"], r.get("created_ns", 0)))


cfg = lambda: json.load(open(M + "/engine/config.json"))

# ---------- setup status before anything ----------
s, u = J("/api/setup")
ids = {x["id"]: x["done"] for x in u["steps"]}
check("guide has 9 steps", u["total"] == 9 and list(ids) == ["claude", "hooks", "personal", "client", "scan", "confirm", "map", "settings", "cycle"], ids)
check("guide: Claude Code and hooks done, the rest open", ids["claude"] and ids["hooks"] and not ids["client"] and not ids["cycle"] and not ids["settings"], ids)
check("guide shows the sign-in method", "claude.ai" in u["steps"][0]["detail"], u["steps"][0])

# ---------- settings: read, save, validate ----------
s, st = J("/api/settings")
check("settings view", s == 200 and "max_budget_usd" in st["settings"] and st["schedule"]["schedule"]["nightly"]["time"] == "02:00", st.get("schedule"))
s, j = J("/api/settings", {"settings": {"max_budget_usd": 2.5, "max_turns": 40, "parallel_runs": 2, "hold_low_confidence": False},
                           "schedule": {"nightly": {"time": "01:30", "days": [0, 1, 2, 3, 4]},
                                        "weekly": {"enabled": True, "day": 6, "time": "04:00", "model": "claude-opus-5-5"}}})
check("settings saved", s == 200 and "Saved" in j["message"], j)
c = cfg()
check("config updated", c["max_budget_usd"] == 2.5 and c["max_turns"] == 40 and c["parallel_runs"] == 2 and c["schedule"]["nightly"]["time"] == "01:30"
      and c["schedule"]["weekly"]["enabled"] and c["schedule"]["weekly"]["model"] == "claude-opus-5-5", c)
check("settings committed to git", "settings:" in subprocess.run(["git", "-C", M, "log", "-1", "--format=%s"], capture_output=True, text=True).stdout)
check("weekly keeps its default instructions", "Weekly consolidation" in c["schedule"]["weekly"]["instructions"])
for bad, why in (({"settings": {"max_budget_usd": -1}}, "between"), ({"settings": {"parallel_runs": 99}}, "between"),
                 ({"settings": {"nope": 1}}, "unknown"), ({"settings": {"model": "rm -rf /"}}, "not a model"),
                 ({"schedule": {"nightly": {"time": "25:00"}}}, "time"), ({"schedule": {"nightly": {"enabled": True, "days": []}}}, "at least one day"),
                 ({"schedule": {"weekly": {"instructions": "x" * 5000}}}, "4,096")):
    s, j = J("/api/settings", bad)
    check("rejects " + json.dumps(bad)[:60], s == 400 and why in j["error"], j)
s, j = J("/api/settings", {"settings": {"max_budget_usd": None}})
check("empty cap means no cap", s == 200 and cfg()["max_budget_usd"] is None, j)
J("/api/settings", {"settings": {"max_budget_usd": 2.5}})
s, u = J("/api/setup")
check("guide: settings step done after saving", [x for x in u["steps"] if x["id"] == "settings"][0]["done"])

# ---------- limits reach Claude Code ----------
WEB = os.path.realpath(H + "/code/acme-shop")
J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})
cycle("create", "--sessions", "a1")
lines = [json.loads(l) for l in open(H + "/mock-calls.log")]
lim = [l for l in lines if "max_turns" in l][-1]
check("turn limit and spend cap passed to Claude Code", lim["max_turns"] == "40" and lim["budget"] == "2.5", lim)
check("start messages explain the job", "costs nothing" in J("/api/scan", {"days": 3})[1]["message"])
for _ in range(60):
    if not J("/api/progress")[1].get("running"):
        break
    time.sleep(0.3)

# ---------- scheduler tick ----------
now = dt.datetime.now()
def at(delta_min):
    return (now + dt.timedelta(minutes=delta_min)).strftime("%H:%M")
wd = now.weekday()
J("/api/settings", {"schedule": {"nightly": {"enabled": True, "time": at(-5), "days": [wd]}, "weekly": {"enabled": False}}})
n0 = len(recs())
cycle("tick")
r = recs()[-1]
check("tick runs the nightly cycle when it is due", len(recs()) == n0 + 1 and r["type"] == "cycle" and r["status"] in ("completed", "failed"), r.get("status"))
check("tick logged", "schedule.run" in open(M + "/logs/somna.log").read())
n1 = len(recs())
cycle("tick")
check("tick does not run the same slot twice", len(recs()) == n1)
J("/api/settings", {"schedule": {"nightly": {"time": at(-13 * 60) if now.hour >= 13 else at(-5), "days": [wd]}}})
st_ = json.load(open(M + "/cycles/state.json"))
if now.hour >= 13:
    st_.pop("last_nightly_slot", None); json.dump(st_, open(M + "/cycles/state.json", "w"))
    cycle("tick")
    check("no catch-up after 12 hours", len(recs()) == n1)
J("/api/settings", {"schedule": {"nightly": {"enabled": False}, "weekly": {"enabled": True, "day": wd, "time": at(-2), "model": "claude-opus-5-5", "since_days": 7,
                                                                             "instructions": "Weekly test pass."}}})
cycle("tick")
r = recs()[-1]
check("tick runs the weekly cycle with its model and instructions", len(recs()) == n1 + 1 and r["model"]["id"] == "claude-opus-5-5" and r.get("instructions") == "Weekly test pass.", (r.get("model"), r.get("instructions")))
sess = [i for i in r["inputs"] if i["type"] == "sessions"][0]
check("weekly reads the last 7 days", (dt.datetime.utcnow() - dt.datetime.strptime(sess["since"], "%Y-%m-%dT%H:%M:%SZ")).days >= 6, sess.get("since"))
ss = cycle("schedule").stdout
check("schedule CLI shows next runs", "next nightly: off" in ss and "next weekly" in ss, ss)
hc = [c_ for c_ in J("/api/state")[1]["health"]["checks"] if c_["title"] == "Schedule"][0]
check("health shows the schedule", "next weekly" in hc["detail"], hc)

# ---------- models ----------
m = J("/api/models?refresh=1")[1]
check("signed in with an account: built-in model list with an honest note", m["source"].startswith("Built-in") and "claude-opus-5-5" in [x["id"] for x in m["models"]] and "Check" in m["note"], m)
s, j = J("/api/check_model", {"model": "claude-sonnet-5-5"})
check("model check passes through Claude Code", s == 200 and "works with your Claude Code" in j["message"], j)
st_ = J("/api/settings")[1]
check("check result remembered", st_["model_checks"]["claude-sonnet-5-5"]["ok"] and "claude-sonnet-5-5" in st_["model_checks"]["claude-sonnet-5-5"]["used"], st_["model_checks"])
r_ = cycle("models", "--check", "claude-bad-1", env={"MOCK_BADMODELS": "claude-bad-1"})
check("a model that does not work is reported", r_.returncode == 1 and "did not work" in r_.stderr, r_.stderr)
# Bedrock: settings env + an aws CLI that lists inference profiles
sett = json.load(open(H + "/.claude/settings.json"))
sett.setdefault("env", {}).update({"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "eu-central-1"})
json.dump(sett, open(H + "/.claude/settings.json", "w"))
aws = H + "/.local/bin/aws"
open(aws, "w").write("#!/bin/sh\ncat <<'EOF'\n" + json.dumps({"inferenceProfileSummaries": [
    {"inferenceProfileName": "EU Claude Opus 5.5", "inferenceProfileId": "eu.anthropic.claude-opus-5-5",
     "inferenceProfileArn": "arn:aws:bedrock:eu-central-1:123456789012:inference-profile/eu.anthropic.claude-opus-5-5", "status": "ACTIVE",
     "models": [{"modelArn": "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-opus-5-5"}]},
    {"inferenceProfileName": "Other", "inferenceProfileId": "eu.meta.llama", "inferenceProfileArn": "arn:x", "models": []}]}) + "\nEOF\n")
os.chmod(aws, 0o755)
m = J("/api/models?refresh=1")[1]
check("Bedrock: models are inference profile ARNs from AWS", m["source"].startswith("Amazon Bedrock") and [x["id"] for x in m["models"]] == ["arn:aws:bedrock:eu-central-1:123456789012:inference-profile/eu.anthropic.claude-opus-5-5"], m)
s, j = J("/api/settings", {"settings": {"model": "arn:aws:bedrock:eu-central-1:123456789012:inference-profile/eu.anthropic.claude-opus-5-5"}})
check("an ARN is accepted as a model", s == 200, j)
sett["env"] = {}
json.dump(sett, open(H + "/.claude/settings.json", "w"))
J("/api/models?refresh=1")
J("/api/settings", {"settings": {"model": ""}})


for pid in J("/api/state")[1]["pending"]:
    J("/api/discard", {"id": pid})


async def ui():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); errs = []
        pg = await b.new_page(viewport={"width": 1360, "height": 900})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1000)
        txt = await pg.inner_text("main")
        check("UI opens on Start here while setup is incomplete", "Start here" in txt and "of 9 done" in txt, txt[:200])
        check("UI next step highlighted", await pg.locator(".stepc.next").count() == 1)
        await pg.screenshot(path=SHOTS + "/start.png", full_page=True)
        await pg.click('header [data-help="run"]'); await pg.wait_for_timeout(300)
        pop = await pg.inner_text("#pop")
        check("UI help popover explains Run cycle now", "Usually 2 to 6 minutes" in pop, pop)
        await pg.screenshot(path=SHOTS + "/help.png")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(200)
        check("UI Esc closes help", not await pg.is_visible("#pop"))
        await pg.click('nav button[data-tab="repos"]'); await pg.wait_for_timeout(900)
        check("UI help buttons on Repos", await pg.locator('[data-help="map"]').count() >= 1 and await pg.locator('[data-help="scan"]').count() == 1)
        await pg.click('nav button[data-tab="settings"]'); await pg.wait_for_timeout(1200)
        st = await pg.inner_text("main")
        check("UI settings sections", all(k in st for k in ("Schedule", "Models", "Limits and cost", "Memory", "Review", "Next nightly")), st[:300])
        check("UI model list marks recommended models", "recommended" in await pg.inner_html("#f_model"))
        await pg.fill("#nTime", "03:15"); await pg.check("#nOn")
        for i in range(7):
            await pg.locator('[data-nday="%d"]' % i).check()
        await pg.fill("#f_parallel_runs", "3")
        await pg.click("#setSave"); await pg.wait_for_timeout(1200)
        c = cfg()
        check("UI saves settings", c["schedule"]["nightly"]["time"] == "03:15" and c["schedule"]["nightly"]["enabled"] and c["parallel_runs"] == 3, (c["schedule"]["nightly"], c["parallel_runs"]))
        await pg.select_option("#f_model", "claude-opus-5-5")
        await pg.click('[data-check="f_model"]'); await pg.wait_for_timeout(1500)
        check("UI model Check shows the result", "works with your Claude Code" in await pg.inner_text("#f_modelChk"), await pg.inner_text("#f_modelChk"))
        await pg.screenshot(path=SHOTS + "/settings.png", full_page=True)
        pdir = H + "/.claude/projects/" + re.sub(r"[^a-zA-Z0-9]", "-", WEB)
        open(pdir + "/n1.jsonl", "w").write(json.dumps({"type": "user", "sessionId": "n1", "cwd": WEB, "message": {"role": "user", "content": "new work"}}) + "\n")
        await pg.click("#runBtn"); await pg.wait_for_timeout(200); await pg.click("#shStart")
        info = ""
        for _ in range(30):
            await pg.wait_for_timeout(250)
            if await pg.is_visible("#dock"):
                info = await pg.inner_text("#dInfo")
                if info: break
        check("UI dock explains what the run does", "Usually 2 to 6 minutes" in info, info)
        ph = await b.new_page(viewport={"width": 390, "height": 840})
        ph.on("pageerror", lambda e: errs.append(str(e)))
        await ph.goto(BASE + "/"); await ph.wait_for_timeout(800)
        await ph.click('nav button[data-tab="settings"]'); await ph.wait_for_timeout(1000)
        sw = await ph.evaluate("document.scrollingElement.scrollWidth")
        check("UI settings fit a phone", sw <= 390, sw)
        await ph.screenshot(path=SHOTS + "/settings-phone.png", full_page=True)
        check("UI no page errors", not errs, errs)
        await b.close()

asyncio.run(ui())
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
