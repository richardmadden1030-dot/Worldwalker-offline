WORLDWALKER RPG 3.62.0 - LOCAL PHONE PLAY
=========================================

MOBILE INTERFACE
----------------
- Use the bottom bar to switch between Chronicle, Actions, Character, Map,
  and More without losing your place.
- The fixed Advance bar shows the selected time step and queued-action count.
- More contains the full-screen Advisor, world-specific group roster, Quests, Relationships,
  Inventory, settings, low-data mode, haptics, and large-text mode.
- Draft actions remain available if the browser reloads or briefly disconnects.

WHAT YOU NEED
-------------
- The extracted Worldwalker Phone Host folder on your Windows PC.
- Your PC and phone connected to the same private Wi-Fi network.
- The PC must stay awake and this host window must remain open while playing.

HOW TO START
------------
1. Extract the entire ZIP. Do not run the game from inside the ZIP preview.
2. Double-click "Start Phone Mode.bat" on the Windows PC.
3. If Windows Firewall asks, allow access on PRIVATE networks. Do not enable
   Public-network access.
4. The PC window displays an address similar to:

       https://192.168.1.25:54321/

5. Type that complete address into Safari or Chrome on your phone, including
   https:// and the port number after the colon.
6. The FIRST time you connect, your phone's browser will show a "connection
   isn't private" or "not trusted" warning. This is expected — Phone Mode
   secures itself with a certificate it generates locally rather than one
   from a public certificate authority (there's no real domain name to get
   one for). Tap "Advanced" / "Show Details", then "Proceed" / "visit this
   website" to continue. You only need to do this once per phone; it's
   remembered after that.

The phone is a controller and display for the game running on the PC. Saves,
AI settings, music, and generated art remain on the PC. Closing the host
window ends the phone connection but does not delete the campaign.

IF THE ADDRESS DOES NOT LOAD
----------------------------
1. Confirm both devices are on the same Wi-Fi. Disable cellular data briefly
   so the phone cannot choose the mobile connection instead.
2. Do not use a guest Wi-Fi network; many guest networks prevent devices from
   talking to each other.
3. In Windows Firewall, allow WorldwalkerRPG.exe on Private networks.
4. Temporarily disconnect VPN software on the PC and phone. A VPN can make the
   displayed address unreachable from the local network.
5. Keep the host window open and copy the address exactly. The port changes
   each time Phone Mode starts, so an older saved address will not work.
6. Test the displayed address in a normal browser on the PC. If it works on
   the PC but not the phone, Wi-Fi isolation or the firewall is blocking it.

SECURITY
--------
This mode is intended only for a trusted private network. Do not forward its
port through your router or use it on public Wi-Fi. Anyone who can reach the
displayed address can control the currently running game.
