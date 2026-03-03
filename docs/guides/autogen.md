# AutoGen Integration

Track costs for AutoGen multi-agent conversations.

## Installation

```bash
pip install agentcostin pyautogen
```

## Basic Usage

```python
from autogen import AssistantAgent, UserProxyAgent
from agentcost.sdk.integrations import autogen_callback

callback = autogen_callback("autogen-project")

assistant = AssistantAgent(
    "assistant",
    llm_config={
        "model": "gpt-4o",
        "callbacks": [callback],
    },
)

user_proxy = UserProxyAgent(
    "user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=3,
)

user_proxy.initiate_chat(
    assistant,
    message="Write a Python function to calculate Fibonacci numbers.",
)
```

## What Gets Tracked

Every LLM call within the AutoGen conversation is captured with full cost attribution to the specific agent that made the call.

View results: `agentcost dashboard`
