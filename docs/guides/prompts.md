# Prompt Management & Versioning

AgentCost includes a built-in prompt management system that lets you store, version, deploy, and track the cost of your system prompts — all from the same platform that governs your LLM spending.

## Why Manage Prompts in AgentCost?

Most teams manage prompts in one of three ways: hardcoded in source code, stored in a shared Google Doc, or scattered across a prompt management tool that has no connection to cost data. The result is that when you change a prompt, you have no idea whether the new version costs more or less to run.

AgentCost solves this by connecting prompts directly to cost tracking. When you deploy V2 of your support prompt, you can see exactly how it compares to V1 in cost per call, token usage, and latency — because the traces are tagged with the prompt version automatically.

## Quick Start

### Create a prompt

```python
from agentcost.prompts import get_prompt_service

svc = get_prompt_service()

svc.create_prompt(
    "support-bot",
    project="support",
    content="You are a helpful support agent for {{product}}. Be concise and accurate.",
    description="Main support chatbot system prompt",
    tags=["support", "production"],
    model="gpt-4.1",
)
```

Or via the API:

```bash
curl -X POST http://localhost:8100/api/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "support-bot",
    "project": "support",
    "content": "You are a helpful support agent for {{product}}. Be concise and accurate.",
    "tags": ["support", "production"],
    "model": "gpt-4.1"
  }'
```

### Create a new version

Every edit creates an immutable version. Previous versions are never overwritten.

```python
svc.create_version(
    "support-bot",
    content="You are a concise support agent for {{product}}. Keep responses under 3 sentences.",
    commit_message="Shorter replies to reduce output tokens",
    author="rajneesh",
)
```

### Deploy to an environment

Deployments track which version is active in each environment. You can have V2 in staging while V1 is still running in production.

```python
svc.deploy("support-bot", version=2, environment="staging")

# After testing, promote to production
svc.deploy("support-bot", version=2, environment="production")
```

### Use in your application

```python
from agentcost.sdk import get_prompt, trace
from openai import OpenAI

# Resolve the production prompt, fill variables
prompt = get_prompt(
    "support-bot",
    environment="production",
    variables={"product": "AgentCost"}
)

# Trace with prompt version tagging — cost analytics per version
client = trace(
    OpenAI(),
    project="support",
    prompt_id=prompt["prompt_id"],
    prompt_version=prompt["version"],
)

response = client.chat.completions.create(
    model=prompt.get("model") or "gpt-4.1",
    messages=[
        {"role": "system", "content": prompt["content"]},
        {"role": "user", "content": user_message},
    ]
)
```

Every trace is now tagged with the prompt ID and version. This means you can answer questions like "did V2 of our support prompt reduce costs?" directly from the AgentCost dashboard.

## Features

### Variable Templates

Prompts support `{{variable}}` placeholders that are automatically extracted and filled at resolve time:

```python
svc.create_prompt(
    "email-writer",
    content="Write a {{tone}} email to {{recipient}} about {{topic}}.",
)

result = svc.resolve(
    "email-writer",
    variables={"tone": "professional", "recipient": "the engineering team", "topic": "Q1 costs"},
)
# → "Write a professional email to the engineering team about Q1 costs."
```

Variables are extracted automatically — no manual declaration needed.

### Version Diffing

Compare any two versions side by side:

```bash
curl "http://localhost:8100/api/prompts/support-bot/diff?v1=1&v2=3"
```

Returns a unified diff showing exactly what changed between versions:

```diff
--- v1
+++ v3
-You are a helpful support agent for {{product}}. Be concise and accurate.
+You are a concise support agent for {{product}}. Keep responses under 3 sentences. Always include a link to relevant docs.
```

### Environment-Based Deployment

Deploy different versions to different environments:

```python
svc.deploy("support-bot", version=1, environment="development")
svc.deploy("support-bot", version=2, environment="staging")
svc.deploy("support-bot", version=3, environment="production")
```

When your application calls `get_prompt("support-bot", environment="production")`, it always gets the version deployed to production — even if newer versions exist in staging.

If no deployment exists for an environment, the latest version is returned as a fallback.

### Cost Analytics Per Version

Track how much each prompt version costs to run:

```bash
# Cost stats for a specific version
curl http://localhost:8100/api/prompts/support-bot/versions/2/cost

# Compare costs between two versions
curl "http://localhost:8100/api/prompts/support-bot/cost/compare?v1=1&v2=2"
```

This requires traces to be tagged with `prompt_id` and `prompt_version` (automatic when using `get_prompt()` + `trace()`).

### Resolve by Name or ID

Prompts can be referenced by name or ID:

```python
# Both work
svc.resolve("support-bot", environment="production")
svc.resolve("a1b2c3d4e5f6", environment="production")
```

### Model Recommendations

Each prompt version can specify a recommended model:

```python
svc.create_version(
    "support-bot",
    content="...",
    model="claude-haiku-4-5",
    config={"temperature": 0.3, "max_tokens": 200},
    commit_message="Switch to Haiku for cost savings",
)
```

Your application can then use the recommended model:

```python
prompt = get_prompt("support-bot")
model = prompt.get("model") or "gpt-4.1"  # use recommended or fallback
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/prompts` | Create a prompt with first version |
| `GET` | `/api/prompts` | List all prompts (filter by project, tag) |
| `GET` | `/api/prompts/summary` | Prompt management statistics |
| `GET` | `/api/prompts/{id}` | Get prompt with latest version + deployments |
| `DELETE` | `/api/prompts/{id}` | Delete prompt and all versions |
| `POST` | `/api/prompts/{id}/versions` | Create a new version |
| `GET` | `/api/prompts/{id}/versions` | List all versions (newest first) |
| `GET` | `/api/prompts/{id}/versions/{v}` | Get specific version |
| `GET` | `/api/prompts/{id}/diff?v1=1&v2=2` | Diff two versions |
| `POST` | `/api/prompts/{id}/deploy` | Deploy version to environment |
| `GET` | `/api/prompts/{id}/deployments` | List deployments |
| `POST` | `/api/prompts/{id}/resolve` | Resolve prompt for usage |
| `GET` | `/api/prompts/{id}/versions/{v}/cost` | Cost stats for a version |
| `GET` | `/api/prompts/{id}/cost/compare?v1=1&v2=2` | Compare costs |

## Best Practices

**Name prompts descriptively.** Use names like `support-bot`, `code-reviewer-system`, `email-summarizer` — not `prompt1` or `test`.

**Write commit messages.** Every version should have a commit message explaining why the change was made. This creates an audit trail: "shortened system prompt to reduce input tokens" or "added retrieval instructions for RAG pipeline."

**Test in staging before production.** Deploy to staging, run your test suite, check cost/quality metrics, then promote to production.

**Tag traces with prompt versions.** Use `get_prompt()` + `trace(prompt_id=..., prompt_version=...)` so cost analytics are automatic. Without tagging, you can still manage prompts but won't get per-version cost comparison.

**Use variables for dynamic content.** Instead of creating separate prompts for each customer or product, use `{{variables}}` and fill them at resolve time.

**Review cost comparison after major changes.** After deploying a new version, check the cost comparison endpoint to verify the change didn't increase costs unexpectedly.
