---
date: 2026-03-26
categories:
    - Security
    - Supply Chain
tags:
    - litellm
    - supply-chain-attack
    - dependency-management
---

# The litellm Supply Chain Attack Proves AI Cost Tools Need Fewer Dependencies, Not More

## How we built AgentCost with 4 dependencies — and why that decision matters more than ever after March 24, 2026.

_By Founder of [AgentCost](https://agentcost.in) | March 26, 2026_

---

On March 24, 2026, a routine `pip install litellm` became one of the most devastating supply chain attacks in AI infrastructure history.

For approximately three hours, versions 1.82.7 and 1.82.8 of litellm — a package downloaded 95 million times per month — silently exfiltrated SSH keys, AWS/GCP/Azure credentials, Kubernetes secrets, crypto wallets, CI/CD tokens, database passwords, and every API key stored in `.env` files. The malware didn't even need you to import litellm. Simply having it installed was enough — it executed on every Python process startup.

Andrej Karpathy called it "Software horror." Elon Musk quote-tweeted "Caveat emptor." The Hacker News thread hit 324 points. And every AI developer who read the news had the same thought: _Am I affected?_

The answer, for a terrifyingly large number of teams, was yes.

---

## What actually happened

The attack was the capstone of a coordinated campaign by a threat actor called TeamPCP. Here's the chain:

**Step 1:** TeamPCP compromised Aqua Security's Trivy — an open-source vulnerability scanner — by exploiting a GitHub Actions workflow vulnerability on March 19. They force-pushed malicious code to 75 of 76 version tags.

**Step 2:** litellm used Trivy in its own CI/CD pipeline for security scanning. When the compromised Trivy ran inside litellm's GitHub Actions workflow, TeamPCP harvested litellm's PyPI publishing token from the runner environment.

**Step 3:** With that token, they published two backdoored versions directly to PyPI, bypassing litellm's normal release process entirely.

The irony is brutal: a security scanner became the attack vector.

The payload was a three-stage weapon. Stage 1 harvested every credential it could find — SSH keys, cloud provider tokens, Kubernetes configs, environment variables, even cryptocurrency wallets. Stage 2 encrypted everything with AES-256 and exfiltrated it to `models.litellm.cloud` (a domain registered the day before, designed to look like legitimate litellm infrastructure). Stage 3 installed a persistent backdoor via systemd and, in Kubernetes environments, deployed privileged pods to every node in the cluster.

The attack was only discovered because the malware had a bug. Callum McMahon of FutureSearch was testing a Cursor MCP plugin that pulled litellm as a transitive dependency. The `.pth` file mechanism — which fires on every Python startup — created an accidental fork bomb that crashed his machine from RAM exhaustion. Without that bug, the credential stealer would have run silently for days or weeks.

As Karpathy noted: "So if the attacker didn't vibe code this attack it could have been undetected for many days or weeks."

---

## The blast radius: it's not just litellm

Here's what makes this attack catastrophic. litellm isn't just a standalone tool. It's a **transitive dependency** embedded inside the most popular AI frameworks:

- **CrewAI** depends on litellm as its default LLM router
- **DSPy** (Stanford NLP) depends on litellm>=1.64.0
- **MLflow** uses litellm for multi-provider LLM support
- **LlamaIndex** has a dedicated litellm integration package
- **Browser-Use, Opik, Mem0, Instructor, Guardrails, Agno** — all affected

If you ran `pip install crewai` or `pip install dspy` on March 24 without pinned versions, you were compromised — even though you never directly installed litellm. It arrived silently inside your dependency tree.

Projects scrambled to respond. MLflow filed PR #21971 within hours, pinning to `litellm<=1.82.6`. CrewAI went further — PR #5040 began decoupling from litellm entirely. The CVE (CVE-2026-33634) was assigned a CVSS score of 9.4.

Wiz's head of threat exposure summarized it bluntly: "The open source supply chain is collapsing in on itself. Trivy gets compromised → litellm gets compromised → credentials from tens of thousands of environments end up in attacker hands → and those credentials lead to the next compromise. We are stuck in a loop."

---

## The dependency problem in AI tooling

This attack validates something Karpathy has been saying for months. In his post, he wrote:

> "Classical software engineering would have you believe that dependencies are good (we're building pyramids from bricks), but imo this has to be re-evaluated."

He's right. And the problem is particularly acute for AI cost and observability tools. Here's why:

**AI cost tools handle the most sensitive credentials in your stack.** If your cost tracker needs to measure spending across OpenAI, Anthropic, Google, and Azure, it needs access to API keys for all of them. If that tool depends on litellm — which itself centralizes those keys through a proxy — a single supply chain compromise hands attackers every AI credential your organization possesses.

**Transitive dependencies are invisible attack surface.** Most teams don't audit what their dependencies depend on. You install a cost tracker. It depends on an LLM router. The router depends on a security scanner. The scanner gets compromised. Three layers deep, and your SSH keys are on an attacker's server.

**The AI ecosystem moves fast and pins poorly.** Unlike mature ecosystems where lockfiles and exact version pinning are standard practice, many AI projects still use loose version constraints like `litellm>=1.64.0`. During the attack window, any build or install that resolved litellm pulled the malicious version.

---

## How we built AgentCost with 4 dependencies

When I started building [AgentCost](https://github.com/agentcostin/agentcost) — an open-source AI cost governance platform — one of the earliest architectural decisions was about the dependency tree. The temptation was obvious: depend on litellm for multi-provider support, depend on LangChain for framework integrations, depend on a dozen utility libraries for convenience.

We chose the opposite path. AgentCost has **4 direct dependencies**. That's it.

Here's why, and how:

### 1. We vendor our own pricing database

AgentCost maintains a pricing database of **2,610+ models from 40+ providers**, updated weekly via a GitHub Action that syncs upstream pricing data. This data is vendored directly into the package — it ships with AgentCost, not as a runtime dependency on an external service.

Many competing tools depend on litellm's `model_cost` map for pricing data. When litellm was quarantined on PyPI on March 24 (all versions, not just the malicious ones), those tools lost access to their pricing data entirely. AgentCost's vendored database continued working normally.

### 2. We wrap provider SDKs directly

Instead of routing through a universal proxy like litellm, AgentCost's `trace()` function wraps your existing provider client:

```python
from agentcost.sdk import trace
from openai import OpenAI

client = trace(OpenAI(), project="my-app")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

The provider SDK (openai, anthropic, etc.) is _your_ dependency, not ours. AgentCost intercepts the call metadata — model, tokens, latency — without sitting in the credential path. We never see or store your API keys.

### 3. We avoid deep dependency trees

Every dependency you add is a dependency on that package's dependencies, and their dependencies, and so on. litellm alone pulls in dozens of transitive packages. Each one is a potential attack vector.

By keeping our dependency count to 4, the total transitive tree is small enough to audit manually. You can run `pip install agentcostin` and see exactly what goes into your environment.

### 4. We pin exact versions in CI

Our GitHub Actions workflows pin every dependency to exact versions with hash verification. Our Docker images are built from pinned requirements. This isn't glamorous work, but it's the difference between being compromised and not being compromised during a three-hour supply chain attack window.

---

## What you should do right now

If you're running AI workloads in production, here's your immediate checklist:

**Check if you were exposed:**

```bash
pip show litellm | grep Version
# If 1.82.7 or 1.82.8, assume full credential compromise
```

**Check transitive exposure:**

```bash
pip install pipdeptree
pipdeptree --reverse --packages litellm
# Shows every package in your environment that depends on litellm
```

**If exposed, rotate everything:**

- SSH keys
- Cloud provider credentials (AWS, GCP, Azure)
- Kubernetes configs and secrets
- All API keys in `.env` files
- Database passwords
- CI/CD tokens

**Check for persistence:**

```bash
# Local backdoor
ls -la ~/.config/sysmon/
# Kubernetes pods
kubectl get pods -n kube-system | grep node-setup
```

**For the long term:**

- Pin dependencies to exact versions (use lockfiles)
- Audit your transitive dependency tree
- Consider whether each dependency is worth the risk it introduces
- For cost tracking specifically: choose tools with minimal dependency footprints that don't sit in the credential path

---

## The bigger lesson

The litellm attack isn't really about litellm. It's about what happens when the AI ecosystem's most sensitive credentials flow through deeply embedded transitive dependencies maintained by small teams with limited security resources.

The attack chain — from a vulnerability scanner to an LLM proxy to your production credentials — illustrates a fundamental architectural problem that no amount of post-hoc scanning can fix. The fix is structural: fewer dependencies, vendored data, direct provider wrapping, and tools that stay out of the credential path.

Karpathy concluded his post by advocating for using LLMs to "yoink" functionality rather than importing heavy dependency trees. Whether or not that specific approach scales, the principle is sound: **every dependency is a trust decision, and the AI ecosystem has been making those decisions far too casually.**

We built AgentCost with 4 dependencies because we believe cost governance should be lightweight, auditable, and safe. The litellm attack proved that this isn't just a philosophical preference — it's a security imperative.

---

_[AgentCost](https://github.com/agentcostin/agentcost) is open-source (MIT), tracks 2,610+ models from 40+ providers, and ships as a single `pip install agentcostin` with 4 dependencies. Try it: [github.com/agentcostin/agentcost](https://github.com/agentcostin/agentcost) | [demo.agentcost.in](https://demo.agentcost.in)_

---

_Sources: FutureSearch (original disclosure), Snyk, Endor Labs, Wiz, The Hacker News, Andrej Karpathy (X/Twitter), DreamFactory, Arctic Wolf, SANS Institute, Cybernews. CVE-2026-33634._
