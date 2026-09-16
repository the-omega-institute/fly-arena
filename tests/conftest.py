"""Explicit resource coverage for the single frozen v8 archive integration test."""
from pathlib import Path

import pytest


def pytest_collection_modifyitems(items):
    test_file = Path(__file__).with_name("test_contact_v8.py").resolve()
    inputs = test_file.parents[1] / "var/contact-v8/inputs"
    # lstat distinguishes an absent path from a broken symlink or invalid file.
    # Permission errors, partial directories and corrupt inputs must fail normally.
    try:
        inputs.lstat()
    except FileNotFoundError:
        for item in items:
            if (Path(item.path).resolve() == test_file
                    and item.name == "test_authoritative_binary_loader_rest_only"):
                item.add_marker(pytest.mark.skip(reason=(
                    "RESOURCE SKIP: entire var/contact-v8/inputs archive is absent; "
                    "authoritative binary/rest-state integration coverage needs the "
                    "frozen evidence archive. Source contracts are still tested."
                )))
