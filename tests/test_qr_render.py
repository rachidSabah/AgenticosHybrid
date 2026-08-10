"""Tests for the local WhatsApp QR renderer.

The pairing QR must be rendered on this machine (never sent to an external
image service) and must be a *live* render of the current QR string.
"""

from __future__ import annotations

import pytest

from agentic_os.adapters.gateway.qr_render import render_qr_svg


def test_render_qr_svg_returns_svg_document():
    svg = render_qr_svg("2@0live-qr-content")
    assert svg.startswith("<?xml") or svg.startswith("<svg")
    assert "<svg" in svg
    assert "path" in svg  # SvgPathImage emits <path> elements


def test_render_qr_is_deterministic_for_same_input():
    a = render_qr_svg("same-content")
    b = render_qr_svg("same-content")
    assert a == b


def test_render_qr_differs_for_different_input():
    a = render_qr_svg("content-a")
    b = render_qr_svg("content-b")
    assert a != b


def test_render_qr_empty_raises():
    with pytest.raises(ValueError):
        render_qr_svg("")


def test_render_qr_whitespace_raises():
    with pytest.raises(ValueError):
        render_qr_svg("   ")
