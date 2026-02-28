"""
API test fixtures.

Adds an autouse fixture that patches get_api_key() to return None so that
all API tests run without auth enforcement by default. Tests in test_auth.py
override this per-test with their own patch() context managers.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def no_api_key():
    """Disable API key enforcement for all API tests unless overridden."""
    with patch("core.config.get_api_key", return_value=None):
        yield
