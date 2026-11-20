"""Safe, diagnosable error reporting for the web app.

An unexpected exception on a page is logged as ONE line:

    incident=7F3A2C RuntimeError at app.pages.home:render:27

i.e. only the exception CLASS, the module, function and line of the innermost frame inside app/, and a short random
incident id that the user also sees. The exception message, its arguments and local variables are never logged:
they could quote statement cells, file names, amounts or SQL values.
"""
import logging
import secrets
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
LOGGER_NAME = "alama"

log = logging.getLogger(LOGGER_NAME)
if not log.handlers:                                  # Streamlit does not configure our logger; print to stderr
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


def incident_id() -> str:
    return secrets.token_hex(3).upper()


def _module_name(filename: str) -> str:
    try:
        rel = Path(filename).resolve().relative_to(ROOT)
    except ValueError:
        return Path(filename).stem
    return ".".join(rel.with_suffix("").parts)


def app_location(exc: BaseException) -> tuple:
    """(module, function, line) of the innermost traceback frame inside app/ (or the innermost frame at all)."""
    frames = traceback.extract_tb(exc.__traceback__)
    inside = [f for f in frames if Path(f.filename).resolve().is_relative_to(APP_DIR)]
    f = (inside or frames or [None])[-1]
    if f is None:
        return "unknown", "unknown", 0
    return _module_name(f.filename), f.name, f.lineno or 0


def report(exc: BaseException) -> str:
    """Log one line for an unexpected exception (class, location, incident id only) and return the incident id."""
    iid = incident_id()
    module, func, line = app_location(exc)
    log.error("incident=%s %s at %s:%s:%d", iid, type(exc).__name__, module, func, line)
    return iid
