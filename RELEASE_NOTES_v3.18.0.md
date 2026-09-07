# Worldwalker RPG v3.18.0

## Two-player shared campaigns

- The hosted friend server can now create a shared copy of any loaded or imported campaign and invite one friend with a six-character code.
- Both players inhabit one authoritative world and Chronicle while retaining separate characters, portraits, action queues and Ready states.
- Multiplayer rooms, character sheets, queued plans and the round clock persist through browser refreshes and server restarts.
- The host selects the shared time advance. A round resolves early when both connected players are ready or automatically after ten minutes.
- At timeout, only ready and connected players act. Disconnected or unready players pass. If neither player is ready, the world advances one Moment with both characters passing.
- A player who disconnects never repeats an old standing order or receives an AI-controlled action.
- Existing single-player campaigns and imported older saves can be copied into multiplayer without overwriting the original campaign.

## Interface and quality of life

- Added a visible, persistent volume slider to the world-music widget.
- Hovering the compact Time value now reveals its complete date and clock text.
- Added synchronized round/countdown information to the top bar and a responsive multiplayer lobby for desktop and phone browsers.
- Fixed second-player status normalization discovered during the two-device browser test.

## Verification

- Passed the full automated suite, including durable-room, separate-character, disconnect/pass, timeout and account-isolation coverage.
- Completed a real two-account desktop/mobile browser flow: host, invite, join, distinct character views, host-only time controls, synchronized countdown and persistent volume.
