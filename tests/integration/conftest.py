# -*- coding: utf-8 -*-
"""Containment for integration tests' global Kodi-mock mutations.

The integration test modules install their own bare ``MockXBMC`` (etc.) into
``sys.modules`` at import time for standalone running. That pollutes the
shared interpreter for any test run afterwards in the same process. This
directory-scoped autouse fixture restores the canonical mocks from the root
conftest and purges cached ``lib.*`` modules after each integration test, so
the leak cannot escape the integration directory.
"""

import sys
import pytest

from tests.conftest import _CANONICAL_KODI


@pytest.fixture(autouse=True)
def _contain_integration_mock_pollution():
    yield
    # After each integration test, restore the canonical Kodi mock objects so
    # the bare MockXBMC an integration module installed at import time cannot
    # leak into later (unit) tests. lib.* were pre-imported canonical-bound by
    # the root conftest, so no purge is needed.
    sys.modules.update(_CANONICAL_KODI)
