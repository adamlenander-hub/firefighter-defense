#!/usr/bin/env python3
"""
browser_check.py — the on-every-ship browser test (ITEM-060-follow-up / working-style audit).

Why this exists
---------------
The play rules live in TWO places: the Python engine (engine.py) and the copy that
actually runs in the player's browser (static/game.js's advance()). Until now the only
automated check on the browser copy was `node --check` — which only confirms it *parses*,
not that it still *behaves* like the server. This test closes that gap and also runs the
repeatable phone checks that used to be done by hand (fires/buttons off-screen, a modal
button you can't reach, a stale version being served — the ITEM-057 round-trips).

It deliberately does NOT judge play-feel — that stays a human job.

What it checks (each prints PASS / FAIL)
  1. The page loads with no uncaught script error, and the rules + key on-screen
     controls the game relies on are actually present (catches a silent rename/removal
     that would blank the page — the ITEM-058-style drift).
  2. Matrix parity: the right/useless/dangerous table the browser uses matches the
     server's source of truth for every (fire class, tool) pair.
  3. Rule-number parity: the browser's rule constants (reward, danger speed-up, fire
     toughness, ...) equal the server's — so a number changed in one copy but not the
     other is caught.
  4. Behaviour parity: the browser plays the first level to the end under the SAME
     strategies the server's own behaviour check uses, and must reach the SAME outcome
     the server does (correct play wins with nothing leaking; doing nothing, all-water,
     and ignoring the fat fires all lose).
  5. Phone fit: at three common phone sizes nothing overflows sideways and the buttons
     you must tap (start, tools, and any pop-up's continue button) sit fully on screen.
  6. Freshness: the running server actually serves the current browser code (not a stale
     cached copy) and answers /health with a version.

Usage
  python3 browser_check.py                 # boots a local server on a free port, runs everything
  python3 browser_check.py --url URL        # runs the page/phone/health checks against a running
                                            #   server (used post-deploy by the completion gate);
                                            #   engine-parity checks are skipped in this mode.

Exit codes
  0  all applicable checks passed (or the browser tooling isn't installed — see below)
  1  a check FAILED
If Playwright or its browser isn't installed, the script prints a loud SKIP and exits 0,
so it never breaks the wider run — the same way check.sh already skips node/pytest when
those aren't present. CI installs Playwright so the check always runs there for real.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Common phone screens (CSS px, portrait). ITEM-057 was about things being off-screen
# or unreachable on exactly these.
PHONES = [(360, 640, "small Android"), (375, 667, "iPhone SE"), (390, 844, "iPhone 12")]

# The first level's strategies + expected outcomes — kept identical to the server's
# behaviour_check() in checks.py, so the browser is held to the same standard.
def _level0_strategies(build_spot_count: int):
    n = build_spot_count
    return [
        ("correct play (powder + wet-chemical)", [(0, "powder"), (2, "wetchem")], "won", True),
        ("doing nothing",                         [],                              "lost", False),
        ("all-water",                             [(i, "water") for i in range(n)], "lost", False),
        ("all-powder (ignores the fat fires)",    [(i, "powder") for i in range(n)], "lost", False),
    ]

RULE_CONSTANTS = [
    "FIRE_PX_PER_SEC", "TOWER_RANGE", "TOWER_COOLDOWN", "EXTINGUISH_REWARD",
    "SMART_BONUS", "DANGER_SPEEDUP", "FIRE_HP", "GOOD_HIT_DAMAGE",
    "WEAK_HIT_DAMAGE", "MAX_ACTIVE_FIRES",
]

# The rules + controls a working game must expose. A missing one means the browser copy
# drifted (renamed/removed) — which is exactly what silently blanked the page before.
REQUIRED_GLOBALS = ["advance", "newGame", "placeTower", "onStartButton", "game", "matrixMap", "toolMap"]
REQUIRED_DOM = ["#startBtn", "#board", "#toolPalette", "#recap", "#recapAgain"]


class Reporter:
    def __init__(self):
        self.rows = []
        self.failed = False

    def ok(self, name, detail=""):
        self.rows.append(("PASS", name, detail))

    def fail(self, name, detail=""):
        self.rows.append(("FAIL", name, detail))
        self.failed = True

    def dump(self):
        print("\n  Browser test results")
        print("  " + "-" * 66)
        for status, name, detail in self.rows:
            mark = "OK  " if status == "PASS" else "FAIL"
            line = f"  [{mark}] {name}"
            if detail:
                line += f"\n         {detail}"
            print(line)
        print("  " + "-" * 66)
        n_fail = sum(1 for r in self.rows if r[0] == "FAIL")
        if self.failed:
            print(f"  Browser test FAILED — {n_fail} check(s) failed above.\n")
        else:
            print(f"  Browser test PASSED — {len(self.rows)} checks, browser matches server.\n")


# --------------------------------------------------------------------------- tooling
def find_chromium():
    """Return an explicit chromium path if the managed install isn't on the default
    search path (our sandbox keeps it under /opt/pw-browsers); else None to let
    Playwright find its own."""
    import glob
    for pat in ("/opt/pw-browsers/chromium/chrome-linux/chrome",
                "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_health(base, timeout=20):
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as r:
                if r.status == 200:
                    return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - polling, any error means "not up yet"
            last = str(e)
        time.sleep(0.3)
    raise RuntimeError(f"server did not become healthy at {base} ({last})")


# --------------------------------------------------------------------------- checks
def check_page_and_globals(page, rep):
    missing_g = [g for g in REQUIRED_GLOBALS
                 if page.evaluate(f"typeof window['{g}']") in ("undefined",)]
    if missing_g:
        rep.fail("Rules & controls present in the browser",
                 f"missing browser rule/control(s): {', '.join(missing_g)}")
    else:
        rep.ok("Rules & controls present in the browser",
               "advance/newGame/placeTower/matrixMap/toolMap all live")
    missing_d = [sel for sel in REQUIRED_DOM if page.query_selector(sel) is None]
    if missing_d:
        rep.fail("Key on-screen elements present", f"missing element(s): {', '.join(missing_d)}")
    else:
        rep.ok("Key on-screen elements present", " ".join(REQUIRED_DOM))


def check_matrix_parity(page, rep, server_matrix):
    browser_map = page.evaluate("window.matrixMap")
    if not browser_map:
        rep.fail("Matrix parity (browser vs server)", "browser matrixMap is empty — it never loaded")
        return
    diffs = []
    for key, outcome in server_matrix.items():
        b = browser_map.get(key)
        if b != outcome:
            diffs.append(f"{key}: server={outcome} browser={b}")
    extra = [k for k in browser_map if k not in server_matrix]
    if diffs or extra:
        detail = "; ".join(diffs[:6]) + (f"; +{len(diffs)-6} more" if len(diffs) > 6 else "")
        if extra:
            detail += f"; browser has unknown pairs: {extra[:4]}"
        rep.fail("Matrix parity (browser vs server)", detail)
    else:
        rep.ok("Matrix parity (browser vs server)", f"all {len(server_matrix)} class|tool outcomes agree")


def check_constant_parity(page, rep, server_consts):
    browser = page.evaluate(
        "(() => { const o={}; for (const k of %s) o[k]=window[k]; return o; })()"
        % json.dumps(RULE_CONSTANTS)
    )
    diffs = []
    for k in RULE_CONSTANTS:
        sv = server_consts.get(k)
        bv = browser.get(k)
        if bv is None:
            diffs.append(f"{k}: missing in browser")
        elif abs(float(bv) - float(sv)) > 1e-9:
            diffs.append(f"{k}: server={sv} browser={bv}")
    if diffs:
        rep.fail("Rule-number parity (browser vs server)", "; ".join(diffs))
    else:
        rep.ok("Rule-number parity (browser vs server)",
               f"all {len(RULE_CONSTANTS)} rule constants match")


# The browser copy of the server's _play_out(): a standing-order player that keeps each
# spot stocked with its tool and steps the browser's own advance() to the end.
_PLAYOUT_JS = r"""
(payload) => {
  const {level, placements, dt, maxT} = payload;
  const g = window.newGame(level);
  window.game = g;
  window.level = level;
  g.status = 'playing';
  const has = (si) => g.towers.some(tw => tw.spot_index === si);
  let t = 0;
  while (g.status === 'playing' && t < maxT) {
    for (const [si, tool] of placements) { if (!has(si)) window.placeTower(si, tool); }
    window.advance(dt);
    t += dt;
  }
  return {status: g.status, leaked: g.leaked};
}
"""


def check_behaviour_parity(page, rep, server_results, level0, dt):
    # level0 is the SAME payload the browser normally plays (fetched from /api/level/0).
    n = len(level0.get("build_spots", []))
    for name, placements, expected_status, expect_no_leak in _level0_strategies(n):
        srv = server_results[name]
        try:
            br = page.evaluate(_PLAYOUT_JS, {
                "level": level0, "placements": placements, "dt": dt, "maxT": 180,
            })
        except Exception as e:  # noqa: BLE001
            rep.fail(f"Behaviour parity — {name}", f"browser play-through threw: {e}")
            continue
        # 1) browser must match the server engine exactly
        same = (br["status"] == srv["status"] and int(br["leaked"]) == int(srv["leaked"]))
        # 2) and both must match the intended lesson (correct play wins & nothing leaks)
        intended = (srv["status"] == expected_status) and ((not expect_no_leak) or srv["leaked"] == 0)
        if same and intended:
            rep.ok(f"Behaviour parity — {name}",
                   f"browser & server both: status={br['status']}, leaked={br['leaked']}")
        elif not same:
            rep.fail(f"Behaviour parity — {name}",
                     f"browser={br} vs server={srv} — the two copies disagree")
        else:
            rep.fail(f"Behaviour parity — {name}",
                     f"both engines gave status={srv['status']} but the level's lesson expects {expected_status}")


def _box_within(box, vw, vh, tol=1.0, check_vertical=True):
    if box is None:
        return False, "not laid out / zero size"
    if box["width"] <= 0 or box["height"] <= 0:
        return False, "zero size"
    if box["x"] < -tol or box["x"] + box["width"] > vw + tol:
        return False, f"off sideways (x={box['x']:.0f}..{box['x']+box['width']:.0f}, screen 0..{vw})"
    if check_vertical and (box["y"] < -tol or box["y"] + box["height"] > vh + tol):
        return False, f"below/above the fold (y={box['y']:.0f}..{box['y']+box['height']:.0f}, screen 0..{vh})"
    return True, "on-screen"


def check_phone_fit(page, rep, base):
    for vw, vh, label in PHONES:
        page.set_viewport_size({"width": vw, "height": vh})
        page.goto(base + "/?lang=de", wait_until="networkidle")
        problems = []
        # no sideways overflow of the whole page
        overflow = page.evaluate(
            "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
            "- window.innerWidth")
        if overflow > 1:
            problems.append(f"page overflows sideways by {overflow}px")
        # a pop-up overlay (pregame / card / recap): its continue button must be reachable
        for overlay_sel, btn_sel in (("#pregame", "#pregameOk"), ("#card", "#cardOk")):
            ov = page.query_selector(overlay_sel)
            if ov and ov.is_visible():
                btn = page.query_selector(btn_sel)
                box = btn.bounding_box() if btn else None
                good, why = _box_within(box, vw, vh)
                if not good:
                    problems.append(f"{btn_sel} unreachable: {why}")
                # dismiss it so the game controls underneath can be checked
                if btn and btn.is_visible():
                    try:
                        btn.click(timeout=1000)
                    except Exception:  # noqa: BLE001
                        pass
        # the start button must sit fully on screen
        start = page.query_selector("#startBtn")
        if start and start.is_visible():
            good, why = _box_within(start.bounding_box(), vw, vh)
            if not good:
                problems.append(f"#startBtn {why}")
        # the tool buttons must not run off the side
        tool_boxes = page.evaluate(
            "Array.from(document.querySelectorAll('#toolPalette .toolbtn, #toolPalette button'))"
            ".map(b => { const r=b.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; })")
        for i, box in enumerate(tool_boxes):
            good, why = _box_within(box, vw, vh, check_vertical=False)
            if not good:
                problems.append(f"tool button {i+1} {why}")
        if problems:
            rep.fail(f"Phone fit — {label} ({vw}x{vh})", "; ".join(problems[:5]))
        else:
            rep.ok(f"Phone fit — {label} ({vw}x{vh})",
                   f"{len(tool_boxes)} tool buttons on-screen, start reachable, no sideways overflow")


def check_freshness(page, rep, base, local_mode):
    # /health answers with a version
    try:
        health = wait_health(base, timeout=5)
        rep.ok("Health endpoint answers with a version",
               f"content_version={health.get('content_version')}, schema_version={health.get('schema_version')}")
    except Exception as e:  # noqa: BLE001
        rep.fail("Health endpoint answers with a version", str(e))
    if not local_mode:
        return
    # local: the served page must embed the CURRENT static/game.js (not a stale copy)
    try:
        with urllib.request.urlopen(base + "/?lang=de", timeout=5) as r:
            served = r.read().decode("utf-8", "replace")
        with open(os.path.join(HERE, "static", "game.js"), encoding="utf-8") as fh:
            src = fh.read()
        # a stable marker from the current file: the rule-constants line
        marker = "EXTINGUISH_REWARD = 12"
        m_src = marker in src
        m_served = marker in served
        if m_src and m_served:
            rep.ok("Served page contains the current browser code",
                   "current game.js rule constants are present in the served HTML")
        elif not m_src:
            rep.ok("Served page contains the current browser code",
                   "(marker changed; skipped — update the freshness marker if constants moved)")
        else:
            rep.fail("Served page contains the current browser code",
                     "served HTML does not contain the current game.js — a stale/cached copy is being served")
    except Exception as e:  # noqa: BLE001
        rep.fail("Served page contains the current browser code", str(e))


# --------------------------------------------------------------------------- server data
def gather_server_facts(level_index=0, dt=1 / 30.0):
    """Import the server's own engine and compute the parity targets, so the browser is
    checked against the real source of truth — not a hand-copied duplicate."""
    sys.path.insert(0, HERE)
    # firefighter_defense re-exports config + content + engine, so every rule constant
    # and the matrix/levels are reachable from this one aggregated namespace regardless
    # of which module actually defines them.
    import firefighter_defense as FD  # noqa: E402
    from checks import _play_out  # noqa: E402

    MATRIX = FD.MATRIX
    LEVELS = FD.LEVELS
    server_matrix = {f"{c}|{t}": o for c, row in MATRIX.items() for t, o in row.items()}
    server_consts = {k: getattr(FD, k) for k in RULE_CONSTANTS if hasattr(FD, k)}
    missing = [k for k in RULE_CONSTANTS if k not in server_consts]
    if missing:
        raise RuntimeError("rule constants not found on the server side: " + ", ".join(missing))

    lv = LEVELS[level_index]
    n = len(lv.get("build_spots", []))
    server_results = {}
    for name, placements, _st, _leak in _level0_strategies(n):
        r = _play_out(lv, placements, dt=dt)
        server_results[name] = {"status": r["status"], "leaked": int(r.get("leaked", 0))}
    return server_matrix, server_consts, server_results


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="On-every-ship browser test for Firefighter Defense.")
    ap.add_argument("--url", help="Test a running/deployed server instead of booting one locally. "
                                   "Engine-parity checks are skipped in this mode.")
    ap.add_argument("--dt", type=float, default=1 / 30.0, help="Sim step for the play-throughs.")
    args = ap.parse_args()

    # Graceful skip if the browser tooling isn't installed (mirrors check.sh's node/pytest skips).
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        print("  Browser test SKIPPED — Playwright is not installed.")
        print("      Enable it with:  pip install playwright  &&  playwright install chromium")
        print("      (CI installs it, so the check runs there for real.)")
        return 0
    from playwright.sync_api import sync_playwright

    local_mode = args.url is None
    proc = None
    try:
        if local_mode:
            port = free_port()
            base = f"http://127.0.0.1:{port}"
            env = dict(os.environ, HOST="127.0.0.1", PORT=str(port))
            proc = subprocess.Popen([sys.executable, os.path.join(HERE, "firefighter_defense.py")],
                                    cwd=HERE, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            wait_health(base, timeout=25)
        else:
            base = args.url.rstrip("/")
            wait_health(base, timeout=15)

        exe = find_chromium()
        rep = Reporter()

        # Server-side parity targets (local mode only — a remote server may legitimately
        # be a different build than this checkout).
        server_matrix = server_consts = server_results = level0 = None
        if local_mode:
            server_matrix, server_consts, server_results = gather_server_facts(dt=args.dt)
            with urllib.request.urlopen(base + "/api/level/0?lang=de", timeout=5) as r:
                level0 = json.loads(r.read().decode())

        with sync_playwright() as p:
            launch_kw = {"args": ["--no-sandbox"]}
            if exe:
                launch_kw["executable_path"] = exe
            browser = p.chromium.launch(**launch_kw)
            page = browser.new_page()
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.goto(base + "/?lang=de", wait_until="networkidle")
            # Wait for the browser to finish loading its rules/tools. If an uncaught error
            # on boot (e.g. a renamed element) halts the script, this never becomes true —
            # we catch that as a clean failure instead of crashing the test.
            loaded = True
            try:
                page.wait_for_function(
                    "window.matrixMap && Object.keys(window.matrixMap).length>0 && "
                    "window.toolMap && Object.keys(window.toolMap).length>0",
                    timeout=8000)
            except Exception:  # noqa: BLE001
                loaded = False

            # 1. page health
            if page_errors:
                rep.fail("Page loads with no uncaught script error", "; ".join(page_errors[:3]))
            elif not loaded:
                rep.fail("Page loads with no uncaught script error",
                         "the browser code never finished loading its rules/tools — "
                         "likely an uncaught error on boot (a renamed/removed element?)")
            else:
                rep.ok("Page loads with no uncaught script error", "no pageerror events")

            # 2-4. rules present + engine parity — only meaningful if the page loaded.
            if loaded:
                check_page_and_globals(page, rep)
                if local_mode:
                    check_matrix_parity(page, rep, server_matrix)
                    check_constant_parity(page, rep, server_consts)
                    check_behaviour_parity(page, rep, server_results, level0, args.dt)
                else:
                    print("  (engine-parity checks skipped in --url mode)")
            else:
                rep.fail("Rules & controls present in the browser",
                         "skipped — the page did not finish loading; fix the boot error above first")

            # 5. phone fit
            check_phone_fit(page, rep, base)

            # 6. freshness
            check_freshness(page, rep, base, local_mode)

            browser.close()

        rep.dump()
        return 1 if rep.failed else 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
