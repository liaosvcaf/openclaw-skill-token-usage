# token-usage

OpenClaw skill for analyzing daily token consumption from session transcripts.

## What it does

Scans OpenClaw session JSONL files and produces token usage reports with breakdowns by:

- **Date** — daily token and cost trends
- **Model** — which models consume the most (e.g., Opus vs Gemini Flash)
- **Channel** — Telegram vs webchat vs Discord etc.
- **Session** — top sessions ranked by cost
- **Hour** — when tokens are consumed during the day

## Install

Copy the `token-usage/` folder into your OpenClaw workspace `skills/` directory, or clone directly:

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/liaosvcaf/openclaw-skill-token-usage.git token-usage
```

## Standalone usage

```bash
python3 scripts/token-usage.py              # last 7 days
python3 scripts/token-usage.py --days 30    # last 30 days
python3 scripts/token-usage.py --detail     # include hourly breakdown
python3 scripts/token-usage.py --json       # machine-readable JSON output
```

## Example output

```
============================================================
  Token Usage Report (2 days, 1137 API calls)
============================================================
  Input:             9.2M
  Output:          258.0K
  Cache Read:       84.1M
  Cache Write:      14.9M
  Total:           108.4M
  Est. Cost:      $135.80

--- By Model ---
Model                          Input  Output  Total     Cost    %  Calls
-----------------------------  -----  ------  -----  -------  ---  -----
claude-opus-4-5                 1.3K  185.7K  81.9M  $131.11  76%    964
google/gemini-3-flash-preview   9.2M   72.3K  26.5M    $4.69  24%    143
```

## Requirements

- Python 3.10+
- No external dependencies

## License

MIT
