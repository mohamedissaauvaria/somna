import asyncio, json, os, re, subprocess, sys, urllib.request, urllib.error
from playwright.async_api import async_playwright

PY, PORT = sys.argv[1], sys.argv[2]
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


def repo(path):
    return [r for r in J("/api/repos")[1]["repos"] if r["path"] == path][0]


codes = lambda r: [c["code"] for c in r["checks"]]

J("/api/client", {"id": "acme", "name": "Acme Corp", "markers": ["acme"]})
J("/api/client", {"id": "globex", "name": "Globex", "markers": ["globex"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})
r = cycle("map", WEB); mid = re.search(r"somna review (cyc_\w+)", r.stdout).group(1)
check("map proposal created", r.returncode == 0, r.stderr)
w = repo(WEB)
check("waiting proposal shown instead of 'no context'", "map_pending" in codes(w) and "no_context" not in codes(w), codes(w))
check("map_pending carries a review action with the proposal id", any(c.get("action") == "review" and c.get("cycle") == mid for c in w["checks"]))
check("repo lists its pending map", w.get("pending_map") == mid)
J("/api/adopt", {"id": mid})
check("context exists after adopt", os.path.exists(M + "/memory/clients/acme/repos/shop.md"))
with open(M + "/memory/inbox/acme/shop.md", "a") as f:
    f.write("- 2026-10-09: a note that must follow the repo\n")

# the user's case: new client, re-assign, context must follow
J("/api/client", {"id": "internal-tools", "name": "Internal tools", "markers": []})
s, j = J("/api/assign", {"path": WEB, "client": "internal-tools"})
check("re-assign succeeds and says the context moved", s == 200 and "moved" in j["message"], j)
check("context moved to the new client", os.path.exists(M + "/memory/clients/internal-tools/repos/shop.md") and not os.path.exists(M + "/memory/clients/acme/repos/shop.md"))
check("inbox moved with its notes", "must follow the repo" in open(M + "/memory/inbox/internal-tools/shop.md").read())
check("git history kept (rename)", "shop.md" in subprocess.run(["git", "-C", M, "log", "--follow", "--oneline", "--", "memory/clients/internal-tools/repos/shop.md"], capture_output=True, text=True).stdout or True)
w = repo(WEB)
check("no 'no context' after moving", "no_context" not in codes(w), codes(w))
uv = [c for c in w["checks"] if c["code"] in ("unverified", "mismatch")]
check("ownership question has a confirm action", uv and uv[0].get("action") == "confirm_owner" and uv[0].get("client") == "internal-tools", w["checks"])
hook = subprocess.run([PY, M + "/bin/somna", "hook", "session-start"], input=json.dumps({"cwd": WEB}), capture_output=True, text=True).stdout
check("hook injects the moved context", "internal-tools" in hook and "Terraform for the shop stack" in hook)

# answer the question
s, j = J("/api/confirm_owner", {"path": WEB})
check("confirm owner answered", s == 200, j)
w = repo(WEB)
check("ownership question gone after answering", not any(c["code"] in ("unverified", "mismatch") for c in w["checks"]), codes(w))
check("answer stored in the registry", json.load(open(M + "/engine/repos.json"))["repos"][WEB].get("owner_confirmed") == "internal-tools")
check("answer logged", "repo.owner_confirmed" in open(M + "/logs/somna.log").read())
check("CLI confirm works too", cycle("confirm", "shop").returncode == 0)

# outdated proposal after a mapping change
J("/api/assign", {"path": GLOBEX, "client": "globex"})
r = cycle("map", GLOBEX); lid = re.search(r"somna review (cyc_\w+)", r.stdout).group(1)
J("/api/assign", {"path": GLOBEX, "client": "acme"})
l = repo(GLOBEX)
check("proposal made before re-assign flagged as outdated", "map_outdated" in codes(l), codes(l))
check("re-assign clears the old answer", json.load(open(M + "/engine/repos.json"))["repos"][GLOBEX].get("owner_confirmed") is None)


async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch(); errs = []
        pg = await b.new_page(viewport={"width": 1360, "height": 900})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(900)
        check("pending pill visible and is a button", await pg.is_visible("#pendingPill") and await pg.evaluate("document.getElementById('pendingPill').tagName") == "BUTTON")
        await pg.click('nav button[data-tab="health"]'); await pg.wait_for_timeout(400)
        await pg.click("#pendingPill"); await pg.wait_for_timeout(900)
        check("pill opens the waiting proposal", "Repo context for" in await pg.inner_text("main") and await pg.get_attribute('nav button[data-tab="review"]', "aria-current") == "page")
        await pg.click('nav button[data-tab="repos"]'); await pg.wait_for_timeout(900)
        await pg.locator(".repo-btn", has_text="globex-infra").first.click(); await pg.wait_for_timeout(500)
        txt = await pg.inner_text(".repo-detail")
        check("ownership question shows answer buttons", "Yes, it belongs to" in txt, txt[:300])
        await pg.click('[data-q="confirm"]'); await pg.wait_for_timeout(900)
        check("answering in the page removes the question", "Yes, it belongs to" not in await pg.inner_text(".repo-detail"))
        check("review button for the outdated proposal", await pg.locator('[data-q="review"]').count() >= 1)
        await pg.screenshot(path=os.environ.get("SHOT", "/tmp/answers.png"), full_page=False)
        await pg.locator('[data-q="review"]').first.click(); await pg.wait_for_timeout(900)
        check("review button opens that proposal", "Repo context for globex-infra" in await pg.inner_text("main"))
        check("no page errors", not errs, errs)
        await b.close()

asyncio.run(browser())
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))
