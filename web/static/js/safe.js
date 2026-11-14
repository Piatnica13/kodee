// Escape every value that enters an HTML template; links remain local paths.
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
}
function productURL(slug) {
  return '/product/' + encodeURIComponent(String(slug ?? ''));
}
function productImage(value) {
  try {
    const url = new URL(String(value || ''), window.location.origin);
    if (url.origin === window.location.origin && url.pathname.startsWith('/static/image/')) return escapeHTML(url.pathname);
  } catch (_) {}
  return '/static/image/imgShop/BrasletsAndEgg.webp';
}
