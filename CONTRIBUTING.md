# Contributing to AgentCost

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/agentcostin/agentcost.git
cd agentcost

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev,server]"

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run tests
pytest tests/ -v

# Lint
ruff check agentcost/ tests/
```

## Project Structure

```
agentcost/
├── agentcost/           # Python package (MIT)
│   ├── sdk/             # Tracing SDK
│   ├── api/             # FastAPI server
│   ├── data/            # Event store (SQLite)
│   ├── forecast/        # Cost forecasting
│   ├── optimizer/       # Cost optimization
│   ├── analytics/       # Usage analytics
│   ├── estimator/       # Prompt cost estimator
│   ├── plugins/         # Plugin SDK
│   ├── auth/            # SSO/SAML (enterprise, BSL)
│   ├── org/             # Org management (enterprise, BSL)
│   ├── cost/            # Budget enforcement (enterprise, BSL)
│   ├── policy/          # Policy engine (enterprise, BSL)
│   └── notify/          # Notifications (enterprise, BSL)
├── dashboard/           # Web dashboard
├── sdks/typescript/     # TypeScript SDK
├── tests/               # Test suite
├── docs/                # MkDocs documentation
└── examples/            # Usage examples
```

## Making Changes

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/my-feature`
3. **Make changes** and add tests
4. **Run the test suite**: `pytest tests/ -v`
5. **Lint your code**: `ruff check agentcost/`
6. **Commit**: Use conventional commits (`feat:`, `fix:`, `docs:`)
7. **Push** and open a **Pull Request**

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add cost breakdown by agent` — New feature
- `fix: correct token count for streaming` — Bug fix
- `docs: update SDK reference` — Documentation
- `test: add forecaster edge case tests` — Tests
- `chore: update dependencies` — Maintenance

## Pull Request Checklist

- [ ] Tests pass (`pytest tests/ -v`)
- [ ] Linting passes (`ruff check agentcost/`)
- [ ] New features have tests
- [ ] Documentation updated if needed
- [ ] CHANGELOG.md updated

## Running the Dashboard

```bash
# Seed sample data and start server
python scripts/seed_sample_data.py --days 7
python -m agentcost dashboard
# Open http://localhost:8500
```

## Plugin Development

See the [Plugin Development Guide](https://agentcost.in/docs/guides/plugins/) for creating AgentCost plugins.

```bash
# Scaffold a new plugin
python -m agentcost plugin create my-plugin

# Test your plugin
python -m agentcost plugin test
```

## Enterprise Features

Enterprise features (auth, org, policies, etc.) are in `agentcost/{auth,org,cost,policy,notify}/` and licensed under BSL 1.1. Community contributions to enterprise features are welcome — you retain copyright of your contributions.

## Questions?

- [GitHub Discussions](https://github.com/agentcostin/agentcost/discussions) — General questions
- [Discord](https://discord.gg/agentcost) — Real-time chat
- [Issues](https://github.com/agentcostin/agentcost/issues) — Bug reports and feature requests
