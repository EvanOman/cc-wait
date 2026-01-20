"""FastHTML dashboard server for cc-wait with integrated daemon."""

from __future__ import annotations

import argparse
import os
import sys
import threading
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fasthtml.common import (
    H1,
    H2,
    H3,
    Body,
    Div,
    Head,
    Html,
    Meta,
    P,
    Script,
    Span,
    Style,
    Title,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from cc_wait.daemon import RateLimitDaemon
from cc_wait.oauth import UsageStatus, UsageWindow, fetch_usage_status
from cc_wait.tmux import TmuxPane, find_rate_limited_panes, get_claude_panes
from cc_wait.tracing import create_span, setup_tracing

# Initialize tracing
setup_tracing()

# Global daemon instance for status access
_daemon: RateLimitDaemon | None = None

# Create FastAPI app
app = FastAPI(
    title="cc-wait Dashboard",
    description="Claude Code session monitoring dashboard",
    version="0.2.0",
    root_path=os.environ.get("ROOT_PATH", ""),
)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# CSS styles
STYLES = """
:root {
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-card: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --accent-green: #22c55e;
    --accent-yellow: #eab308;
    --accent-red: #ef4444;
    --accent-blue: #3b82f6;
    --border-color: #475569;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    padding: 2rem;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
}

.header h1 {
    font-size: 1.75rem;
    font-weight: 600;
}

.last-updated {
    color: var(--text-secondary);
    font-size: 0.875rem;
}

.usage-section {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.usage-card {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid var(--border-color);
}

.usage-card h2 {
    font-size: 1rem;
    color: var(--text-secondary);
    margin-bottom: 0.75rem;
}

.usage-value {
    font-size: 2.5rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}

.usage-value.ok { color: var(--accent-green); }
.usage-value.warning { color: var(--accent-yellow); }
.usage-value.limited { color: var(--accent-red); }

.progress-bar {
    height: 8px;
    background: var(--bg-card);
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 0.5rem;
}

.progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
}

.progress-fill.ok { background: var(--accent-green); }
.progress-fill.warning { background: var(--accent-yellow); }
.progress-fill.limited { background: var(--accent-red); }

.reset-time {
    color: var(--text-secondary);
    font-size: 0.875rem;
}

.sessions-section h2 {
    font-size: 1.25rem;
    margin-bottom: 1rem;
}

.session-count {
    color: var(--text-secondary);
    font-weight: normal;
    font-size: 1rem;
}

.sessions-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
}

.session-tile {
    background: var(--bg-secondary);
    border-radius: 10px;
    padding: 1rem;
    border: 1px solid var(--border-color);
    transition: transform 0.2s, border-color 0.2s;
}

.session-tile:hover {
    transform: translateY(-2px);
    border-color: var(--accent-blue);
}

.session-tile.rate-limited {
    border-color: var(--accent-red);
    background: linear-gradient(135deg, var(--bg-secondary), rgba(239, 68, 68, 0.1));
}

.session-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
}

.session-id {
    font-family: 'SF Mono', Monaco, monospace;
    font-size: 0.875rem;
    color: var(--accent-blue);
}

.session-status {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
    border-radius: 9999px;
    font-weight: 500;
}

.session-status.ok {
    background: rgba(34, 197, 94, 0.2);
    color: var(--accent-green);
}

.session-status.limited {
    background: rgba(239, 68, 68, 0.2);
    color: var(--accent-red);
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}

.session-name {
    font-weight: 500;
    margin-bottom: 0.25rem;
}

.session-command {
    color: var(--text-secondary);
    font-size: 0.75rem;
    font-family: 'SF Mono', Monaco, monospace;
}

.empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--text-secondary);
}

.empty-state h3 {
    font-size: 1.125rem;
    margin-bottom: 0.5rem;
}

.error-banner {
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid var(--accent-red);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
    color: var(--accent-red);
}
"""

# Auto-refresh script
REFRESH_SCRIPT = """
// Auto-refresh every 30 seconds
setTimeout(() => location.reload(), 30000);

// Show relative time
function updateTimes() {
    document.querySelectorAll('[data-timestamp]').forEach(el => {
        const ts = parseInt(el.dataset.timestamp);
        const now = Date.now();
        const diff = Math.floor((ts - now) / 1000);

        if (diff > 0) {
            const hours = Math.floor(diff / 3600);
            const mins = Math.floor((diff % 3600) / 60);
            el.textContent = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
        }
    });
}
updateTimes();
setInterval(updateTimes, 60000);
"""


def format_duration(seconds: int | None) -> str:
    """Format seconds as human-readable duration."""
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"


def get_status_class(utilization: float) -> str:
    """Get CSS class based on utilization percentage."""
    if utilization >= 100:
        return "limited"
    elif utilization >= 80:
        return "warning"
    return "ok"


def render_usage_card(title: str, window: UsageWindow) -> Div:
    """Render a usage card for a time window."""
    status_class = get_status_class(window.utilization)
    resets_in = format_duration(window.resets_in_seconds)

    return Div(
        H2(title),
        Div(f"{window.utilization:.0f}%", cls=f"usage-value {status_class}"),
        Div(
            Div(
                style=f"width: {min(window.utilization, 100)}%",
                cls=f"progress-fill {status_class}",
            ),
            cls="progress-bar",
        ),
        P(f"Resets in {resets_in}", cls="reset-time"),
        cls="usage-card",
    )


def render_session_tile(pane: TmuxPane) -> Div:
    """Render a session tile."""
    status_class = "limited" if pane.is_rate_limited else "ok"
    status_text = "Rate Limited" if pane.is_rate_limited else "Active"
    tile_class = "session-tile rate-limited" if pane.is_rate_limited else "session-tile"

    return Div(
        Div(
            Span(pane.pane_id, cls="session-id"),
            Span(
                Span(cls="status-dot"),
                status_text,
                cls=f"session-status {status_class}",
            ),
            cls="session-header",
        ),
        Div(pane.session_name, cls="session-name"),
        Div(pane.command, cls="session-command"),
        cls=tile_class,
    )


def render_dashboard(
    usage: UsageStatus | None,
    panes: list[TmuxPane],
    limited_panes: list[TmuxPane],
) -> Html:
    """Render the full dashboard."""
    now = datetime.now().strftime("%H:%M:%S")

    # Mark rate-limited panes
    limited_ids = {p.pane_id for p in limited_panes}
    for pane in panes:
        pane.is_rate_limited = pane.pane_id in limited_ids

    # Sort: limited first, then by session name
    panes.sort(key=lambda p: (not p.is_rate_limited, p.session_name))

    # Build content
    content = [
        Div(
            H1("Claude Code Sessions"),
            Span(f"Last updated: {now}", cls="last-updated"),
            cls="header",
        ),
    ]

    # Usage section
    if usage:
        content.append(
            Div(
                render_usage_card("5-Hour Usage", usage.five_hour),
                render_usage_card("Weekly Usage", usage.seven_day),
                cls="usage-section",
            )
        )
    else:
        content.append(
            Div(
                "Unable to fetch usage data. Check Claude Code credentials.",
                cls="error-banner",
            )
        )

    # Sessions section
    session_header = H2(
        "Active Sessions ",
        Span(f"({len(panes)})", cls="session-count"),
    )
    content.append(Div(session_header, cls="sessions-section"))

    if panes:
        tiles = [render_session_tile(pane) for pane in panes]
        content.append(Div(*tiles, cls="sessions-grid"))
    else:
        content.append(
            Div(
                H3("No Claude sessions found"),
                P("Start a Claude session in tmux to see it here."),
                cls="empty-state",
            )
        )

    return Html(
        Head(
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Title("cc-wait Dashboard"),
            Style(STYLES),
        ),
        Body(
            Div(*content, cls="container"),
            Script(REFRESH_SCRIPT),
        ),
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Render the dashboard."""
    with create_span("render_dashboard"):
        with create_span("fetch_usage"):
            usage = fetch_usage_status()

        with create_span("get_sessions"):
            panes = get_claude_panes()
            limited_panes = find_rate_limited_panes()

        html = render_dashboard(usage, panes, limited_panes)
        return HTMLResponse(str(html))


@app.get("/api/usage")
async def api_usage():
    """Get current usage status as JSON."""
    with create_span("api_usage"):
        usage = fetch_usage_status()
        if usage is None:
            return {"error": "Could not fetch usage"}

        return {
            "five_hour": {
                "utilization": usage.five_hour.utilization,
                "is_limited": usage.five_hour.is_limited,
                "resets_in_seconds": usage.five_hour.resets_in_seconds,
            },
            "seven_day": {
                "utilization": usage.seven_day.utilization,
                "is_limited": usage.seven_day.is_limited,
                "resets_in_seconds": usage.seven_day.resets_in_seconds,
            },
            "is_limited": usage.is_limited,
        }


@app.get("/api/sessions")
async def api_sessions():
    """Get current Claude sessions as JSON."""
    with create_span("api_sessions"):
        panes = get_claude_panes()
        limited_panes = find_rate_limited_panes()
        limited_ids = {p.pane_id for p in limited_panes}

        return {
            "total": len(panes),
            "rate_limited": len(limited_panes),
            "sessions": [
                {
                    "pane_id": p.pane_id,
                    "session_name": p.session_name,
                    "command": p.command,
                    "is_rate_limited": p.pane_id in limited_ids,
                }
                for p in panes
            ],
        }


@app.get("/health")
async def health():
    """Health check endpoint."""
    global _daemon
    return {
        "status": "healthy",
        "daemon_running": _daemon is not None,
        "waiting_for_reset": _daemon.waiting_for_reset if _daemon else False,
    }


@app.get("/api/daemon")
async def api_daemon():
    """Get daemon status."""
    global _daemon
    if _daemon is None:
        return {"error": "Daemon not running"}

    return {
        "running": True,
        "waiting_for_reset": _daemon.waiting_for_reset,
        "continued_panes": list(_daemon.continued_panes),
        "poll_interval": _daemon.poll_interval,
    }


def _run_daemon_thread():
    """Run the daemon in a background thread."""
    global _daemon
    _daemon = RateLimitDaemon()
    _daemon.run()


@app.on_event("startup")
async def startup_event():
    """Start the daemon in a background thread on server startup."""
    daemon_thread = threading.Thread(target=_run_daemon_thread, daemon=True)
    daemon_thread.start()
    print("Daemon monitoring thread started")


def main():
    """Run the dashboard server with integrated daemon."""
    parser = argparse.ArgumentParser(description="cc-wait dashboard server")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    print(f"Starting cc-wait dashboard + daemon on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    sys.exit(main() or 0)
