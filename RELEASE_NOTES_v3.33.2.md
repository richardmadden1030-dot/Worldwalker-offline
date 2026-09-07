# Worldwalker RPG v3.33.2

- Local-phone CSS, JavaScript and artwork now remain safely cached so an iOS-restored tab does not collapse into raw HTML during a brief LAN interruption.
- APIs and account/game data remain strictly uncached.
- The phone now checks the actual Worldwalker host instead of relying only on the device's generic online status.
- Returning to a suspended tab immediately checks the PC, refreshes campaign state after reconnection and preserves the player's typed draft.
- A small inline recovery screen remains readable even when the main stylesheet itself cannot be reached.
- Versioned service-worker shell files prevent old CSS or JavaScript from surviving an update.

## Verification

- Cache-policy unit and route tests
- Online, forced-offline, reconnect and restored-page browser checks
- Mobile viewport visual check
- Full automated test suite
- Windows executable self-test
