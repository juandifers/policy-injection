"""Test hygiene for optional external tools.

Strict validation, schema linking and symcc need the `cedar` CLI (built with the `analyze` feature) and cvc5;
see README.md for the PATH and CVC5 setup. Without `cedar`, the test modules that cannot run skip with a reason,
the same way the symcc tests do, instead of failing with FileNotFoundError tracebacks. A safety net converts any
remaining `cedar`-missing failure into a skip with the same reason.
"""

from __future__ import annotations

import shutil

import pytest

from pgi.oracle.validation import ValidationUnavailable

CEDAR_REASON = "cedar CLI not on PATH (README: export PATH=\"$HOME/tools/bin:$PATH\" and CVC5)"
# Modules whose every test validates policies with the cedar CLI.
NEEDS_CEDAR = {"test_oracle", "test_scenarios", "test_citations", "test_defaults", "test_causes", "test_realizable",
               "test_mutators", "test_probe", "test_runs", "test_critic", "test_rescore", "test_snapshot"}


def _cedar_missing() -> bool:
    return shutil.which("cedar") is None


def pytest_collection_modifyitems(config, items):
    if not _cedar_missing():
        return
    mark = pytest.mark.skip(reason=CEDAR_REASON)
    for item in items:
        if item.module.__name__ in NEEDS_CEDAR:
            item.add_marker(mark)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    if not _cedar_missing():
        return
    exc = outcome.excinfo[1] if outcome.excinfo else None
    if isinstance(exc, ValidationUnavailable) or (isinstance(exc, FileNotFoundError) and "cedar" in str(exc)) \
            or (exc is not None and type(exc).__name__ == "SchemaGenError" and "cedar" in str(exc)):
        outcome.force_exception(pytest.skip.Exception(CEDAR_REASON))
