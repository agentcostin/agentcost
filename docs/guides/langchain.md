# LangChain Integration

Track costs for every LangChain chain, agent, and tool invocation.

## Installation

```bash
pip install agentcostin langchain-openai
```

## Basic Usage

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agentcost.sdk.integrations import langchain_callback

# Create your chain as usual
llm = ChatOpenAI(model="gpt-4o-mini")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("human", "{question}"),
])
chain = prompt | llm

# Add AgentCost callback
callback = langchain_callback("my-langchain-project")

# Every invocation is tracked
result = chain.invoke(
    {"question": "What is machine learning?"},
    config={"callbacks": [callback]}
)
```

## With Agents

```python
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from agentcost.sdk.integrations import langchain_callback

llm = ChatOpenAI(model="gpt-4o")
agent = create_openai_functions_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# Track all agent LLM calls
result = executor.invoke(
    {"input": "Research AI cost trends"},
    config={"callbacks": [langchain_callback("research-agent")]}
)
```

## What Gets Tracked

The callback captures:

- Model name and provider
- Input and output tokens
- Computed cost (from AgentCost's model registry)
- Latency
- Success/error status
- Chain/agent metadata

View results in the dashboard: `agentcost dashboard`
