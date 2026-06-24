/* Shared doc-page renderer: injects the header/footer and renders the page's
   markdown (from <body data-md="…">) with marked.js — keeps styling consistent
   with the Tailwind landing page, no Jekyll needed. */
(function () {
  var md = document.body.dataset.md;
  var title = document.body.dataset.title || 'Docs';
  document.title = title + ' · JobHunt';

  var nav =
    '<header class="sticky top-0 z-20 backdrop-blur bg-white/80 border-b border-slate-200">' +
    '<div class="max-w-3xl mx-auto px-5 h-14 flex items-center justify-between">' +
    '<a href="index.html" class="flex items-center gap-2.5">' +
    '<div class="w-8 h-8 rounded-lg bg-emerald-500 text-white font-bold grid place-items-center text-sm">JH</div>' +
    '<span class="font-semibold text-slate-900">JobHunt</span></a>' +
    '<nav class="flex items-center gap-5 text-sm text-slate-600">' +
    '<a href="architecture.html" class="hover:text-emerald-600">Architecture</a>' +
    '<a href="features.html" class="hover:text-emerald-600">Features</a>' +
    '<a href="api.html" class="hover:text-emerald-600">API</a></nav></div></header>';

  var footer =
    '<footer class="border-t border-slate-200 bg-white mt-16">' +
    '<div class="max-w-3xl mx-auto px-5 py-8 flex items-center justify-between text-sm text-slate-500">' +
    '<a href="index.html" class="hover:text-emerald-600">← Back to home</a>' +
    '<nav class="flex items-center gap-4">' +
    '<a href="architecture.html" class="hover:text-emerald-600">Architecture</a>' +
    '<a href="features.html" class="hover:text-emerald-600">Features</a>' +
    '<a href="api.html" class="hover:text-emerald-600">API</a></nav></div></footer>';

  document.body.insertAdjacentHTML('afterbegin', nav);
  var main = document.createElement('main');
  main.className = 'max-w-3xl mx-auto px-5 py-12';
  main.innerHTML = '<article id="doc" class="doc">Loading…</article>';
  document.body.appendChild(main);
  document.body.insertAdjacentHTML('beforeend', footer);

  fetch(md)
    .then(function (r) { return r.text(); })
    .then(function (t) {
      // Drop the in-markdown footer nav line (the HTML wrapper provides nav).
      t = t.replace(/\n\[← Back to home\][^\n]*\n?/g, '\n');
      document.getElementById('doc').innerHTML = marked.parse(t);
    })
    .catch(function () {
      document.getElementById('doc').textContent = 'Failed to load ' + md;
    });
})();
