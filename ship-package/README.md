# AgentCost Live Simulator — Ship Package

## What's Inside

```
ship-package/
├── dashboard/
│   └── index.html              ← Complete modified dashboard (drop-in replacement)
├── simulator.patch             ← Git patch (262 insertions, 6 deletions)
├── APPLY.sh                    ← One-command apply script
├── launch-content/
│   ├── blog-post-draft.md      ← Ready-to-publish blog post
│   ├── social-media-launch.md  ← X thread + LinkedIn + HN + YouTube
│   ├── comparison-page-updates.md ← Updates for all 4 comparison pages
│   └── launch-checklist.md     ← Full pre-launch / launch day / post-launch checklist
└── README.md
```

## How to Apply

### Option A: Git Patch (Recommended)

```bash
cd agentcost
cp /path/to/simulator.patch .
git apply simulator.patch
```

### Option B: File Replacement

```bash
cd agentcost
cp dashboard/index.html dashboard/index.html.backup
cp /path/to/ship-package/dashboard/index.html dashboard/index.html
```

### Option C: Apply Script

```bash
cd agentcost
cp /path/to/ship-package/* .
bash APPLY.sh
```

## What Changed

Single file modified: `dashboard/index.html`

| Change | Lines |
|---|---|
| SimulatorPage component + all sub-components | +200 lines |
| Simulation data (nodes, chaos events, scenarios, risk map) | +50 lines |
| NAV array: added `{section:'Tools'},{id:'simulator',...}` | +1 line |
| TITLES map: added `simulator:'Cost Simulator'` | modified |
| Tab rendering: added `{tab==='simulator'&&<SimulatorPage/>}` | +1 line |
| Nav item: added BETA badge for simulator | +1 line |
| Main header: hidden when simulator active | modified |
| Main content: padding=0, overflow=hidden for simulator | modified |
| Feedback bar: hidden when simulator active | modified |
| **Total** | **+262 lines, -6 lines** |

## Features Included

- 6-node AI agent architecture (API Gateway → Model Router → Semantic Cache → LLM Provider → Agent Runtime → Cost Database)
- 28 chaos events across 4 categories (Cost, Model, Governance, Optimizations)
- 9 preset scenarios including "Perfect Storm"
- Real-time metrics (RPS, latency, availability, cache hit rate, cost rate, budget, tokens)
- Risk badges (SPOF, COST SPIKE, RUNAWAY, etc.) with FIX buttons
- Animated connection edges with flowing particles
- Node load bars with percentage labels
- Budget progress bar with warning/critical coloring
- Speed control (0.5× to 3×) and traffic slider (10–100)
- Event log with timestamps
- Search/filter chaos events
- Zero backend dependencies — 100% client-side
