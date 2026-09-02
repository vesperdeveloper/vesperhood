/* Vesper — the live desk. */
(function () {
  'use strict';
  var all = [], tier = 'all', term = '';

  function num(n) { return Number(n).toLocaleString('en-US'); }
  function short(a) { return a.slice(0, 6) + '…' + a.slice(-4); }

  fetch('/v1/session').then(function (r) { return r.json(); }).then(function (s) {
    var h = document.getElementById('deskHead');
    var d = document.getElementById('deskDot');
    var n = document.getElementById('deskNote');
    if (h) h.textContent = s.open ? 'Exchange open.' : 'Exchange shut.';
    if (n) n.textContent = s.note + ' New York ' + s.new_york_time + '.';
    if (d) { d.className = 'dot ' + (s.open ? 'live' : 'shut'); }
  }).catch(function () {
    var n = document.getElementById('deskNote');
    if (n) n.textContent = 'Session endpoint unreachable.';
  });

  fetch('/v1/network').then(function (r) { return r.json(); }).then(function (d) {
    var a = document.getElementById('stHead'), b = document.getElementById('stGas');
    if (a && d.block) a.textContent = num(d.block);
    if (b && d.gas_price_gwei != null) b.textContent = d.gas_price_gwei;
  }).catch(function () {});

  fetch('/v1/agents').then(function (r) { return r.json(); }).then(function (d) {
    var a = document.getElementById('stAgOnline');
    var b = document.getElementById('stAgTotal');
    var w = document.getElementById('stWindow');
    if (a) a.textContent = num(d.agents_online || 0);
    if (b) b.textContent = num(d.agents_total || 0);
    if (w) w.textContent = d.online_window_label || '24h';
  }).catch(function () {});

  fetch('/v1/contracts').then(function (r) { return r.json(); }).then(function (d) {
    var el = document.getElementById('stBook');
    if (el) el.textContent = d.venue_live ? 'live' : 'pending';
  }).catch(function () {});

  function render() {
    var tb = document.getElementById('board');
    if (!tb) return;
    var rows = all.filter(function (p) {
      if (tier !== 'all' && p.tier !== tier) return false;
      if (!term) return true;
      var t = term.toLowerCase();
      return p.symbol.toLowerCase().indexOf(t) >= 0 || (p.name || '').toLowerCase().indexOf(t) >= 0;
    });
    tb.innerHTML = '';
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="7" class="muted">Nothing matches that.</td></tr>';
    }
    rows.forEach(function (p) {
      var tr = document.createElement('tr');
      var icon = p.icon ? '<img src="' + p.icon + '" alt="" loading="lazy">' : '';
      var last = p.price_usd != null
        ? '$' + Number(p.price_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : '<span class="muted">—</span>';
      tr.innerHTML =
        '<td class="sym"><span class="tick">' + icon + p.symbol + '/USDG</span></td>' +
        '<td class="muted">' + (p.name || '') + '</td>' +
        '<td><span class="pill ' + p.tier + '">' + p.tier + '</span></td>' +
        '<td class="n r">' + num(p.holders) + '</td>' +
        '<td class="n r">' + last + '</td>' +
        '<td><a class="addr" href="' + p.explorer + '" target="_blank" rel="noopener">' + short(p.address) + '</a></td>' +
        '<td class="n r muted">at launch</td>';
      tb.appendChild(tr);
    });
    var s = document.getElementById('shown');
    if (s) s.textContent = 'showing ' + rows.length + ' of ' + all.length + ' pairs';
  }

  document.querySelectorAll('.filters button').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.filters button').forEach(function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      tier = b.getAttribute('data-tier');
      render();
    });
  });
  var q = document.getElementById('q');
  if (q) q.addEventListener('input', function () { term = q.value.trim(); render(); });

  fetch('/v1/pairs?live=1').then(function (r) { return r.json(); }).then(function (d) {
    all = d.pairs || [];
    var c = document.getElementById('cAll');
    if (c) c.textContent = d.count;
    render();
  }).catch(function () {
    var tb = document.getElementById('board');
    if (tb) tb.innerHTML = '<tr><td colspan="7" class="muted">Registry unreachable.</td></tr>';
  });
})();
