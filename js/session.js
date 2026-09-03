/* VesperHood — session clock, ground switching, rail telemetry.
   The regular US equity session is 09:30–16:00 America/New_York, Mon–Fri.
   Everything outside it is what this desk exists for. */
(function () {
  'use strict';

  var STORE = 'vesperhood.ground';

  function nyParts(d) {
    var f = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York', hour12: false,
      weekday: 'short', hour: '2-digit', minute: '2-digit'
    }).formatToParts(d);
    var o = {};
    f.forEach(function (p) { o[p.type] = p.value; });
    var days = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
    return {
      dow: days[o.weekday],
      mins: (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10)
    };
  }

  var OPEN = 9 * 60 + 30, CLOSE = 16 * 60;

  function state(d) {
    var p = nyParts(d || new Date());
    var weekday = p.dow >= 1 && p.dow <= 5;
    var open = weekday && p.mins >= OPEN && p.mins < CLOSE;
    var mins;
    if (open) {
      mins = CLOSE - p.mins;
    } else {
      // minutes until the next 09:30 ET that falls on a weekday
      var d2 = p.mins < OPEN && weekday ? 0 : 1;
      if (d2 === 1) {
        var dow = p.dow;
        var add = 1;
        while (((dow + add) % 7) === 0 || ((dow + add) % 7) === 6) add++;
        d2 = add;
      }
      mins = (d2 * 1440) + OPEN - p.mins;
    }
    return { open: open, mins: mins };
  }

  function human(m) {
    if (m < 60) return m + 'm';
    var h = Math.floor(m / 60), r = m % 60;
    if (h < 24) return h + 'h ' + String(r).padStart(2, '0') + 'm';
    return Math.floor(h / 24) + 'd ' + (h % 24) + 'h';
  }

  function ground(g, manual) {
    document.documentElement.setAttribute('data-session', g);
    var b = document.getElementById('tswitch');
    if (b) {
      b.textContent = g === 'night' ? 'Paper' : 'Night';
      b.setAttribute('aria-pressed', g === 'night' ? 'true' : 'false');
    }
    if (manual) { try { localStorage.setItem(STORE, g); } catch (e) {} }
  }

  function paint() {
    var s = state();
    var pref = null;
    try { pref = localStorage.getItem(STORE); } catch (e) {}
    // Paper is the default ground. The session clock still drives the rail
    // readouts, but it no longer flips the theme under the reader — only
    // the switch does, and that choice persists.
    ground(pref || 'day', false);

    var ms = document.getElementById('mSession');
    var mu = document.getElementById('mUntil');
    if (ms) {
      ms.textContent = s.open ? 'open' : 'closed';
      ms.className = s.open ? 'live' : 'shut';
    }
    if (mu) mu.textContent = human(s.mins);
    return s;
  }

  function head() {
    fetch('/v1/network').then(function (r) { return r.json(); }).then(function (d) {
      var el = document.getElementById('mHead');
      if (el && d && d.block) el.textContent = Number(d.block).toLocaleString('en-US');
    }).catch(function () {});
  }

  function agents() {
    var el = document.getElementById('mAgents');
    if (!el) return;
    fetch('/v1/agents').then(function (r) { return r.json(); }).then(function (d) {
      var n = Number(d.agents_online || 0);
      el.textContent = n + ' online';
      el.className = n > 0 ? 'live' : '';
    }).catch(function () { el.textContent = '—'; });
  }

  var b = document.getElementById('tswitch');
  if (b) b.addEventListener('click', function () {
    ground(document.documentElement.getAttribute('data-session') === 'night' ? 'day' : 'night', true);
  });

  paint();
  head();
  agents();
  setInterval(paint, 30000);
  setInterval(head, 60000);
  setInterval(agents, 45000);

  window.VesperSession = { state: state, human: human };
})();
