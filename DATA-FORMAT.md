# Data Source & Format

## Overview

This skill reads **session transcript files** stored by OpenClaw at:

```
~/.openclaw/agents/main/sessions/<session-id>.jsonl
```

Each file is a newline-delimited JSON (JSONL) log of a single conversation session. Every line is a self-contained JSON object representing one event: a message, a model change, a cache event, etc.

The script only extracts **assistant messages with `usage` data** — these are the API responses from the model provider, which include exact token counts and cost breakdowns.

## File location

```
~/.openclaw/
└── agents/
    └── main/
        └── sessions/
            ├── a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl
            ├── f9e8d7c6-b5a4-3210-fedc-ba0987654321.jsonl
            └── ...
```

Each `.jsonl` file corresponds to one session. Sessions are created when the agent starts a new conversation context (e.g., after a restart, compaction, or new channel pairing).

## JSONL entry types

Each line has a `type` field. The main types are:

| Type | Description |
|------|-------------|
| `session` | Session metadata (ID, version, working directory) |
| `model_change` | Model/provider switch event |
| `thinking_level_change` | Thinking level adjustment |
| `custom` | OpenClaw internal events (cache-ttl, model-snapshot) |
| `message` | User, assistant, or tool result messages |

**This script only reads `message` entries where `message.role == "assistant"` and `message.usage` is present.**

## Entry examples (anonymized)

### Session header

The first line of every transcript:

```json
{
  "type": "session",
  "version": 3,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2026-02-01T08:00:00.000Z",
  "cwd": "/home/user/.openclaw/workspace"
}
```

### User message

```json
{
  "type": "message",
  "id": "msg_001",
  "parentId": "prev_001",
  "timestamp": "2026-02-01T08:00:01.000Z",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "[Telegram Alice id:1234567890 2026-02-01 00:00 PST] What is the weather today?\n[message_id: 42]"
      }
    ],
    "timestamp": 1738368001000
  }
}
```

The channel source is embedded in the text prefix (e.g., `[Telegram ...`). The script detects this pattern to categorize usage by channel.

### Assistant message (text-only response)

```json
{
  "type": "message",
  "id": "msg_002",
  "parentId": "msg_001",
  "timestamp": "2026-02-01T08:00:03.000Z",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "Currently 52°F and cloudy in your area."
      }
    ],
    "api": "anthropic-messages",
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "usage": {
      "input": 3,
      "output": 14,
      "cacheRead": 0,
      "cacheWrite": 17605,
      "totalTokens": 17622,
      "cost": {
        "input": 0.000015,
        "output": 0.00035,
        "cacheRead": 0.0,
        "cacheWrite": 0.110031,
        "total": 0.110396
      }
    },
    "stopReason": "stop",
    "timestamp": 1738368003000
  }
}
```

### Assistant message (with tool calls)

When the agent invokes tools (exec, browser, web_search, etc.), the response contains `toolCall` content blocks alongside text/thinking:

```json
{
  "type": "message",
  "id": "msg_003",
  "parentId": "msg_002",
  "timestamp": "2026-02-01T08:01:00.000Z",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "thinking",
        "thinking": "(internal reasoning about how to approach the task)",
        "text": "..."
      },
      {
        "type": "toolCall",
        "id": "toolu_abc123",
        "name": "exec",
        "arguments": {
          "command": "curl -s wttr.in/Portland?format=3"
        },
        "input": {}
      },
      {
        "type": "toolCall",
        "id": "toolu_def456",
        "name": "web_search",
        "arguments": {
          "query": "Portland weather forecast"
        },
        "input": {}
      }
    ],
    "api": "anthropic-messages",
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "usage": {
      "input": 3,
      "output": 193,
      "cacheRead": 7191,
      "cacheWrite": 10483,
      "totalTokens": 17870,
      "cost": {
        "input": 0.000015,
        "output": 0.004825,
        "cacheRead": 0.003595,
        "cacheWrite": 0.065519,
        "total": 0.073954
      }
    },
    "stopReason": "toolUse",
    "timestamp": 1738368060000
  }
}
```

### Tool result message

After tool execution, OpenClaw records the result:

```json
{
  "type": "message",
  "id": "msg_004",
  "parentId": "msg_003",
  "timestamp": "2026-02-01T08:01:05.000Z",
  "message": {
    "role": "toolResult",
    "toolCallId": "toolu_abc123",
    "content": "Portland: ⛅ +11°C",
    "timestamp": 1738368065000
  }
}
```

Tool result messages do not contain `usage` data — token costs are attributed to the subsequent assistant response that consumes the tool result.

### Model change event

```json
{
  "type": "model_change",
  "id": "evt_001",
  "parentId": null,
  "timestamp": "2026-02-01T08:00:00.000Z",
  "provider": "anthropic",
  "modelId": "claude-opus-4-5"
}
```

## Usage fields reference

The `message.usage` object on assistant messages contains:

| Field | Type | Description |
|-------|------|-------------|
| `input` | number | New input tokens sent (excluding cache) |
| `output` | number | Output tokens generated by the model |
| `cacheRead` | number | Tokens read from prompt cache (cheap) |
| `cacheWrite` | number | Tokens written to prompt cache (expensive, ~same as input pricing) |
| `totalTokens` | number | Sum of all token categories |

The `message.usage.cost` sub-object contains:

| Field | Type | Description |
|-------|------|-------------|
| `input` | number | Cost in USD for new input tokens |
| `output` | number | Cost in USD for output tokens |
| `cacheRead` | number | Cost in USD for cache read tokens |
| `cacheWrite` | number | Cost in USD for cache write tokens |
| `total` | number | Total cost in USD for this API call |

Costs are computed by OpenClaw using the model's configured pricing. For models with zero-cost pricing (e.g., Gemini Flash via OpenRouter free tier), all cost fields will be `0`.

## What the script extracts

For each assistant message with usage data, the script records:

- **date** — local date (PST) derived from `timestamp`
- **hour** — local hour for hourly breakdown
- **model** — from `message.model` (e.g., `claude-opus-4-5`)
- **provider** — from `message.provider` (e.g., `anthropic`, `openrouter`)
- **session_id** — first 8 chars of the JSONL filename
- **channel** — detected from user message text patterns (`[Telegram`, `[Discord`, etc.)
- **token counts** — input, output, cacheRead, cacheWrite, totalTokens
- **cost** — `usage.cost.total`
