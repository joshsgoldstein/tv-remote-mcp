# Connect an LG or Sony TV

LG and Sony adapters are **experimental**. Protocol tests use simulated devices.
No LG or Sony hardware has been checked yet. Support depends on your model.
Keep your existing Samsung setup. No token migration is needed.

## Add your TV

1. Turn on the TV.
2. Open Home Control on a computer on your home network.
3. Select LG webOS or Sony BRAVIA under **Discover with**.
4. Select **Find devices**.
5. If discovery finds nothing, open **Add TV by address**.
6. Enter the TV type, name, and IP address.
7. Select **Add TV**.

Discovery uses UPnP/SSDP. Some TVs disable it. Docker bridge networks can block
multicast packets. Manual IP entry works without multicast discovery.
A network match is not proof that your model supports all controls.

## LG webOS

Use this adapter for webOS TVs. LG NetCast is not supported.

1. Enable local app control in the TV settings. Some models call this **LG Connect Apps**.
2. Select **Pair television** in Home Control.
3. Select **Allow** on the TV within 25 seconds.

The adapter saves the TV's client key in private local storage.
The default port is 3001 with TLS. Older models may need port 3000.
Use the optional Port field when you add a TV that needs port 3000.
These local TLS connections accept the TV's self-signed certificate.

Controls include navigation, volume, channels, playback, apps, text, and power off.
Source and guide buttons are not advertised by this first LG adapter.
Text requires an active text field on the TV. Model support varies.

Power on needs the TV's MAC address and Wake-on-LAN support.
Enable **TV On With Mobile** or its equivalent when your model provides it.
Save the MAC with the CLI or private configuration. A wake packet does not confirm power on.

## Sony BRAVIA

Use this adapter for TVs with Sony's JSON-RPC API and IRCC-IP remote controls.
Android TV or Google TV branding alone does not guarantee those APIs.
This adapter uses a **pre-shared key (PSK)**. PIN and cookie pairing are not implemented.

1. Enable **IP control** in the TV settings.
2. Enable pre-shared-key access.
3. Set a private key on the TV.
4. Select **Pair television** in Home Control.
5. Enter the key in the password dialog.
6. Select **Connect**.

Menu names vary by model. Do not switch off authentication.
The key is saved in a private file on the Home Control server.
Do not paste it into chat, a shell argument, a screenshot, or a public file.
The default port is 80. For models with HTTPS API access, use port 443.
The adapter accepts local self-signed TLS certificates on port 443.
PSKs sent over port 80 use plain HTTP on the home LAN.

Controls include navigation, volume, channels, playback, apps, and power.
Only remote key names advertised by the TV are sent.
App IDs must come from the TV's app list. Sony text entry is not implemented.
App APIs can be absent on some models.

## Use the terminal

These addresses are examples. Use the TV's actual address and returned device ID.

```sh
uv run home-control add-device lg_webos lounge 192.168.1.20 --name "Lounge LG"
uv run home-control device-pair lg_webos:lounge
uv run home-control add-device sony_bravia den 192.168.1.21 --name "Den Sony"
uv run home-control device-pair sony_bravia:den
```

The Sony command asks for the key with hidden input.
Use `--mac 02:00:00:00:00:01` only with the TV's actual MAC for wake.
Use `--port 3000` for an LG that needs plain WebSocket access.
Use `--port 443` for a Sony with an HTTPS API.

## State and control switches

Status checks open a TCP connection only. They do not pair the TV or read power.
The dashboard reports power as unknown for these adapters.
A saved key does not guarantee that the TV still accepts it.
If the TV revokes a key, an explicit command can fail or cause a new TV prompt.
Pair again only when someone is ready.

Both adapters check the device and master switches before commands.
They check again after a connection or authorization step.
This includes pairing, wake, apps, and remote keys.
Keys use private files with mode 0600. Inventory and status never return them.
