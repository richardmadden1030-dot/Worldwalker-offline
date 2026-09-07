# Worldwalker RPG 3.6.1

## Phone Mode fixes

- Phone Mode now serves itself over HTTPS with a locally generated,
  persisted certificate. Browsers refuse to run this app's embedded Godot
  ambience canvases (portrait/scene/map) unless the page is a secure
  context, and a bare LAN address over plain HTTP never qualified — this
  was causing the ambient art to fail to load on phones even when the
  connection itself worked. The certificate is self-signed (there's no
  real domain name to get a publicly trusted one for), so each phone needs
  to accept a one-time "connection isn't private" warning on first
  connect; it's remembered after that. See the updated PHONE_PLAY_README.txt.
- Fixed the address Phone Mode displays and shares with your phone: on a
  machine with more than one network adapter (a VPN client such as
  Tailscale, a virtual switch, etc.), the previous detection method could
  return the VPN/virtual adapter's address instead of the real Wi-Fi/LAN
  address — reachable from the PC itself, but not from a phone on the same
  physical Wi-Fi network. Detection now reliably picks the adapter actually
  used for LAN/outbound traffic.

## Validation

- Verified the LAN-mode HTTPS server responds correctly and normal
  (non-LAN) desktop mode is unaffected and remains plain HTTP.
- Verified network-IP detection returns the real LAN address on a machine
  with an active Tailscale adapter present.
