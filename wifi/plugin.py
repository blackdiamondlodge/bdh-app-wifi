from bdh_sdk import PluginSpec, Tile

spec = PluginSpec(
    id="wifi",
    app="wifi",
    urls="wifi.urls",
    tiles=(
        Tile(
            title="WiFi",
            url_name="wifi_qr",
            icon="wifi/hub/icon.svg",
            section="more",
            subtitle="Connect to the internet",
            order=10,
        ),
    ),
)
