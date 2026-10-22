# Connect your TV

Choose the instructions for your TV:

- [Samsung TVs and The Frame](#samsung-tvs-and-the-frame)
- [LG webOS](#lg-webos)
- [Sony BRAVIA](#sony-bravia)

Samsung is the first adapter. LG and Sony adapters are experimental.
Physical control checks are still pending. Support depends on your model.

## Find your TV

1. Turn on the TV.
2. Open Home Control on a computer on your home network.
3. Select your TV brand under **Discover with**.
4. Select **Find devices**.
5. Select your TV from the list.
6. Follow the instructions for your brand below.

If an LG or Sony TV is missing, use **Add TV by address**.
Enter its type, name, and IP address. Then select **Add TV**.
For a missing Samsung TV, check the home subnet and scan again.
[The manual setup guide](REFERENCE.md#discover-and-pair-from-the-terminal) has more help.

LG and Sony discovery uses UPnP/SSDP. Some TVs and Docker networks block it.
Manual IP entry works without multicast discovery.

## Samsung TVs and The Frame

Use this adapter for Samsung Tizen TVs. Older Orsay TVs are not supported.
The Frame uses the same setup.

1. Select **Pair television** in Home Control.
2. Select **Allow** on the TV for **Samsung TV Remote MCP** within 25 seconds.
3. Wait for Home Control to show that the pairing token was saved.

If no one can select Allow, leave pairing pending. Try again when someone is ready.
The saved token lets Home Control reconnect later. Keep the TV's authorization enabled.

Use the remote panel for navigation, volume, channels, and playback.
Select **Load apps** to request the app list. App support varies by model.

On The Frame, use the **Art Mode** panel to select art or request Art Mode.
Art Mode and TV power are separate. A power toggle can change between them.
For power on, the TV needs Wake-on-LAN support and a saved MAC address.
Enable **Power On with Mobile** if your model provides it.

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
# Samsung: use the ID returned by discovery.
uv run tv-remote discover --save
uv run tv-remote pair frame

# LG and Sony:
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

Samsung status reads the TV's reported state.
LG and Sony status checks open a TCP connection only. They do not read power.
The dashboard reports power as unknown for LG and Sony.
Status checks do not start pairing.
A saved key does not guarantee that the TV still accepts it.
If the TV revokes a key, an explicit command can fail or cause a new TV prompt.
Pair again only when someone is ready.

All three adapters check the device and master switches before commands.
They check again after a connection or authorization step.
This includes pairing, wake, apps, and remote keys.
Keys use private files with mode 0600. Inventory and status never return them.
