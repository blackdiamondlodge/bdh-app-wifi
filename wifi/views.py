import base64
from functools import lru_cache
from pathlib import Path

import qrcode
from bdh_sdk.settings import app_setting
from django.shortcuts import render

APP_ID = "wifi"
DEFAULT_NETWORKS = "bdl_guest"

QR_COLOR = "#0b1622"
QR_BORDER = 4  # quiet zone, in modules (the QR spec minimum)
LOGO_FRACTION = 0.26  # logo width as a share of the code width; safe with ECC level H
LOGO_FILE = Path(__file__).parent / "static" / "wifi" / "brand" / "bdl-monogram.svg"


def _networks(key):
    """SSIDs from BDH_WIFI_<KEY> (or the legacy WIFI_<KEY>), comma separated."""
    value = app_setting(APP_ID, key, DEFAULT_NETWORKS, legacy=(f"WIFI_{key}",))
    if isinstance(value, str):
        value = value.split(",")
    return [ssid.strip() for ssid in value if ssid.strip()]


def _password(ssid):
    """Password for an SSID from BDH_WIFI_PASSWORD_FOR_<SSID> (or the legacy
    WIFI_PASSWORD_FOR_<SSID>), with spaces in the SSID replaced by "_"."""
    key = f'PASSWORD_FOR_{ssid.upper().replace(" ", "_")}'
    return app_setting(APP_ID, key, "password", legacy=(f"WIFI_{key}",))


@lru_cache(maxsize=1)
def _logo_inner():
    """Contents of the monogram SVG (everything inside the root <svg>)."""
    svg = LOGO_FILE.read_text(encoding="utf-8")
    return svg[svg.index(">") + 1:svg.rindex("</svg>")]


def qr_svg(text):
    """SVG of a QR code for text: round dots, square finder patterns and the
    lodge monogram over a cleared centre. Error correction H (30%) keeps it
    scannable with the centre covered."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=QR_BORDER)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    finders = [(QR_BORDER, QR_BORDER), (QR_BORDER, n - QR_BORDER - 7), (n - QR_BORDER - 7, QR_BORDER)]

    hole = round((n - 2 * QR_BORDER) * LOGO_FRACTION) | 1  # odd, so it centres on a module
    h0 = (n - hole) // 2
    h1 = h0 + hole

    def skip(r, c):
        in_finder = any(fr <= r < fr + 7 and fc <= c < fc + 7 for fr, fc in finders)
        in_hole = h0 - 1 <= r <= h1 and h0 - 1 <= c <= h1  # plus a one-module margin
        return in_finder or in_hole

    dots = "".join(
        f'<circle cx="{c + .5}" cy="{r + .5}" r=".46"/>'
        for r, row in enumerate(matrix)
        for c, on in enumerate(row)
        if on and not skip(r, c)
    )
    # Finder patterns stay square: rounded corners break some decoders (OpenCV).
    eyes = "".join(
        f'<rect x="{c + .5}" y="{r + .5}" width="6" height="6" fill="none" stroke="{QR_COLOR}" stroke-width="1"/>'
        f'<rect x="{c + 2}" y="{r + 2}" width="3" height="3"/>'
        for r, c in finders
    )
    pad = 0.6
    size = hole + 2 - 2 * pad
    origin = h0 - 1 + pad
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="geometricPrecision">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<g fill="{QR_COLOR}">{dots}</g>'
        f'<g fill="{QR_COLOR}">{eyes}</g>'
        f'<svg x="{origin}" y="{origin}" width="{size}" height="{size}" viewBox="0 0 100 100" class="qr-logo">'
        f'{_logo_inner()}</svg></svg>'
    )


def wifi_qr(request):
    # Signed-in users see the full network list; guests only the public one.
    key = "NETWORKS_AUTH" if request.user.is_authenticated else "NETWORKS_PUBLIC"

    qr_codes = []
    for ssid in _networks(key):
        password = _password(ssid)
        # Standard Wi-Fi QR format: WIFI:S:<SSID>;T:WPA;P:<password>;;
        svg = qr_svg(f"WIFI:S:{ssid};T:WPA;P:{password};;")
        qr_codes.append({
            "ssid": ssid,
            "qr_image": base64.b64encode(svg.encode("utf-8")).decode("ascii"),
            "password": password,
        })

    return render(request, "wifi/wifi_qr.html", {"qr_codes": qr_codes})