/* Vesperhood — landing: scroll reveals, nav highlighting, registry preview. */
(function () {
  'use strict';

  var rv = document.querySelectorAll('.rv');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -8% 0px', threshold: .06 });
    rv.forEach(function (el) { io.observe(el); });
  } else {
    rv.forEach(function (el) { el.classList.add('in'); });
  }

  var secs = [].slice.call(document.querySelectorAll('.sec[id]'));
  var links = {};
  document.querySelectorAll('.nav a[href^="#"]').forEach(function (a) {
    links[a.getAttribute('href').slice(1)] = a;
  });
  if (secs.length && 'IntersectionObserver' in window) {
    var spy = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var a = links[e.target.id];
        if (!a) return;
        if (e.isIntersecting) {
          Object.keys(links).forEach(function (k) { links[k].classList.remove('on'); });
          a.classList.add('on');
        }
      });
    }, { rootMargin: '-15% 0px -70% 0px' });
    secs.forEach(function (s) { spy.observe(s); });
  }

  fetch('/v1/pairs').then(function (r) { return r.json(); }).then(function (d) {
    var tb = document.getElementById('preview');
    if (!tb || !d.pairs) return;
    var n = document.getElementById('sPairs');
    if (n) n.textContent = d.count;
    tb.innerHTML = '';
    d.pairs.slice(0, 10).forEach(function (p) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td class="sym">' + p.symbol + '/USDG</td>' +
        '<td class="muted">' + p.name + '</td>' +
        '<td><span class="pill ' + p.tier + '">' + p.tier + '</span></td>' +
        '<td class="n r">' + Number(p.holders).toLocaleString('en-US') + '</td>';
      tb.appendChild(tr);
    });
    var more = document.createElement('tr');
    more.innerHTML = '<td colspan="4" class="muted">…and ' + (d.count - 10) +
      ' more on the <a href="desk.html" style="color:var(--ember)">desk</a></td>';
    tb.appendChild(more);
  }).catch(function () {
    var tb = document.getElementById('preview');
    if (tb) tb.innerHTML = '<tr><td colspan="4" class="muted">Registry unreachable.</td></tr>';
  });
})();
