"""Markers for specs that cannot pass yet.

planned(reason)    intended functionality that is not built. The test is an executable spec.
known_bug(reason)  built functionality that misbehaves today. The test states the correct behavior.

Both are strict xfail. They fail today. When the feature or fix lands the test passes, strict mode reports
that as a failure, and the author deletes the marker.
"""

from __future__ import annotations

import pytest


def planned(reason: str):
    def decorate(fn):
        return pytest.mark.xfail(strict=True, reason=f"PLANNED: {reason}")(
            pytest.mark.planned(fn)
        )

    return decorate


def known_bug(reason: str):
    def decorate(fn):
        return pytest.mark.xfail(strict=True, reason=f"KNOWN BUG: {reason}")(
            pytest.mark.known_bug(fn)
        )

    return decorate
