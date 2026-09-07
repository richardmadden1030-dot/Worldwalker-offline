# Worldwalker RPG v3.35.0

## Canon-event cinematics

- Every canon event now opens with a full-screen native cinematic before returning control to the Chronicle.
- The scene is assembled from live campaign data: event title, canon date, event location, player location, travel time, involvement, combat state, and the best matching cached scene image.
- Naruto, One Piece, Bleach, Jujutsu Kaisen, Overgeared, Solo Max-Level Newbie, Reincarnated as a Slime, and Hunter x Hunter receive distinct color and motion treatments.
- Canon scenes include a short camera move, ink-cut reveal, event frame, particles, a replay control on desktop, and a direct handoff to the Chronicle.
- New events and custom timeline packs automatically use the system without requiring a bespoke UI implementation or an AI image call at playback time.

## Mobile and accessibility

- Mobile canon scenes use a dedicated vertical composition with readable title, context, position, travel, and involvement information.
- Animation-off and reduced-motion modes immediately reveal all event information without flashes, moving particles, or delayed text.
- Ordinary personal milestones and danger warnings keep the smaller informational sheet, reserving the full cinematic for canon history.

## Cost

- Cinematic playback is local HTML, CSS, and JavaScript. It does not add an AI request.
- Existing cached event art is used first. The normal environment-art fallback supplies a matching scene when no dedicated event image exists.
