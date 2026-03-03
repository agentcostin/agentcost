# CrewAI Integration

Track costs for CrewAI crews, agents, and tasks.

## Installation

```bash
pip install agentcostin crewai
```

## Basic Usage

```python
from crewai import Agent, Task, Crew
from agentcost.sdk.integrations import crewai_callback

# Define agents
researcher = Agent(
    role="Senior Researcher",
    goal="Find the latest AI cost trends",
    backstory="You are an expert in AI economics.",
)

writer = Agent(
    role="Writer",
    goal="Summarize research findings",
    backstory="You write clear, concise reports.",
)

# Define tasks
research_task = Task(
    description="Research AI infrastructure costs in 2026",
    agent=researcher,
)

write_task = Task(
    description="Write a summary of the research findings",
    agent=writer,
)

# Create crew with AgentCost tracking
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    callbacks=[crewai_callback("crewai-research")]
)

result = crew.kickoff()
```

## What Gets Tracked

Each LLM call within the crew is tracked with:

- Which agent made the call
- Task context
- Model, tokens, cost, latency
- Error status

View results in the dashboard: `agentcost dashboard`
