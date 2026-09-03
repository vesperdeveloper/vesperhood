/* Copy the contract address. A CA people have to hand-transcribe is a CA
   people get wrong, and getting it wrong costs them money. */
(function () {
  'use strict';
  var btn = document.querySelector('.ca-copy');
  if (!btn) return;
  var state = btn.querySelector('.ca-state');
  var reset;

  function flash(text) {
    if (!state) return;
    state.textContent = text;
    btn.classList.add('done');
    clearTimeout(reset);
    reset = setTimeout(function () {
      state.textContent = 'copy';
      btn.classList.remove('done');
    }, 1600);
  }

  btn.addEventListener('click', function () {
    var ca = btn.getAttribute('data-ca');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(ca).then(function () { flash('copied'); },
                                             function () { fallback(ca); });
    } else {
      fallback(ca);
    }
  });

  function fallback(ca) {
    // Older browsers and insecure contexts have no clipboard API. Select the
    // text instead so the address can still be copied by hand.
    var el = btn.querySelector('.ca-full') || btn;
    try {
      var r = document.createRange();
      r.selectNodeContents(el);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      flash(document.execCommand('copy') ? 'copied' : 'select');
    } catch (e) {
      flash('select');
    }
  }
})();
