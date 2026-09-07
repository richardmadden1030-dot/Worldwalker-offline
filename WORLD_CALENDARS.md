# World dates and calendar audit

Build: 3.63.0-adventures-1. All nine worlds have built-in civil-calendar
profiles. World time is independent of the computer's clock and the campaign's
elapsed-days counter. Starting another era no longer restarts January 1.

## Precision, not invented certainty

| World | Anchor used | What the date means |
|---|---|---|
| One Piece | Sea Circle 1522-02-18 at the installed Reverse Mountain offset | Chapter-referenced reconstruction, not an official exhaustive dated chronology. |
| Hunter x Hunter | 1999-01-07 at the installed 287th Hunter Exam offset | Reconstructed chronology; other event spacing remains the installed approximation. |
| Jujutsu Kaisen | 2018-10-31 at the Shibuya Incident offset | The official episode page confirms this date. Other installed event offsets remain projections. |
| Bleach | 2001-05-18 at the opening offset | Mid-May is reconstructed; the 18th is an explicitly estimated game anchor, not an asserted canon day. |
| Naruto | October 10, Birth era 0, at Naruto's birth offset | The named era numbering is a game convention, not an asserted canonical civil year. |
| Overgeared | September 1, Satisfy era 1, at the service-launch offset | A fixed in-world game convention, not a claim about the canon launch day or Earth year. |
| Reincarnated as a Slime | April 1, Rimuru era 1, at arrival | Conventional month/day and era for the installed relative chronology. |
| Solo Max-Level Newbie | September 1, Tower era 1, at Tower arrival | Conventional date for the relative chronology; explicit saved Earth epochs remain intact. |
| Custom World | April 1, World era 1 | Default convention; explicit saved/custom epochs remain intact. |

A fully specified canonical day/month/year system was not established by the
available sources for every setting. The UI therefore labels precision and
explains conventions rather than presenting fabricated absolute dates as canon.
A calendar profile is not proof that every scheduled story event has a confirmed
date. The installed timelines retain approximate spacing. Exact time-of-day
scheduling is not a newly verified canon chronology: ordinary event boundaries
still use the engine's established morning boundary unless otherwise authored.

Source notes are bundled in `assets/data/world_calendars.json` and surfaced in
calendar descriptions. References consulted:

- Official Jujutsu Kaisen episode 32: https://jujutsukaisen.jp/episodes/32.php
- Artur's chapter-referenced One Piece reconstruction: https://thelibraryofohara.com/the-one-piece-timeline/
- Hunterpedia's referenced timeline: https://hunterxhunter.fandom.com/wiki/Timeline
- Bleach timeline: https://bleach.fandom.com/wiki/Timeline_of_Events
- Naruto chronology: https://naruto.fandom.com/wiki/User:Seelentau/Naruto_Timeline
- Overgeared dating limitations: https://overgeared.fandom.com/wiki/Timeline

## Compatibility and calculation

`canon_day` and `canon_time_minutes` remain the authoritative scheduling offsets.
Event IDs, fired-event receipts, selected starting eras and stored elapsed time
are not renumbered. Legacy chronicles are not rewritten. New UI dates are
computed from a world epoch and offset, including negative (historical) offsets.
Python and browser formatters are tested against the same bundled profiles.

New campaigns use a fixed world epoch, not today's real-world date. Existing
Custom World and Solo Max-Level Newbie saves with an explicit date retain it.
All realm maps share their campaign clock; viewing another realm or the canon
reference does not move the character or advance time.

Hours, days and weeks are elapsed durations. Whole calendar-month advances use
civil month lengths with end-of-month clamping (January 31, 2024 -> February 29,
2024 -> March 29, 2024 for consecutive one-month advances). Fractional months
use the length of the target month. No local timezone or daylight saving offset
enters the calculation. Legacy 360-day age/progression counters are retained for
save compatibility; this update does not retroactively recalculate birthdays,
age, or earlier training rewards.

## Canon reference

The ordinary Journal and map toolbar expose **Canon timeline**. Future titles
and summaries are unmasked regardless of the former spoiler-hiding preference.
Search, date/status filters, and editable preparation drafts help the player
reference events. Labels distinguish projected, historical and changed events.
Reading the reference never inserts its future facts into NPC knowledge. Player
interference can still make an event delayed, changed or impossible; referencing
it does not force it to occur.
