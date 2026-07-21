"""Shared test setup for Firefighter Defense.

Injects a minimal FastAPI stand-in when the real one isn't installed, so the module
imports and its logic runs in an offline sandbox (the web layer itself is confirmed
by actually running the app). pytest imports this before collecting the test files,
so every test_*.py can simply `import firefighter_defense as g`. Split out of the old
test_app.py (Step C)."""
import importlib
import os
import sys
import types


def _ensure_importable():
    """Let the module import even if FastAPI isn't installed here, by injecting a
    minimal stand-in. Uses the real FastAPI when it's available."""
    try:
        import fastapi  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    fake = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = _decorator
        post = _decorator
        on_event = _decorator

    def _response(content=None, *a, **k):
        return content

    fake.FastAPI = _App
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _response
    responses.JSONResponse = _response
    fake.responses = responses
    sys.modules["fastapi"] = fake
    sys.modules["fastapi.responses"] = responses


_ensure_importable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
importlib.import_module("firefighter_defense")
