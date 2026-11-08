# bdh-app-wifi

Black Diamond Hub app that shows Wi-Fi QR codes, so guests can join the
lodge network by scanning. Installed into the hub through the
`blackdiamondhub.plugins` entry point (see
[bdh-sdk](https://github.com/blackdiamondlodge/bdh-sdk)).

Page: `/wifi/` (URL name `wifi_qr`). Signed-in users see every network in
`NETWORKS_AUTH`; everyone else sees `NETWORKS_PUBLIC`.

## Settings

Read with `bdh_sdk.settings.app_setting`: the namespaced env var first, then
the legacy name.

| Setting | Legacy name | Default |
|---|---|---|
| `BDH_WIFI_NETWORKS_PUBLIC` | `WIFI_NETWORKS_PUBLIC` | `bdl_guest` (comma separated SSIDs) |
| `BDH_WIFI_NETWORKS_AUTH` | `WIFI_NETWORKS_AUTH` | `bdl_guest` |
| `BDH_WIFI_PASSWORD_FOR_<SSID>` | `WIFI_PASSWORD_FOR_<SSID>` | `password` (SSID upper-cased, spaces → `_`) |

## Development

CI (`.github/workflows/ci.yml`) uses the reusable `app-ci.yml` from bdh-sdk.
It builds the wheel, installs it next to the hub, then runs `hub_smoke`, the
app tests and the selenium tests.

To release, bump `version` in `pyproject.toml`. When that lands on `main`,
`release.yml` tags it and publishes the wheel, and the release notes include
the hashed line for the hub's `sites/<site>/apps.txt`.