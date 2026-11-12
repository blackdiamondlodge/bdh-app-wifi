import base64
import re

from bdh_sdk import is_admin
from bdh_sdk.qr import qr_svg
from bdh_sdk.settings import app_setting
from django.shortcuts import render

APP_ID = "wifi"
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")
# Characters the Wi-Fi QR format requires to be backslash-escaped.
_QR_SPECIAL = re.compile(r'([\\;,:"])')


def _qr_escape(text):
    return _QR_SPECIAL.sub(r"\\\1", text)


def _networks(key):
    """SSIDs from BDH_WIFI_<KEY> (or the legacy WIFI_<KEY>), comma separated.
    No networks are shown unless they are configured."""
    value = app_setting(APP_ID, key, "", legacy=(f"WIFI_{key}",))
    if isinstance(value, str):
        value = value.split(",")
    return [ssid.strip() for ssid in value if ssid.strip()]


def _password(ssid):
    """Password for an SSID from BDH_WIFI_PASSWORD_FOR_<SSID> (or the legacy
    WIFI_PASSWORD_FOR_<SSID>), with every non-alphanumeric character in the
    SSID replaced by "_" (e.g. "y'all guest" -> PASSWORD_FOR_Y_ALL_GUEST)."""
    key = f"PASSWORD_FOR_{_NON_ALNUM.sub('_', ssid.upper())}"
    return app_setting(APP_ID, key, "password", legacy=(f"WIFI_{key}",))


def wifi_qr(request):
    # Admins see the full network list; everyone else only the public one.
    key = "NETWORKS_AUTH" if is_admin(request) else "NETWORKS_PUBLIC"

    qr_codes = []
    for ssid in _networks(key):
        password = _password(ssid)
        # Standard Wi-Fi QR format: WIFI:S:<SSID>;T:WPA;P:<password>;;
        svg = qr_svg(f"WIFI:S:{_qr_escape(ssid)};T:WPA;P:{_qr_escape(password)};;")
        qr_codes.append({
            "ssid": ssid,
            "qr_image": base64.b64encode(svg.encode("utf-8")).decode("ascii"),
            "password": password,
        })

    return render(request, "wifi/wifi_qr.html", {"qr_codes": qr_codes})