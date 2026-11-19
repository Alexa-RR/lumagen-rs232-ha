<img src="assets/icon.svg" width="64" height="64" alt="">

# Lumagen RS-232 for Home Assistant

A custom integration that controls a Lumagen Radiance Pro video processor over
its RS-232 port, built on [serialx](https://github.com/puddly/serialx). Protocol
reference: [Lumagen Tech Tip 11](https://static1.squarespace.com/static/67b8d70190034365ac65203b/t/6845003aca9ed36c58812065/1749352506798/Tip0011_RS232CommandInterface_111023.pdf).

Requires Home Assistant 2026.10 or newer.

## Connecting the processor

Use a **null-modem** cable from the Radiance's DB9 port to a USB-to-RS-232
adapter. When you add the integration, Home Assistant asks for one thing, the
**serial port**. It works like the built-in *LG TV via Serial* integration:

- **USB adapter on the Home Assistant host:** pick it from the list.
- **Network serial bridge:** choose **Enter manually** and type its URL,
  `socket://<host>:<port>` for raw TCP or `rfc2217://<host>:<port>` for RFC 2217.

The processor must be on (not in standby) while you add it. If the port opens
but the Lumagen doesn't answer, a troubleshooting page lists what to check, and
**Submit** tries again.

### Network bridge (Raspberry Pi + ser2net)

Plug the adapter into a wired Raspberry Pi near the Lumagen and share the port
with [ser2net](https://github.com/cminyard/ser2net) (`sudo apt install ser2net`).
`/etc/ser2net.yaml`:

```yaml
connection: &lumagen
  accepter: tcp,2000
  enable: on
  options:
    kickolduser: true
  connector: serialdev,/dev/serial/by-id/<your-adapter>,9600n81,local
```

Restart ser2net (`sudo systemctl restart ser2net`), then enter
`socket://<pi-address>:2000` as the serial port.

For **RFC 2217** instead, use `accepter: telnet(rfc2217),tcp,2000` and
`rfc2217://<pi-address>:2000`. Home Assistant then sets the port settings
itself.

`kickolduser` lets Home Assistant take the port back after a reconnect. It also
means only one client can use the bridge at a time.

To move between USB and the Pi later, use **Reconfigure** on the integration.

## Radiance settings

Leave these at their defaults (MENU → Other → I/O Setup → RS-232 Setup):

- **Delimiters: Off.** The integration does not use the `#...<CR>` framing.
- **Echo: On.** Lumagen recommends it. The integration ignores the echoed text.

Optional but recommended:

- **Report mode changes: Full v4.** The processor then reports video mode
  changes instantly instead of waiting for the next 15-second poll.

## Entities

| Entity | What it does |
|---|---|
| Remote | Power on / standby, plus `remote.send_command` for any key |
| Input (select) | Inputs 1-N, named with the labels set on the Radiance |
| Input memory (select) | Memory A-D |
| Game mode (switch) | Radiance Pro game mode |
| Video signal, HDR (binary sensors) | From the full-status report |
| Sensors | Source/output resolution, frame rate, aspect, colorspace, CMS, style, and more |

Video entities are unavailable while the processor is in standby. Set the
number of inputs in the integration's options (default 8).

### Remote commands

`remote.send_command` takes the key names below, or any raw RS-232 string,
which is sent exactly as given (include `\r` where Tech Tip 11 shows `<CR>`):

`menu`, `exit`, `ok`, `up`, `down`, `left`, `right`, `clear`, `help`, `alt`,
`0`-`9`, `plus_10`, `previous_input`, `zone`, `save`, `nls`, `osd_on`, `osd_off`,
`auto_aspect_on`, `auto_aspect_off`, `hdr_setup`, `test_pattern`, `memory_a`-`memory_d`,
`pip_off`, `pip_select`, `pip_swap`, `pip_mode`, and the source aspects
`aspect_4_3`, `aspect_letterbox`, `aspect_16_9`, `aspect_1_85`, `aspect_1_90`,
`aspect_2_00`, `aspect_2_20`, `aspect_2_35`, `aspect_2_40` (with `_nz`, `_nls` and `_nz_nls`
variants where the Radiance has them) and the extended aspects
`aspect_4_3_pillarbox`, `aspect_1_375_pillarbox`, `aspect_1_66_pillarbox`,
`aspect_2_10`, `aspect_2_55`, `aspect_2_76`.

```yaml
action: remote.send_command
target:
  entity_id: remote.lumagen_radiancepro
data:
  command: [aspect_2_40]
```

## Development

```sh
uv venv --python 3.14 && uv pip install pytest-homeassistant-custom-component aiousbwatcher serialx==1.11.0 ruff
.venv/bin/python -m pytest
```

`custom_components/lumagen/pylumagen/` is the protocol client. It has no Home
Assistant imports, so it can be split into its own package later.
