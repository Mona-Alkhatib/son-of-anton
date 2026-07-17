import os

import pytest


def pytest_collection_modifyitems(config, items):
    if "ANTHROPIC_API_KEY" not in os.environ or not os.environ["ANTHROPIC_API_KEY"]:
        skip_llm = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
        for item in items:
            if "needs_llm" in item.keywords:
                item.add_marker(skip_llm)
    if "DATABASE_URL" not in os.environ:
        skip_db = pytest.mark.skip(reason="DATABASE_URL not set")
        for item in items:
            if item.get_closest_marker("integration") is not None:
                item.add_marker(skip_db)
