document.addEventListener('DOMContentLoaded', () => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.getElementById('indiv1')?.classList.add('individual-intro-started');
}, {once: true});
