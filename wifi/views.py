import base64

from bdh_sdk import is_admin
from bdh_sdk.qr import qr_svg
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


def wifi_qr(request):
    # Admins see the full network list; everyone else only the public one.
    key = "NETWORKS_AUTH" if is_admin(request) else "NETWORKS_PUBLIC"

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