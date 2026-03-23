from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from wireman_tracker.config import BROWSER_VIRTUAL_TIME_BUDGET_MS


class BrowserUnavailableError(RuntimeError):
    """Raised when no compatible browser is available."""


COMMON_BROWSER_PATHS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]

COMMON_BROWSER_COMMANDS = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "msedge",
    "microsoft-edge",
]


def discover_browser_path(explicit_path: str | None = None) -> str:
    env_path = explicit_path or os.getenv("WIREMAN_BROWSER_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    for command in COMMON_BROWSER_COMMANDS:
        resolved = shutil.which(command)
        if resolved:
            return resolved

    for path in COMMON_BROWSER_PATHS:
        if path.exists():
            return str(path)

    raise BrowserUnavailableError(
        "No Chromium-family browser found. Set WIREMAN_BROWSER_PATH to continue."
    )


def dump_dom(
    url: str,
    browser_path: str | None = None,
    virtual_time_budget_ms: int = BROWSER_VIRTUAL_TIME_BUDGET_MS,
) -> str:
    binary = discover_browser_path(browser_path)
    with tempfile.TemporaryDirectory(prefix="wireman-browser-") as user_data_dir:
        launch_args = [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-breakpad",
            "--disable-extensions",
            "--disable-features=Translate,BackForwardCache",
            "--hide-scrollbars",
            "--mute-audio",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            f"--user-data-dir={user_data_dir}",
            f"--virtual-time-budget={virtual_time_budget_ms}",
            "--dump-dom",
            url,
        ]
        result = subprocess.run(
            launch_args,
            capture_output=True,
            timeout=120,
            check=False,
        )

    stdout = result.stdout.decode("utf-8", "ignore")
    stderr = result.stderr.decode("utf-8", "ignore")
    merged = stdout
    if "<!DOCTYPE html>" not in merged and "<html" not in merged.lower():
        merged = f"{stdout}\n{stderr}"

    doctype_index = merged.find("<!DOCTYPE html>")
    if doctype_index >= 0:
        merged = merged[doctype_index:]
    else:
        html_index = merged.lower().find("<html")
        if html_index >= 0:
            merged = merged[html_index:]

    if "<html" not in merged.lower():
        raise RuntimeError(
            f"Browser dump for {url} did not return HTML. Exit code: {result.returncode}"
        )

    return merged
