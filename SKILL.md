---
name: token-usage
description: Analyze daily token consumption from OpenClaw session transcripts. Use when the user asks about token usage, API costs, token breakdown, usage report, or wants to optimize token spending. Triggers on phrases like "token usage", "how many tokens", "API cost", "usage report", "token breakdown".
---

# Token Usage

Analyze token consumption from OpenClaw session JSONL transcripts with breakdowns by date, model, channel, and session.

## Quick start

```bash
python3 {baseDir}/scripts/token-usage.py
python3 {baseDir}/scripts/token-usage.py --days 30
python3 {baseDir}/scripts/token-usage.py --days 7 --detail
python3 {baseDir}/scripts/token-usage.py --days 1 --json
```

## Flags

- `--days N` — Look back N days (default: 7)
- `--detail` — Include hourly breakdown
- `--json` — Output raw JSON for programmatic use
- `--sessions-dir PATH` — Override sessions directory (default: `~/.openclaw/agents/main/sessions`)

## Report sections

1. **Grand totals** — input, output, cache read/write tokens, estimated cost, API call count
2. **By date** — daily token and cost breakdown
3. **By model** — which models consume the most tokens and cost
4. **By channel** — telegram vs webchat vs other sources
5. **By session** — top sessions ranked by cost
6. **By hour** (with `--detail`) — when tokens are consumed during the day

## Interpreting results

- **Cache write** is often the largest token category and the main cost driver for Anthropic models. Each new conversation turn writes the full context to cache.
- **Cache read** is cheap but high volume — reusing cached context across turns within the TTL window.
- **Input vs output ratio** reveals whether cost comes from large prompts (skills, system prompt, context) or verbose responses.
- **Channel breakdown** shows which interface drives the most usage.
- **Hourly breakdown** identifies peak usage windows for scheduling optimization.

## Optimization tips to share with the user

- Switch to a cheaper model (Gemini Flash) for routine tasks via heartbeat/subagent config
- Reduce heartbeat frequency during quiet hours
- Use `/compact` to trim session history before it grows large
- Disable unused skills to shrink the system prompt
- Use `contextPruning.ttl` to control cache lifetime
