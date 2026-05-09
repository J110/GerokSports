"""Frame-aware cricket logger with file output and SSE forwarding.

Every log line includes timestamp, frame number, and component name.
Format: [09:15:23 F1234 COMPONENT] LEVEL: message

Three output destinations:
  - Console: everything (color-coded)
  - File: everything (logs/machine-1-{date}.log, rotated daily)
  - Debug UI SSE: WARN and above (real-time in browser)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_-]*)\]\s*(.*)", re.DOTALL)

_TRACE_RECORDER = None
_TRACE_KNOWN_TAGS: frozenset[str] = frozenset()
_TRACE_IMPORT_ATTEMPTED = False


def _get_trace_recorder():
    global _TRACE_RECORDER, _TRACE_KNOWN_TAGS, _TRACE_IMPORT_ATTEMPTED
    if _TRACE_RECORDER is not None:
        return _TRACE_RECORDER
    if _TRACE_IMPORT_ATTEMPTED:
        return None
    _TRACE_IMPORT_ATTEMPTED = True
    try:
        import trace_emitter
        _TRACE_RECORDER = trace_emitter.get_recorder()
        _TRACE_KNOWN_TAGS = frozenset(trace_emitter.KNOWN_TAGS)
    except Exception:
        _TRACE_RECORDER = None
    return _TRACE_RECORDER

# ANSI color codes for console output
_COLORS = {
    "INFO": "\033[37m",      # white
    "WARN": "\033[33m",      # yellow
    "ERROR": "\033[31m",     # red
    "INSIGHT": "\033[93m",   # bright yellow / gold
    "RESET": "\033[0m",
}

# Global frame counter shared across all loggers
_global_frame: int = 0

# SSE callback — set by debug_server at startup
_sse_callback = None


def set_global_frame(n: int):
    global _global_frame
    _global_frame = n


def get_global_frame() -> int:
    return _global_frame


def set_sse_callback(callback):
    """Register the SSE emit function from DebugUI so logs can stream to browser."""
    global _sse_callback
    _sse_callback = callback


def _time_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit_to_sse(component: str, level: str, message: str, frame: int):
    """Forward WARN+ logs to the debug UI via SSE."""
    if _sse_callback is None:
        return
    if level not in ("WARN", "ERROR", "INSIGHT"):
        return
    try:
        data = {
            "component": component,
            "level": level,
            "message": message,
            "frame": frame,
            "time": _time_str(),
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_sse_callback("log", data))
    except Exception:
        pass


# File handler — shared across all CricketLoggers
_file_handler: logging.FileHandler | None = None


def _ensure_file_handler() -> logging.FileHandler:
    global _file_handler
    if _file_handler is not None:
        return _file_handler

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = log_dir / f"machine-1-{date_str}.log"

    _file_handler = TimedRotatingFileHandler(
        str(path), when="midnight", backupCount=7, encoding="utf-8"
    )
    _file_handler.setFormatter(logging.Formatter("%(message)s"))
    _file_handler.setLevel(logging.DEBUG)
    return _file_handler


class CricketLogger:
    """Per-component logger with frame tracking.

    Usage:
        log = CricketLogger("LLM")
        log.info("Response in 2.3s, frame_type=live_play")
        log.warn("Consensus override: score [79, 73, 79] → 79")
        log.error("Timeout after 15s — skipping frame")
        log.insight("KHALEEL run-up 15% shorter since over 1")
    """

    def __init__(self, component: str):
        self.component = component
        self._frame: int | None = None  # per-instance override, else global

    def set_frame(self, n: int):
        self._frame = n

    @property
    def frame(self) -> int:
        return self._frame if self._frame is not None else _global_frame

    def info(self, msg: str):
        self._log("INFO", msg)

    def warn(self, msg: str):
        self._log("WARN", msg)

    def error(self, msg: str):
        self._log("ERROR", msg)

    def insight(self, msg: str):
        self._log("INSIGHT", msg)

    def debug(self, msg: str):
        """Structured debug via stdlib (no CricketLogger console line)."""
        logging.getLogger(self.component).debug(msg)

    def _log(self, level: str, msg: str):
        ts = _time_str()
        f = self.frame
        line = f"[{ts} F{f} {self.component}] {level}: {msg}"

        # Console (color-coded)
        color = _COLORS.get(level, "")
        reset = _COLORS["RESET"]
        print(f"{color}{line}{reset}")

        # File
        try:
            handler = _ensure_file_handler()
            record = logging.LogRecord(
                name=self.component, level=logging.INFO,
                pathname="", lineno=0, msg=line, args=(), exc_info=None,
            )
            handler.emit(record)
        except Exception:
            pass

        # SSE (WARN+ only)
        _emit_to_sse(self.component, level, msg, f)

        # Trace recorder auto-promotion: mirror DecisionLogHandler behavior
        # for [TAG]-prefixed lines so trace records capture decisions
        # emitted via CricketLogger (which bypasses the stdlib logging tree).
        m = _TAG_RE.search(msg)
        if m is not None:
            recorder = _get_trace_recorder()
            if recorder is not None:
                tag = m.group(1)
                try:
                    recorder.record(
                        tag=tag,
                        raw_message=msg[:200],
                        log_level=level,
                        logger=self.component,
                        known=tag in _TRACE_KNOWN_TAGS,
                        _auto=True,
                    )
                except Exception:
                    pass
