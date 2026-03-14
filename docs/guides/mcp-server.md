# MCP Server

AgentCost runs as a Model Context Protocol (MCP) server, letting Claude Desktop, Cursor, VS Code, and any MCP-compatible agent query your cost data directly. Ask "what's my spend this month?" or "which model should I switch to?" and get answers from your actual AgentCost data.

## Why MCP?

MCP is becoming the standard protocol for how AI agents interact with tools. By exposing AgentCost as an MCP server, your AI assistants can:

- Check costs before and after making LLM calls
- Get budget alerts mid-conversation
- Ask for optimization recommendations in natural language
- Resolve managed prompts on the fly
- Submit quality feedback on traces

No API calls to write, no dashboard to check — just ask your AI assistant.

## Quick Start

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentcost": {
      "command": "python",
      "args": ["-m", "agentcost.mcp"]
    }
  }
}
```

Restart Claude Desktop. You'll see AgentCost tools available. Try asking:

- "What's my total AI spend this month?"
- "Which models are costing the most in the support project?"
- "Show me the last 20 traces"
- "Set a $50 daily budget for the sales project"

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "agentcost": {
      "command": "python",
      "args": ["-m", "agentcost.mcp"]
    }
  }
}
```

### Remote Access (SSE Transport)

For shared team access, run the MCP server with SSE transport:

```bash
python -m agentcost.mcp --transport sse --port 8300
```

Then configure your MCP client to connect to `http://your-server:8300`.

### Standalone (stdio)

```bash
python -m agentcost.mcp
```

## Available Tools

AgentCost exposes 14 tools via MCP:

### Cost Analytics

| Tool | Description |
|------|-------------|
| `get_cost_summary` | Total spend, calls, tokens, model count (filter by project) |
| `get_cost_by_model` | Cost breakdown per model with calls, tokens, latency |
| `get_cost_by_project` | Cost breakdown per project |
| `list_projects` | All projects that have trace data |

### Traces

| Tool | Description |
|------|-------------|
| `search_traces` | Search recent traces, filter by project and model |
| `get_trace_count` | Total trace count per project |

### Budgets

| Tool | Description |
|------|-------------|
| `check_budget` | Budget status — spend, limits, utilization % |
| `set_budget` | Set daily and monthly budget limits for a project |

### Intelligence

| Tool | Description |
|------|-------------|
| `get_optimization_recommendations` | Model downgrade suggestions with savings estimates |
| `estimate_cost` | Pre-call cost estimation for any model + token count |

### Feedback

| Tool | Description |
|------|-------------|
| `submit_feedback` | Thumbs up/down on a trace (source tagged as "mcp") |
| `get_quality_by_model` | Quality ratings breakdown per model |

### Prompts

| Tool | Description |
|------|-------------|
| `resolve_prompt` | Get deployed prompt content with variables filled |
| `list_prompts` | All managed prompts with versions and deployments |

## Resources

The server also exposes one MCP resource:

| URI | Description |
|-----|-------------|
| `agentcost://status` | Server status, total traces, total cost, projects, feature list |

## Example Conversations

### "How much am I spending?"

```
You: What's my total AI spend?
Claude: [calls get_cost_summary]
       Your total spend across all projects is $26.40 over 1,832 calls.
       You're using 8 models across 5 projects. The average call costs $0.014.
```

### "Which model should I use?"

```
You: I'm building a support bot. Which model gives the best cost/quality ratio?
Claude: [calls get_quality_by_model, get_cost_by_model]
       Based on your data, gpt-4.1-mini has 78% positive feedback at $0.0006/call,
       while gpt-4.1 has 92% positive at $0.0034/call. The mini variant is 4x more
       cost-efficient per positive response.
```

### "Set a budget alert"

```
You: Set a $100/month budget for the research project
Claude: [calls set_budget]
       Done. Monthly budget for 'research' set to $100. You'll get alerts at 80% utilization.
```

### "Check before I call"

```
You: How much would 2000 input + 1000 output tokens cost on claude-sonnet-4-6?
Claude: [calls estimate_cost]
       That would cost approximately $0.021 — $0.006 for input and $0.015 for output.
```

## Architecture

```
  Claude Desktop / Cursor / Custom Agent
            │
            │  MCP Protocol (stdio or SSE)
            ▼
  ┌─────────────────────┐
  │  AgentCost MCP      │
  │  Server             │
  │  (14 tools)         │
  ├─────────────────────┤
  │  AgentCost Core     │
  │  ├─ EventStore      │
  │  ├─ Budgets         │
  │  ├─ Optimizer       │
  │  ├─ Feedback        │
  │  └─ Prompts         │
  ├─────────────────────┤
  │  SQLite/PostgreSQL   │
  └─────────────────────┘
```

The MCP server is a thin layer that calls the same internal services as the REST API and dashboard. No separate data store, no sync issues.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENTCOST_DB` | `~/.agentcost/benchmarks.db` | SQLite database path |
| `AGENTCOST_DATABASE_URL` | — | PostgreSQL connection string (overrides SQLite) |

The MCP server uses the same database as the API server and dashboard — all three see the same data.
