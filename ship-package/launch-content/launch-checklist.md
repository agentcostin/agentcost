# Launch Checklist — AgentCost Live Simulator

## Pre-Launch (Before shipping)

- [ ] All 16 simulator files copied into `dashboard/src/simulator/`
- [ ] NAV array updated with `{section:'Tools'},{id:'simulator',icon:'🔬',label:'Cost Simulator'}`
- [ ] Tab rendering added: `{tab==='simulator' && <SimulatorPage/>}`
- [ ] TITLES map updated with `simulator:'Cost Simulator'`
- [ ] BETA badge added to nav item
- [ ] Main content padding overridden to 0 when simulator tab is active
- [ ] Manual test: Start → inject 3 chaos events → verify metrics respond → FIX → RESET
- [ ] Manual test: Load "Perfect Storm" preset → verify all 4 events activate
- [ ] Manual test: Speed 3× + Traffic 100 → verify no lag or NaN values
- [ ] Manual test: Rapidly toggle events on/off → verify no state corruption
- [ ] Deploy to demo.agentcost.in
- [ ] Verify simulator works on demo site

## Launch Day

### Code
- [ ] Merge feature branch to main
- [ ] Tag release (e.g., v0.6.0 — Cost Simulator)
- [ ] Push Docker image with new dashboard
- [ ] Verify demo.agentcost.in is updated

### Content
- [ ] Publish blog post: "We Built a Chaos Engineering Tool for AI Costs"
- [ ] Record 60-second demo video (screen recording)
- [ ] Create GIF from demo video (for X thread)
- [ ] Upload demo video to YouTube @AgentCostIn

### Social Media
- [ ] Post X thread (7 tweets) from @agentcostin
- [ ] Post LinkedIn article
- [ ] Submit to Hacker News (Show HN)

### Documentation
- [ ] Update comparison page: agentcost.in/docs/compare/langfuse.md
- [ ] Update comparison page: agentcost.in/docs/compare/helicone.md
- [ ] Update comparison page: agentcost.in/docs/compare/portkey.md
- [ ] Update comparison page: agentcost.in/docs/compare/litellm.md
- [ ] Add "Cost Simulator" to main features list on agentcost.in homepage
- [ ] Add simulator screenshot to GitHub README

### Community
- [ ] Post in relevant GitHub Discussions (LangChain, CrewAI, LiteLLM)
- [ ] Share in relevant Discord servers
- [ ] Consider Reddit r/MachineLearning or r/LocalLLaMA

## Post-Launch (Week 1)

- [ ] Monitor demo.agentcost.in traffic (PostHog)
- [ ] Track GitHub star growth rate
- [ ] Respond to HN comments
- [ ] Respond to X replies
- [ ] Collect feedback on missing chaos events
- [ ] Plan Phase 2 based on user feedback

## Demo Video Script (60 seconds)

```
[0:00-0:05] Open demo.agentcost.in → Click "Cost Simulator" in sidebar
[0:05-0:10] Show the clean architecture: 6 nodes, connections
[0:10-0:15] Click START SIMULATION → metrics start flowing
[0:15-0:20] Drag traffic slider to 80 → show cost rate increasing
[0:20-0:30] Click "Token Price Spike (3×)" → WATCH cost rate triple instantly
             Risk badge "3× PRICE" appears on LLM node
[0:30-0:40] Click "Cache Miss Storm" → costs compound further
             "COST SPIKE" badge on Cache node
[0:40-0:50] Click "Runaway Agent" → EXTREME cost spike
             "RUNAWAY" badge, cost rate goes crazy
[0:50-0:55] Click FIX buttons → watch everything normalize
[0:55-0:60] Final shot: clean metrics, text overlay:
             "Stress-test your AI costs. demo.agentcost.in"
```
