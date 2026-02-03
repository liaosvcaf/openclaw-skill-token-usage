#!/usr/bin/env python3
"""Analyze daily token consumption from OpenClaw session transcripts.

Scans session JSONL files, extracts usage data from assistant messages,
and produces breakdowns by date, model, channel, and session.

Usage:
    python3 token-usage.py [--days N] [--detail] [--json] [--sessions-dir PATH]
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_SESSIONS_DIR = Path.home() / ".openclaw/agents/main/sessions"
# PST offset; sufficient for daily bucketing
TZ_OFFSET = timedelta(hours=-8)


def parse_args():
    days = 7
    detail = False
    as_json = False
    sessions_dir = DEFAULT_SESSIONS_DIR
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif args[i] == "--detail":
            detail = True
            i += 1
        elif args[i] == "--json":
            as_json = True
            i += 1
        elif args[i] == "--sessions-dir" and i + 1 < len(args):
            sessions_dir = Path(args[i + 1])
            i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            i += 1
    return days, detail, as_json, sessions_dir


def to_local(ts_str):
    """Parse ISO timestamp to local datetime."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt + TZ_OFFSET
    except Exception:
        return None


def scan_sessions(sessions_dir, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()
    entries = []

    if not sessions_dir.exists():
        return entries

    for f in sessions_dir.glob("*.jsonl"):
        try:
            if f.stat().st_mtime < cutoff_ts:
                continue
        except OSError:
            continue

        session_id = f.stem
        session_channel = None

        for line in open(f, errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue

            msg = d.get("message", {})
            if not isinstance(msg, dict):
                continue

            # Detect channel from user message patterns (per-message, not sticky)
            if msg.get("role") == "user":
                text = ""
                content = msg.get("content", [])
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text = c.get("text", "")
                            break
                elif isinstance(content, str):
                    text = content
                if "[Telegram" in text:
                    session_channel = "telegram"
                elif "[Discord" in text:
                    session_channel = "discord"
                elif "[Signal" in text:
                    session_channel = "signal"
                elif "[Slack" in text:
                    session_channel = "slack"
                elif "[message_id:" in text:
                    session_channel = "webchat"
                else:
                    session_channel = "other"

            if msg.get("role") != "assistant":
                continue

            usage = msg.get("usage") or d.get("usage")
            if not usage:
                continue

            ts = d.get("timestamp")
            local_dt = to_local(ts) if ts else None
            if not local_dt:
                continue

            date_str = local_dt.strftime("%Y-%m-%d")

            cost_obj = usage.get("cost", {}) or {}
            entries.append({
                "date": date_str,
                "hour": local_dt.hour,
                "model": msg.get("model", d.get("model", "unknown")),
                "provider": msg.get("provider", d.get("provider", "unknown")),
                "session_id": session_id[:8],
                "channel": session_channel or "unknown",
                "input": usage.get("input", 0) or 0,
                "output": usage.get("output", 0) or 0,
                "cache_read": usage.get("cacheRead", 0) or 0,
                "cache_write": usage.get("cacheWrite", 0) or 0,
                "total": usage.get("totalTokens", 0) or 0,
                "cost": cost_obj.get("total", 0) or 0,
                "cost_input": cost_obj.get("input", 0) or 0,
                "cost_output": cost_obj.get("output", 0) or 0,
                "cost_cache_read": cost_obj.get("cacheRead", 0) or 0,
                "cost_cache_write": cost_obj.get("cacheWrite", 0) or 0,
            })

    return entries


# ── Formatting helpers ──

def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(c):
    if c >= 1:
        return f"${c:.2f}"
    if c >= 0.01:
        return f"${c:.3f}"
    return f"${c:.4f}"


def print_table(headers, rows, alignments=None):
    if not rows:
        return
    widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        sr = [str(c) for c in row]
        str_rows.append(sr)
        for i, c in enumerate(sr):
            widths[i] = max(widths[i], len(c))
    if alignments is None:
        alignments = ["<"] + [">"] * (len(headers) - 1)
    fmt = lambda sr: "  ".join(
        f"{sr[i]:<{widths[i]}}" if alignments[i] == "<" else f"{sr[i]:>{widths[i]}}"
        for i in range(len(headers))
    )
    print(fmt(headers))
    print("  ".join("-" * w for w in widths))
    for sr in str_rows:
        print(fmt(sr))


# ── Aggregation ──

def aggregate(entries):
    agg = {
        "totals": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0, "cost": 0, "calls": 0},
        "by_date": defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0, "cost": 0, "calls": 0}),
        "by_model": defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0, "cost": 0, "cost_input": 0, "cost_output": 0, "cost_cache_read": 0, "cost_cache_write": 0, "calls": 0}),
        "by_channel": defaultdict(lambda: {"input": 0, "output": 0, "total": 0, "cost": 0, "calls": 0}),
        "by_session": defaultdict(lambda: {"input": 0, "output": 0, "total": 0, "cost": 0, "calls": 0, "channel": "?", "model": "?"}),
        "by_hour": defaultdict(lambda: {"total": 0, "calls": 0}),
    }
    t = agg["totals"]
    for e in entries:
        for key in ("input", "output", "cache_read", "cache_write", "total", "cost"):
            t[key] += e[key]
        t["calls"] += 1

        for group_key, group_field in [("by_date", "date"), ("by_model", "model"), ("by_channel", "channel"), ("by_session", "session_id")]:
            b = agg[group_key][e[group_field]]
            b["input"] += e["input"]
            b["output"] += e["output"]
            b["total"] += e["total"]
            b["cost"] += e["cost"]
            b["calls"] += 1
            if group_key in ("by_date", "by_model"):
                b["cache_read"] += e["cache_read"]
                b["cache_write"] += e["cache_write"]
            if group_key == "by_model":
                b["cost_input"] += e["cost_input"]
                b["cost_output"] += e["cost_output"]
                b["cost_cache_read"] += e["cost_cache_read"]
                b["cost_cache_write"] += e["cost_cache_write"]
            if group_key == "by_session":
                b["channel"] = e["channel"]
                b["model"] = e["model"]

        agg["by_hour"][e["hour"]]["total"] += e["total"]
        agg["by_hour"][e["hour"]]["calls"] += 1

    return agg


