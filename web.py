"""The web layer — the health check, the page assembly, and the FastAPI app.

FastAPI is imported lazily inside build_app() so importing this module never
requires the web framework (ITEM-026/027 headless-testing unlock)."""
from __future__ import annotations

import os
from functools import lru_cache
from contextlib import asynccontextmanager

from config import *
from db import *
from content import *
from levels import *

# --- Page + health content (framework-free, so it can be tested on its own) ----

def health_payload() -> dict:
    """The data behind /health — kept separate from the web layer so it can be
    checked without starting a server."""
    nc, nt = content_counts()
    return {
        "status": "ok",
        "schema_version": read_meta("schema_version"),
        "content_version": read_meta("content_version"),
        "fire_classes": nc,
        "tools": nt,
        "database": os.path.basename(DATABASE_PATH),
    }


def render_game_html(lang: str = "de") -> str:
    """The game view — a canvas that draws the current level (path, build spots,
    building, lives) with a marker travelling the path to the building. German-first
    (ITEM-001) with an in-game German→English switch, plain canvas + JavaScript
    inside the one app (ITEM-003).

    The page is assembled from three editable source files — templates/index.html
    (the markup), static/styles.css, and static/game.js — with the CSS and JS
    inlined back into the single document at the markers below. The default (German)
    served bytes are identical to the one-string version apart from the added i18n;
    the only per-language difference is the <html lang> attribute, which the browser
    uses (with localStorage 'fd_lang') to render either language with no reload."""
    html = _assemble_game_html()
    if lang == "en":
        html = html.replace('<html lang="de">', '<html lang="en">', 1)
    return html


# Where the page's source lives, resolved next to this script so it works unchanged
# on a laptop or a hosting server (uvicorn's working directory doesn't matter).
_TEMPLATE_PATH = os.path.join(HERE, "templates", "index.html")
_STYLES_PATH = os.path.join(HERE, "static", "styles.css")
_GAME_JS_PATH = os.path.join(HERE, "static", "game.js")

# Markers in templates/index.html (inside its own <style>/<script> tags) where the
# CSS and JS bodies are inlined back in. Kept in sync with how the files were split.
_STYLE_MARKER = "/*__FD_STYLES__*/"
_JS_MARKER = "//__FD_GAME_JS__"


# --- API payloads (framework-free, so the ?lang plumbing is testable without a
#     running server; the routes below are thin wrappers over these). ------------

def _norm_lang(lang: str) -> str:
    """Only 'de' (default) and 'en' are valid; anything else falls back to German."""
    return "en" if lang == "en" else "de"


def api_levels_payload(lang: str = "de") -> list:
    return levels_index(_norm_lang(lang))


def api_level_payload(index: int, lang: str = "de"):
    return level_json(index, _norm_lang(lang))


def api_classes_payload(lang: str = "de") -> list:
    return classes_display(_norm_lang(lang))


def api_tools_payload(lang: str = "de") -> list:
    return tools_display(_norm_lang(lang))


def api_anton_payload(lang: str = "de") -> dict:
    lg = _norm_lang(lang)
    return {"courage": anton_arc_de(lg), "finale": finale_de(lg)}


def api_matrix_payload(lang: str = "de") -> list:
    lg = _norm_lang(lang)
    m = load_matrix()
    return [
        {"class": c, "tool": t, "outcome": o, "reason": feedback_reason(c, t, lg)}
        for (c, t), o in m.items()
    ]


@lru_cache(maxsize=1)
def _assemble_game_html() -> str:
    """Read the page template and inline its CSS and JS into one document. Cached
    once — the source files don't change while the app runs, and the tests call
    render_game_html() many times."""
    def _read(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    html = _read(_TEMPLATE_PATH)
    html = html.replace(_STYLE_MARKER, _read(_STYLES_PATH))
    html = html.replace(_JS_MARKER, _read(_GAME_JS_PATH))
    return html


# --- Web app -----------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app):
    # The database builds itself on every start. On free hosting whose disk is
    # wiped between restarts (decided in ITEM-002), this is exactly what keeps the
    # app self-contained: nothing needs to be uploaded separately. (Uses the modern
    # "lifespan" startup hook rather than the deprecated on_event style.)
    init_db()
    yield


def build_app():
    """Create and return the FastAPI app with all its routes.

    FastAPI is imported here (not at module top level) so importing this module
    never requires the web framework — the game logic, the content check, and the
    safe-play simulator all run without it (ITEM-026/027 headless-testing unlock).
    The routes and their behaviour are identical to before; only their definition
    moved inside this function.
    """
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title=APP_TITLE, lifespan=_lifespan)

    @app.get("/health")
    def health() -> JSONResponse:
        """A tiny check a person or a hosting provider can hit to confirm it's alive."""
        return JSONResponse(health_payload())

    @app.get("/api/levels")
    def api_levels(lang: str = "de") -> JSONResponse:
        """The list of levels, for the level switcher. ?lang=de|en (default de)."""
        return JSONResponse(api_levels_payload(lang))

    @app.get("/api/level/{index}")
    def api_level(index: int, lang: str = "de") -> JSONResponse:
        """One level's map data (path, build spots, building, waves) for the browser.
        ?lang=de|en (default de)."""
        data = api_level_payload(index, lang)
        if data is None:
            return JSONResponse({"error": "no such level"}, status_code=404)
        return JSONResponse(data)

    @app.get("/api/classes")
    def api_classes(lang: str = "de") -> JSONResponse:
        """Display info per fire class (icon, colour, letter) for drawing + the legend.
        ?lang=de|en (default de)."""
        return JSONResponse(api_classes_payload(lang))

    @app.get("/api/tools")
    def api_tools(lang: str = "de") -> JSONResponse:
        """Tool palette info (name, cost, short label, colour) for placing towers.
        ?lang=de|en (default de)."""
        return JSONResponse(api_tools_payload(lang))

    @app.get("/api/anton")
    def api_anton(lang: str = "de") -> JSONResponse:
        """Anton's growth-arc courage lines and the campaign finale (ITEM-028).
        Fetched once by the browser; a fetch failure degrades gracefully there.
        ?lang=de|en (default de)."""
        return JSONResponse(api_anton_payload(lang))

    @app.get("/api/matrix")
    def api_matrix(lang: str = "de") -> JSONResponse:
        """The fire-safety matrix from the database (class × tool → outcome). The browser
        resolves each shot against this — the facts are never hard-coded in the browser.
        ?lang=de|en (default de)."""
        return JSONResponse(api_matrix_payload(lang))

    @app.get("/", response_class=HTMLResponse)
    def home(lang: str = "de") -> str:
        """The game view — draws the level map with a marker travelling the path.
        ?lang=de|en (default de) sets the initial <html lang> for the switch."""
        return render_game_html(_norm_lang(lang))

    return app

