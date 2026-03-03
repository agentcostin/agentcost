# LlamaIndex Integration

Track costs for LlamaIndex queries, indexing, and retrieval.

## Installation

```bash
pip install agentcostin llama-index
```

## Basic Usage

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from agentcost.sdk.integrations import llamaindex_callback

# Create callback manager with AgentCost tracking
callback_manager = llamaindex_callback("llamaindex-project")

# Use with service context
service_context = ServiceContext.from_defaults(
    callback_manager=callback_manager
)

# Load and index documents
documents = SimpleDirectoryReader("./data").load_data()
index = VectorStoreIndex.from_documents(
    documents,
    service_context=service_context,
)

# Query — all LLM calls are tracked
query_engine = index.as_query_engine()
response = query_engine.query("What are the key findings?")
```

## What Gets Tracked

Every LLM call during indexing and querying is tracked, including embedding calls and completion calls with their associated costs.

View results: `agentcost dashboard`
