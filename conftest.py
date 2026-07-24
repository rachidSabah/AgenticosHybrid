"""Root conftest: ensure `services/` is on sys.path for all tests."""

from __future__ import annotations

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
_services = os.path.join(_root, "services")
if _services not in sys.path:
    sys.path.insert(0, _services)