# ── Output ──

def report_text(agg, detail=False):
    t = agg["totals"]
    if t["calls"] == 0:
        print("No usage data found.")
        return

    num_days = len(agg["by_date"])
    print(f"\n{'=' * 60}")
    print(f"  Token Usage Report ({num_days} day{'s' if num_days != 1 else ''}, {t['calls']} API calls)")
    print(f"{'=' * 60}")
    print(f"  Input:       {fmt_tokens(t['input']):>10}")
    print(f"  Output:      {fmt_tokens(t['output']):>10}")
    print(f"  Cache Read:  {fmt_tokens(t['cache_read']):>10}")
    print(f"  Cache Write: {fmt_tokens(t['cache_write']):>10}")
    print(f"  Total:       {fmt_tokens(t['total']):>10}")
    print(f"  Est. Cost:   {fmt_cost(t['cost']):>10}")

    # By date
    print(f"\n--- By Date ---")
    rows = []
    for date in sorted(agg["by_date"]):
        b = agg["by_date"][date]
        rows.append((date, fmt_tokens(b["input"]), fmt_tokens(b["output"]),
                      fmt_tokens(b["cache_read"]), fmt_tokens(b["total"]),
                      fmt_cost(b["cost"]), b["calls"]))
    print_table(["Date", "Input", "Output", "CacheRd", "Total", "Cost", "Calls"], rows)

    # By model
    print(f"\n--- By Model ---")
    rows = []
    for model in sorted(agg["by_model"], key=lambda m: agg["by_model"][m]["total"], reverse=True):
        b = agg["by_model"][model]
        if b["total"] == 0 and b["cost"] == 0:
            continue
        pct = (b["total"] / t["total"] * 100) if t["total"] else 0
        # Compute effective $/M rates from actual cost data
        in_rate = (b["cost_input"] / b["input"] * 1_000_000) if b["input"] > 0 else 0
        out_rate = (b["cost_output"] / b["output"] * 1_000_000) if b["output"] > 0 else 0
        cr_rate = (b["cost_cache_read"] / b["cache_read"] * 1_000_000) if b["cache_read"] > 0 else 0
        cw_rate = (b["cost_cache_write"] / b["cache_write"] * 1_000_000) if b["cache_write"] > 0 else 0
        rows.append((model, fmt_tokens(b["input"]), fmt_tokens(b["output"]),
                      fmt_tokens(b["cache_read"]), fmt_tokens(b["cache_write"]),
                      fmt_cost(b["cost"]),
                      f"${in_rate:.2f}", f"${out_rate:.2f}",
                      f"${cr_rate:.2f}", f"${cw_rate:.2f}",
                      f"{pct:.0f}%", b["calls"]))
    print_table(["Model", "Input", "Output", "CacheRd", "CacheWr", "Cost",
                  "In$/M", "Out$/M", "CRd$/M", "CWr$/M", "%", "Calls"], rows)

    # By channel
    print(f"\n--- By Channel ---")
    rows = []
    for ch in sorted(agg["by_channel"], key=lambda c: agg["by_channel"][c]["total"], reverse=True):
        b = agg["by_channel"][ch]
        if b["total"] == 0 and b["cost"] == 0:
            continue
        pct = (b["total"] / t["total"] * 100) if t["total"] else 0
        rows.append((ch, fmt_tokens(b["input"]), fmt_tokens(b["output"]),
                      fmt_tokens(b["total"]), fmt_cost(b["cost"]), f"{pct:.0f}%"))
    print_table(["Channel", "Input", "Output", "Total", "Cost", "%"], rows)

    # By session
    print(f"\n--- By Session (top cost) ---")
    rows = []
    for sid in sorted(agg["by_session"], key=lambda s: agg["by_session"][s]["cost"], reverse=True):
        b = agg["by_session"][sid]
        if b["total"] == 0 and b["cost"] == 0:
            continue
        pct = (b["total"] / t["total"] * 100) if t["total"] else 0
        model_short = b["model"].split("/")[-1] if "/" in b["model"] else b["model"]
        rows.append((sid, b["channel"], model_short,
                      fmt_tokens(b["total"]), fmt_cost(b["cost"]), f"{pct:.0f}%", b["calls"]))
    print_table(["Session", "Channel", "Model", "Total", "Cost", "%", "Calls"], rows)

    # By hour
    if detail:
        print(f"\n--- By Hour (PST) ---")
        rows = []
        for h in range(24):
            b = agg["by_hour"].get(h, {"total": 0, "calls": 0})
            if b["total"] > 0:
                rows.append((f"{h:02d}:00", fmt_tokens(b["total"]), b["calls"]))
        print_table(["Hour", "Total", "Calls"], rows)

    print()


def report_json(agg):
    """Output machine-readable JSON."""
    def convert(d):
        if isinstance(d, defaultdict):
            return dict(d)
        return d

    out = {
        "totals": agg["totals"],
        "by_date": {k: dict(v) for k, v in agg["by_date"].items()},
        "by_model": {k: dict(v) for k, v in agg["by_model"].items()},
        "by_channel": {k: dict(v) for k, v in agg["by_channel"].items()},
        "by_session": {k: dict(v) for k, v in agg["by_session"].items()},
        "by_hour": {str(k): dict(v) for k, v in agg["by_hour"].items()},
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    days, detail, as_json, sessions_dir = parse_args()
    entries = scan_sessions(sessions_dir, days)
    agg = aggregate(entries)
    if as_json:
        report_json(agg)
    else:
        report_text(agg, detail)
