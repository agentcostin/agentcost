"""Shared test fixtures — provides a fresh SQLite database for each test."""

import pytest

from agentcost.data.sqlite_adapter import SQLiteAdapter
from agentcost.data.connection import set_db, reset_db


@pytest.fixture(autouse=True)
def fresh_test_db(tmp_path):
    """Ensure each test gets a clean database.

    This fixture runs automatically for every test. It creates a fresh
    SQLite database in a temp directory so tests don't leak state.
    """
    db_path = str(tmp_path / "test.db")
    adapter = SQLiteAdapter(db_path=db_path)
    set_db(adapter)

    # Reset all module singletons that cache DB references
    try:
        from agentcost.goals import reset_goal_service
        reset_goal_service()
    except (ImportError, AttributeError):
        pass

    try:
        from agentcost.heartbeat import reset_heartbeat_tracker
        reset_heartbeat_tracker()
    except (ImportError, AttributeError):
        pass

    try:
        from agentcost.reactions.engine import reset_reaction_engine
        reset_reaction_engine()
    except (ImportError, AttributeError):
        pass

    try:
        from agentcost.prompts import reset_prompt_service
        reset_prompt_service()
    except (ImportError, AttributeError):
        pass

    yield adapter

    reset_db()
