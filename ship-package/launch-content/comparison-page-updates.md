# Comparison Page Updates

## Add this row to ALL comparison pages

Location: agentcost.in/docs/compare/langfuse.md, helicone.md, portkey.md, litellm.md

### New row to add in the feature comparison table:

```markdown
| Live Cost Simulation | ✅ Interactive chaos simulator with 28+ events | ❌ |
```

### Full context — where it fits in the table:

```markdown
| Feature | AgentCost | [Competitor] |
|---------|-----------|--------------|
| ... existing rows ... |
| Prompt Management & Versioning | ✅ | ... |
| **Live Cost Simulation** | **✅ Interactive chaos simulator with 28+ events** | **❌** |
| Pricing Database (2,600+ models) | ✅ | ... |
| ... remaining rows ... |
```

### Specific updates per page:

---

#### agentcost.in/docs/compare/langfuse.md

Add after the Prompt Management row:
```markdown
| Live Cost Simulation | ✅ Browser-based chaos simulator — inject price spikes, cache failures, runaway agents, provider outages. 28 events, 9 preset scenarios. | ❌ No simulation capability |
```

---

#### agentcost.in/docs/compare/helicone.md

Add after the Prompt Management row:
```markdown
| Live Cost Simulation | ✅ Interactive cost chaos engineering — stress-test your AI budget before production incidents. | ❌ No simulation capability |
```

---

#### agentcost.in/docs/compare/portkey.md

Add after the Prompt Management row:
```markdown
| Live Cost Simulation | ✅ Visual architecture simulator with drag-and-drop chaos events for AI cost resilience testing. | ❌ No simulation capability |
```

---

#### agentcost.in/docs/compare/litellm.md

Add after the Prompt Management row:
```markdown
| Live Cost Simulation | ✅ First-of-its-kind AI cost chaos engineering tool — simulate price shocks, outages, runaway agents. | ❌ No simulation capability |
```

---

### Also add to the "Why AgentCost?" summary section on each page:

```markdown
### Unique: Live Cost Simulation

AgentCost is the **only** AI cost governance platform with an interactive cost chaos simulator.
Model your agent architecture, inject failure scenarios (price spikes, cache failures,
runaway agents, provider outages), and validate your cost governance policies — all in your browser,
before any production incident.

[Try the simulator →](https://demo.agentcost.in)
```
