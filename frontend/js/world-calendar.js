/* Generated profile data from assets/data/world_calendars.json; parity-tested. */
const WorldCalendar = (() => {
  "use strict";
  const profiles = {"One Piece":{"epoch":"1522-02-18","anchor_day":17,"label":"Sea Circle calendar","era":"","year_offset":0,"precision":"reconstructed","note":"Anchored to the February 18 Reverse Mountain reconstruction. The installed event spacing is approximate, not a complete canon day-by-day chronology.","sources":[{"title":"The Library of Ohara — sourced timeline reconstruction","url":"https://thelibraryofohara.com/the-one-piece-timeline/"}]},"Hunter x Hunter":{"epoch":"1999-01-07","anchor_day":7,"label":"Hunter world calendar","era":"","year_offset":0,"precision":"reconstructed","note":"The 287th Hunter Exam anchors January 7, 1999. Other dates follow the installed approximate event spacing.","sources":[{"title":"Hunterpedia — chapter-referenced timeline","url":"https://hunterxhunter.fandom.com/wiki/Timeline"}]},"Jujutsu Kaisen":{"epoch":"2018-10-31","anchor_day":183,"label":"Gregorian calendar","era":"","year_offset":0,"precision":"anchored","note":"Shibuya is anchored to October 31, 2018. Other dates retain the installed approximate event spacing; they are campaign projections, not newly verified canon dates.","sources":[{"title":"Official episode 32 — October 31, 2018, 19:00","url":"https://jujutsukaisen.jp/episodes/32.php"}]},"Bleach":{"epoch":"2001-05-18","anchor_day":0,"label":"World of the Living calendar","era":"","year_offset":0,"precision":"estimated","note":"Mid-May 2001 is the reconstructed opening window. May 18 is a campaign anchor, not a confirmed exact day. Realm travel does not silently reset this shared clock.","sources":[{"title":"Bleach — timeline of events","url":"https://bleach.fandom.com/wiki/Timeline_of_Events"}]},"Naruto":{"epoch":"2000-10-10","anchor_day":-4380,"label":"Shinobi calendar","era":"Birth era","year_offset":-2000,"precision":"estimated","note":"October 10 anchors Naruto’s birth. The numbered Birth era is a game convention because a canonical civil year is not established here. Other dates follow the installed chronology.","sources":[{"title":"Narutopedia — referenced chronology","url":"https://naruto.fandom.com/wiki/User:Seelentau/Naruto_Timeline"}]},"Overgeared":{"epoch":"2000-09-01","anchor_day":-365,"label":"Satisfy calendar","era":"Satisfy era","year_offset":-1999,"precision":"campaign convention","note":"A fixed Satisfy launch epoch, not an asserted canon month or Earth year. Dates track in-world time; they are not multiplied again by the real-world login ratio.","sources":[{"title":"Overgeared timeline — dating limitations","url":"https://overgeared.fandom.com/wiki/Timeline"}]},"Reincarnated as a Slime":{"epoch":"2000-04-01","anchor_day":0,"label":"Central World calendar","era":"Rimuru era","year_offset":-1999,"precision":"campaign convention","note":"A fixed civil calendar relative to Rimuru’s arrival. The month/day and era numbering are game conventions where the installed sources provide only relative dates.","sources":[]},"Solo Max-Level Newbie":{"epoch":"2000-09-01","anchor_day":0,"label":"Tower-era calendar","era":"Tower era","year_offset":-1999,"precision":"campaign convention","note":"A fixed Tower-arrival calendar; no unverified Earth year is asserted. Existing saves with an explicit Earth-date epoch retain that epoch.","sources":[]},"Custom World":{"epoch":"2000-04-01","anchor_day":0,"label":"World calendar","era":"World era","year_offset":-1999,"precision":"campaign convention","note":"Default configurable-world civil calendar. Explicit saved epochs are preserved. The default epoch is a game convention, not canon.","sources":[]}};
  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  function profile(world, epoch, anchor) {
    const p = {...(profiles[world] || profiles["Custom World"])};
    if (["Solo Max-Level Newbie","Custom World"].includes(world) && /^\d{4}-\d{2}-\d{2}$/.test(epoch || "")) {
      const d = new Date(epoch + "T00:00:00.000Z");
      if (Number.isFinite(d.getTime()) && d.toISOString().slice(0,10) === epoch) {
        Object.assign(p, {epoch, anchor_day: anchor == null ? (world === "Solo Max-Level Newbie" ? -3 : -7) : Math.trunc(Number(anchor)), era:"", year_offset:0, precision:"saved campaign epoch", note:"Preserved explicit date from this campaign save."});
      }
    }
    return p;
  }
  function parts(world, day, epoch, anchor) {
    const p = profile(world, epoch, anchor);
    if (!Number.isFinite(Number(day))) return null;
    const d = new Date(new Date(p.epoch + "T00:00:00.000Z").getTime() + (Math.trunc(Number(day)) - p.anchor_day)*86400000);
    if (!Number.isFinite(d.getTime()) || d.getUTCFullYear()<1 || d.getUTCFullYear()>9999) return null;
    return {year:d.getUTCFullYear()+p.year_offset,month:d.getUTCMonth()+1,day:d.getUTCDate(),iso:d.toISOString().slice(0,10),era:p.era,calendar:p.label,precision:p.precision};
  }
  function format(world, day, epoch, anchor) {
    const p = parts(world, day, epoch, anchor);
    if (!p) return "Date outside supported calendar range";
    return `${months[p.month-1]} ${p.day}, ${p.era ? p.era+" " : ""}${p.year}`;
  }
  return Object.freeze({format,parts,profile,profiles});
})();
