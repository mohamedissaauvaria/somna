import asyncio, json, os, re, subprocess, sys, urllib.request, urllib.error
from playwright.async_api import async_playwright

PY, PORT = sys.argv[1], sys.argv[2]
SHOTS = os.environ.get("SHOTS", "/tmp")
H = os.environ["HOME"]; M = H + "/somna"; BASE = "http://127.0.0.1:" + PORT
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "   -> " + str(extra)[:300]))
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
cycle = lambda *a: subprocess.run([PY, M + "/bin/somna", *a], capture_output=True, text=True)
WEB = os.path.realpath(H + "/code/acme-shop"); GLOBEX = os.path.realpath(H + "/code/globex-infra")
J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme"]})
J("/api/client", {"id": "globex", "name": "Globex", "markers": ["globex"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})
J("/api/assign", {"path": GLOBEX, "client": "globex"})


async def idle(pg, t=60):
    for _ in range(t * 4):
        if not J("/api/progress")[1].get("running"):
            return True
        await pg.wait_for_timeout(250)
    return False


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); errs = []
        pg = await b.new_page(viewport={"width": 1360, "height": 900})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(800)

        # run sheet with instructions, model and chosen sessions
        await pg.click("#runBtn"); await pg.wait_for_timeout(300)
        check("sheet opens", await pg.is_visible("#sheet"))
        await pg.fill("#shInstr", "Focus on the provider pin. Keep the ADR list.")
        check("character counter", "45 / 4,096" in await pg.inner_text("#shCount"), await pg.inner_text("#shCount"))
        opts = await pg.eval_on_selector_all("#shModel option", "o => o.map(x => x.value)")
        check("model list from the docs", "claude-opus-5-5" in opts and "claude-sonnet-4-6" in opts, opts)
        await pg.select_option("#shModel", "claude-opus-5-5")
        await pg.check('input[name="shSrc"][value="pick"]'); await pg.wait_for_timeout(700)
        rows = await pg.locator("#shList .srow").count()
        check("session picker lists sessions", rows == 3, rows)
        check("session rows show the first line", "fix the provider pin" in await pg.inner_text("#shList"))
        await pg.locator("#shList .srow", has_text="fix the provider pin").locator("input").check()
        check("selection counter", "1 selected" in await pg.inner_text("#shSel"))
        await pg.screenshot(path=SHOTS + "/sheet.png")
        await pg.click("#shStart"); await pg.wait_for_timeout(500)
        check("sheet closes on start", not await pg.is_visible("#sheet"))
        check("dock shows", await pg.is_visible("#dock"))
        await pg.wait_for_timeout(900)
        await pg.screenshot(path=SHOTS + "/dock-live.png")
        check("run finished", await idle(pg))
        await pg.wait_for_timeout(2500)
        await pg.click("#dOpen") if await pg.is_visible("#dOpen") else None
        await pg.wait_for_timeout(900)
        main_txt = await pg.inner_text("main")
        check("review shows the instructions", "Instructions for this cycle" in main_txt and "Keep the ADR list" in main_txt, main_txt[:500])
        check("review shows the model", "claude-opus-5-5" in main_txt)
        check("review says sessions were chosen", "chosen by you" in main_txt)
        check("review shows memory activity", "Memory it read and wrote" in main_txt)
        check("review shows token count", "tokens" in main_txt)
        check("try card for the changed repo", "Try it before adopting" in main_txt and "SOMNA_TRY=" in main_txt, main_txt[-800:])
        await pg.screenshot(path=SHOTS + "/review.png", full_page=True)
        await pg.click('[data-copy="0"]'); await pg.wait_for_timeout(300)
        await pg.click('[data-act="discard"]'); await pg.wait_for_timeout(900)

        # cancel from the dock
        await pg.click("#runBtn"); await pg.wait_for_timeout(200)
        await pg.click("#shStart")
        seen = False
        for _ in range(40):
            await pg.wait_for_timeout(250)
            if await pg.is_visible("#dCancel"):
                seen = True; break
        check("cancel button while running", seen)
        await pg.wait_for_timeout(700)
        feed = await pg.inner_text("#dFeed")
        check("live feed shows engine activity", feed.strip() != "", feed)
        await pg.screenshot(path=SHOTS + "/dock-cancel.png")
        await pg.click("#dCancel")
        await idle(pg, 30); await pg.wait_for_timeout(2500)
        check("dock says canceled", "Canceled" in await pg.inner_text("#dTitle"), await pg.inner_text("#dTitle"))
        await pg.click('nav button[data-tab="history"]'); await pg.wait_for_timeout(600)
        check("history shows the canceled run", "Canceled" in await pg.inner_text("main"))

        # memory versions and redact
        f = "memory/me/writing-style.md"
        s, fj = J("/api/file?path=" + f)
        J("/api/file", {"path": f, "content": fj["content"] + "\ntoken=ghp_EXAMPLESECRET99\n", "sha": fj["sha"]})
        s, fj = J("/api/file?path=" + f)
        J("/api/file", {"path": f, "content": fj["content"].replace("token=ghp_EXAMPLESECRET99\n", ""), "sha": fj["sha"]})
        await pg.click('nav button[data-tab="memory"]'); await pg.wait_for_timeout(700)
        await pg.click('.files button[data-path="' + f + '"]'); await pg.wait_for_timeout(500)
        await pg.click("#showVers"); await pg.wait_for_timeout(900)
        vt = await pg.inner_text(".viewer")
        check("versions listed with current badge", "current" in vt and await pg.locator("[data-redact]").count() >= 1, vt[-400:])
        await pg.locator("[data-redact]").first.click(); await pg.wait_for_timeout(2500)
        vt = await pg.inner_text(".viewer")
        check("redacted badge after redact", "redacted" in vt, vt[-400:])
        allrev = subprocess.run(["git", "-C", M, "rev-list", "--all"], capture_output=True, text=True).stdout.split()
        hits = subprocess.run(["git", "-C", M, "grep", "-l", "ghp_EXAMPLESECRET99", *allrev], capture_output=True, text=True).stdout
        check("secret gone from history after page redact", hits.strip() == "", hits)
        await pg.screenshot(path=SHOTS + "/versions.png", full_page=True)

        # instructions per context
        await pg.click('nav button[data-tab="repos"]'); await pg.wait_for_timeout(900)
        await pg.locator(".repo-btn", has_text="shop").first.click(); await pg.wait_for_timeout(500)
        await pg.fill("#riRepo", "Ask before touching modules/net.")
        await pg.fill("#riClient", "Small PRs with an ADR link.")
        await pg.click("#riSave"); await pg.wait_for_timeout(900)
        reg = json.load(open(M + "/engine/repos.json"))
        check("repo instructions saved from the page", reg["repos"][WEB].get("instructions") == "Ask before touching modules/net.")
        check("client instructions saved from the page", reg["clients"]["acme"].get("instructions") == "Small PRs with an ADR link.")
        check("textarea keeps the saved text", await pg.input_value("#riRepo") == "Ask before touching modules/net.")
        await pg.screenshot(path=SHOTS + "/repo-instructions.png", full_page=True)

        await pg.click('nav button[data-tab="health"]'); await pg.wait_for_timeout(500)
        ht = await pg.inner_text("main")
        check("health shows read-only and limits", "Memory read-only for agents" in ht and "Memory limits" in ht)

        # phone width
        ph = await b.new_page(viewport={"width": 390, "height": 840})
        ph.on("pageerror", lambda e: errs.append(str(e)))
        await ph.goto(BASE + "/"); await ph.wait_for_timeout(700)
        await ph.click("#runBtn"); await ph.check('input[name="shSrc"][value="pick"]'); await ph.wait_for_timeout(700)
        sw = await ph.evaluate("document.scrollingElement.scrollWidth")
        check("sheet fits a phone", sw <= 390, sw)
        await ph.screenshot(path=SHOTS + "/sheet-phone.png")
        check("no page errors", not errs, errs)
        await b.close()

asyncio.run(main())
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
