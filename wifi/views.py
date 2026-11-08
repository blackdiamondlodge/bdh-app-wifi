import base64
import io

import qrcode
from bdh_sdk.settings import app_setting
from django.shortcuts import render

APP_ID = "wifi"
DEFAULT_NETWORKS = "bdl_guest"


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


def _qr_png_base64(text):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def wifi_qr(request):
    # Signed-in users see the full network list; guests only the public one.
    key = "NETWORKS_AUTH" if request.user.is_authenticated else "NETWORKS_PUBLIC"

    qr_codes = []
    for ssid in _networks(key):
        password = _password(ssid)
        # Standard Wi-Fi QR format: WIFI:S:<SSID>;T:WPA;P:<password>;;
        qr_codes.append({
            "ssid": ssid,
            "qr_image": _qr_png_base64(f"WIFI:S:{ssid};T:WPA;P:{password};;"),
            "password": password,
        })

    return render(request, "wifi/wifi_qr.html", {"qr_codes": qr_codes})