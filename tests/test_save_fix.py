"""Regression: cycle saves while the page is open; page must show it, editing must start from it, conflicts keep your text."""
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
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (raw.decode() if path == "/" else json.loads(raw or b"{}"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


TOKEN = re.search(r'const TOKEN = "([^"]+)"', req("/")[1]).group(1)
J = lambda path, body=None: req(path, body, TOKEN)
WEB = os.path.realpath(H + "/code/acme-shop")
J("/api/client", {"id": "acme", "name": "Acme", "markers": ["acme"]})
J("/api/assign", {"path": WEB, "client": "acme", "name": "shop"})
r = subprocess.run([PY, M + "/bin/somna", "map", WEB], capture_output=True, text=True)
J("/api/adopt", {"id": re.search(r"somna review (cyc_\w+)", r.stdout).group(1)})
F = "memory/clients/acme/repos/shop.md"
pdir = H + "/.claude/projects/" + re.sub(r"[^a-zA-Z0-9]", "-", WEB)


def new_session(sid):
    open(pdir + "/" + sid + ".jsonl", "w").write(json.dumps({"type": "user", "sessionId": sid, "cwd": WEB, "timestamp": "2026-10-12T20:00:00Z",
                                                             "message": {"role": "user", "content": "work " + sid}}) + "\n")


def cycle_saves(sid):
    new_session(sid)
    return subprocess.run([PY, M + "/bin/somna", "create", "--sessions", sid], capture_output=True, text=True, env=dict(os.environ, MOCK_TIDY="1"))


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1300, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1000)
        await pg.click('nav button[data-tab="memory"]'); await pg.wait_for_timeout(700)
        await pg.click('.files button[data-path="%s"]' % F); await pg.wait_for_timeout(500)
        o = cycle_saves("s1")
        check("cycle saved automatically on disk", "Saved automatically" in o.stdout and open(M + "/" + F).read().count("cycle acme update") == 1, o.stdout[-200:])
        await pg.wait_for_timeout(33000)
        check("open file refreshes by itself after a background save", "cycle acme update" in await pg.inner_text(".viewer"))
        cycle_saves("s2")
        await pg.click('nav button[data-tab="review"]'); await pg.wait_for_timeout(400)
        await pg.click('nav button[data-tab="memory"]'); await pg.wait_for_timeout(1000)
        check("coming back to Memory shows the latest", (await pg.inner_text(".viewer")).count("cycle acme update") == 2)
        cycle_saves("s3")
        await pg.click("#startEdit"); await pg.wait_for_timeout(600)
        check("editing starts from the latest saved version", (await pg.input_value("#editor")).count("cycle acme update") == 3)
        await pg.fill("#editor", (await pg.input_value("#editor")) + "- my manual line\n")
        await pg.click("#saveEdit"); await pg.wait_for_timeout(1200)
        check("normal save works", "my manual line" in open(M + "/" + F).read())
        # conflict: a cycle saves while you edit
        await pg.click("#startEdit"); await pg.wait_for_timeout(600)
        await pg.fill("#editor", (await pg.input_value("#editor")) + "- second manual line\n")
        cycle_saves("s4")
        await pg.click("#saveEdit"); await pg.wait_for_timeout(1200)
        t = await pg.inner_text(".viewer")
        check("conflict explained, not silently dropped", "changed while you were editing" in t, t[:300])
        check("your text is kept in the editor", "second manual line" in await pg.input_value("#editor"))
        check("nothing overwritten yet", "second manual line" not in open(M + "/" + F).read() and open(M + "/" + F).read().count("cycle acme update") == 4)
        await pg.click("#saveEdit"); await pg.wait_for_timeout(1200)
        check("second Save keeps your version", "second manual line" in open(M + "/" + F).read())
        check("editor closed after saving", await pg.locator("#editor").count() == 0)
        check("no page errors", not errs, errs)
        await b.close()

asyncio.run(main())
print("SUMMARY", "all passed" if not FAILS else "FAILED: " + ", ".join(FAILS))

# a lock left behind whose pid now belongs to another program must not block saves
sl = subprocess.Popen(["sleep", "60"])
open(M + "/cycles/.lock", "w").write(str(sl.pid))
s_, fj = J("/api/file?path=" + F)
s_, j_ = J("/api/file", {"path": F, "content": fj["content"] + "- after stale lock\n", "sha": fj["sha"]})
print(("PASS " if s_ == 200 else "FAIL ") + "stale lock from a reused pid does not block saving", j_)
sl.kill()
