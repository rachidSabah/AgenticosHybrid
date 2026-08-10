"""Local QR rendering for the WhatsApp gateway.

Generates the pairing QR code on THIS machine as an SVG.  The pairing
secret (the QR string from the Baileys bridge) never leaves the host and is
never handed to an external image service.

Pure-Python: uses the ``qrcode`` package's SVG factory, which needs no
binary image dependencies (no Pillow).  If ``qrcode`` is not installed the
module degrades gracefully and callers receive an explicit error rather than
a fabricated QR.
"""

from __future__ import annotations

import io

import qrcode
from qrcode.image.svg import SvgPathImage

# SVG dimensions in millimetres — large enough to scan from a phone screen.
_BOX_SIZE = 10
_BORDER = 2


def render_qr_svg(data: str, box_size: int = _BOX_SIZE, border: int = _BORDER) -> str:
    """Render *data* (a live QR string) as an SVG document.

    Raises
    ------
    ValueError
        If *data* is empty or too large to encode.
    """
    if not data or not data.strip():
        raise ValueError("No QR data to render.")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


__all__ = ["render_qr_svg"]
