# TypeScript SDK Reference

## Installation

```bash
npm install @agentcost/sdk
```

## AgentCost

Main client for sending traces to the AgentCost server.

```typescript
import { AgentCost } from "@agentcost/sdk";

const ac = new AgentCost({
  project: "my-app",
  apiUrl: "http://localhost:8500",
  apiKey: "ac_live_xxx",  // optional, for enterprise
});
```

### Constructor Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `project` | `string` | `"default"` | Project name |
| `apiUrl` | `string` | `"http://localhost:8500"` | AgentCost server URL |
| `apiKey` | `string?` | `undefined` | API key (enterprise) |
| `agentId` | `string?` | `undefined` | Agent identifier |
| `sessionId` | `string?` | `undefined` | Session identifier |

### .trace(event) → Promise\<TraceResult\>

Record a trace event.

```typescript
const result = await ac.trace({
  model: "gpt-4o",
  provider: "openai",
  inputTokens: 150,
  outputTokens: 80,
  cost: 0.0035,
  latencyMs: 450,
  status: "success",
});

console.log(result.traceId); // "a1b2c3..."
```

### .traceBatch(events) → Promise\<BatchResult\>

Send multiple traces at once.

```typescript
const result = await ac.traceBatch([
  { model: "gpt-4o", inputTokens: 100, outputTokens: 50, cost: 0.002, latencyMs: 300 },
  { model: "gpt-4o-mini", inputTokens: 200, outputTokens: 80, cost: 0.0005, latencyMs: 150 },
]);

console.log(result.count); // 2
```

### .getSummary(project?) → Promise\<Summary\>

Get cost summary for a project.

```typescript
const summary = await ac.getSummary("my-app");
console.log(summary.totalCost);    // 12.34
console.log(summary.totalCalls);   // 456
```

## TraceEvent

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | `string` | ✅ | Model name |
| `provider` | `string` | — | Provider name |
| `inputTokens` | `number` | — | Input token count |
| `outputTokens` | `number` | — | Output token count |
| `cost` | `number` | — | Cost in USD |
| `latencyMs` | `number` | — | Latency in ms |
| `status` | `"success" \| "error"` | — | Call status |
| `error` | `string` | — | Error message |
| `metadata` | `Record<string, any>` | — | Custom metadata |

## Usage with Frameworks

### Express Middleware

```typescript
import express from "express";
import { AgentCost } from "@agentcost/sdk";

const app = express();
const ac = new AgentCost({ project: "api-server" });

app.use(async (req, res, next) => {
  const start = Date.now();
  // ... your LLM call
  await ac.trace({
    model: "gpt-4o",
    latencyMs: Date.now() - start,
    // ...
  });
  next();
});
```

### Next.js API Routes

```typescript
import { AgentCost } from "@agentcost/sdk";

const ac = new AgentCost({ project: "nextjs-app" });

export async function POST(req: Request) {
  const start = Date.now();
  const response = await openai.chat.completions.create({ ... });

  await ac.trace({
    model: "gpt-4o",
    inputTokens: response.usage?.prompt_tokens,
    outputTokens: response.usage?.completion_tokens,
    latencyMs: Date.now() - start,
  });

  return Response.json(response);
}
```
