"""Shared test setup: makes `src/` importable and offers a cleaned toy statement."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))     # import clean, features, config, train_models, ...
sys.path.insert(0, HERE)                                # import toy

import toy  # noqa: E402


@pytest.fixture(scope="session")
def raw_vendor():
    return toy.make_vendor()


@pytest.fixture(scope="session")
def clean_vendor(raw_vendor):
    import clean
    return clean.clean(raw_vendor, as_of="2026-12-31")