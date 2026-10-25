"""Account view helpers."""

import base64
from io import BytesIO


def qr_data_uri(value):
    try:
        import qrcode
        import qrcode.image.svg

        image = qrcode.make(
            value,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=8,
        )
        buffer = BytesIO()
        image.save(buffer)
        return 'data:image/svg+xml;base64,' + base64.b64encode(
            buffer.getvalue(),
        ).decode()
    except Exception:
        return None
