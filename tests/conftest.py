"""Mark tests from their directory so the two suites can be selected apart."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = item.path.parts
        if "functional" in parts:
            item.add_marker(pytest.mark.functional)
        elif "unit" in parts:
            item.add_marker(pytest.mark.unit)
