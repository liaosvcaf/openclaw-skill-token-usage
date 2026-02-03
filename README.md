# token-usage

OpenClaw skill for analyzing daily token consumption from session transcripts.

## What it does

Scans OpenClaw session JSONL files and produces token usage reports with breakdowns by:

- **Date** — daily token and cost trends
- **Model** — which models consume the most, with per-million-token cost rates for verification
- **Channel** — Telegram vs webchat vs Discord etc.
- **Session** — top sessions ranked by cost
- **Hour** — when tokens are consumed during the day (with `--detail`)

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
  Token Usage Report (2 days, 1228 API calls)
============================================================
  Input:             9.2M
  Output:          295.3K
  Cache Read:       91.7M
  Cache Write:      15.6M
  Total:           116.8M
  Est. Cost:      $144.89

--- By Date ---
Date        Input  Output  CacheRd  Total     Cost  Calls
----------  -----  ------  -------  -----  -------  -----
2026-02-01   9.2M  214.0K    70.0M  92.3M  $114.60    959
2026-02-02    318   81.3K    21.7M  24.6M   $30.29    269

--- By Model ---
Model                          Input  Output  CacheRd  CacheWr     Cost  In$/M  Out$/M  CRd$/M  CWr$/M    %  Calls
-----------------------------  -----  ------  -------  -------  -------  -----  ------  ------  ------  ---  -----
claude-opus-4-5                 1.4K  223.0K    74.5M    15.6M  $140.20  $5.00  $25.00   $0.50   $6.25  77%   1055
google/gemini-3-flash-preview   9.2M   72.3K    17.2M        0    $4.69  $0.41   $2.48   $0.04   $0.00  23%    143

--- By Channel ---
Channel    Input  Output  Total    Cost    %
--------  ------  ------  -----  ------  ---
webchat     8.8M  213.3K  83.8M  $82.64  72%
telegram  426.6K   73.7K  29.1M  $53.02  25%
other         56    8.3K   4.0M   $9.23   3%

--- By Session (top cost) ---
Session    Channel            Model   Total    Cost    %  Calls
--------  --------  ---------------  ------  ------  ---  -----
7c5fb7c8   webchat          unknown   42.9M  $44.10  37%    326
20cb8929   webchat  claude-opus-4-5   24.6M  $30.29  21%    269
f4d3c3e8   webchat  claude-opus-4-5   22.6M  $26.40  19%    190
28eafddc  telegram  claude-opus-4-5   11.1M  $23.86  10%    158
c3bd4db6   webchat  claude-opus-4-5   15.3M  $19.28  13%    266
f94aa139  telegram  claude-opus-4-5  394.9K  $0.955   0%     19
```

The **In$/M**, **Out$/M**, **CRd$/M**, and **CWr$/M** columns show the effective cost per million tokens for each category, computed from actual billing data. Use these to verify costs match your provider's published pricing.

## Requirements

- Python 3.10+
- No external dependencies

## License

MIT
