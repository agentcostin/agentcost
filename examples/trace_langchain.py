"""
AgentCost — LangChain Integration Example

Track costs for every LangChain chain invocation.

Usage:
    pip install agentcostin langchain-openai
    export OPENAI_API_KEY=sk-...
    python examples/trace_langchain.py
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agentcost.sdk.integrations import langchain_callback

# Create a LangChain chain
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Be concise."),
    ("human", "{question}"),
])
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
chain = prompt | llm

# AgentCost callback — tracks all LLM calls in this chain
callback = langchain_callback("langchain-demo")

# Run the chain with cost tracking
questions = [
    "What is the capital of Japan?",
    "Explain photosynthesis in one sentence.",
    "What's the speed of light?",
]

for q in questions:
    result = chain.invoke({"question": q}, config={"callbacks": [callback]})
    print(f"Q: {q}")
    print(f"A: {result.content}\n")

print("✅ All calls tracked! View in dashboard: agentcost dashboard")
