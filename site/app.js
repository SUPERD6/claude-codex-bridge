// Theme toggle (system by default, remembered per viewer when storage works) and copy buttons.
(function () {
  var root = document.documentElement;
  try { var t = localStorage.getItem('ccx-theme'); if (t) root.dataset.theme = t; } catch (e) {}
  var btn = document.querySelector('.theme');
  if (btn) btn.addEventListener('click', function () {
    var dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('ccx-theme', root.dataset.theme); } catch (e) {}
  });
  document.querySelectorAll('.copy').forEach(function (b) {
    var label = b.textContent;
    b.addEventListener('click', function () {
      var done = function (ok) { b.textContent = ok ? b.dataset.done : b.dataset.fail; setTimeout(function () { b.textContent = label; }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(b.dataset.copy).then(function () { done(true); }, function () { done(false); });
      else done(false);
    });
  });
})();
