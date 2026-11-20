(() => {
  const track = document.querySelector('.examples-track');
  const cards = [...track.querySelectorAll('.example-card')];
  const controls = document.querySelector('.gallery-controls');
  const position = controls.querySelector('.gallery-position');
  const pauseButton = controls.querySelector('.gallery-pause');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduced.matches;
  let inView = false;
  let timer = null;
  let index = 0;
  let programmatic = false;
  controls.hidden = false;

  function lastPosition() {
    const max = track.scrollWidth - track.clientWidth;
    const last = cards.findIndex(card => card.offsetLeft - cards[0].offsetLeft >= max - 1);
    return last < 0 ? cards.length - 1 : last;
  }

  function updateControls() {
    position.textContent = `${index + 1} / ${lastPosition() + 1}`;
    pauseButton.textContent = reduced.matches ? 'Автопрокрутка отключена' : paused ? 'Включить прокрутку' : 'Остановить';
    pauseButton.disabled = reduced.matches;
  }
  function stop() { paused = true; clearInterval(timer); timer = null; updateControls(); }
  function go(next) {
    const count = lastPosition() + 1;
    index = (next + count) % count;
    programmatic = true;
    track.scrollTo({left: cards[index].offsetLeft - cards[0].offsetLeft, behavior: reduced.matches ? 'auto' : 'smooth'});
    updateControls();
    setTimeout(() => { programmatic = false; }, 600);
  }
  function schedule() {
    clearInterval(timer); timer = null;
    if (!paused && inView && !document.hidden && !reduced.matches) timer = setInterval(() => go(index + 1), 6000);
    updateControls();
  }
  controls.querySelector('.gallery-prev').addEventListener('click', () => { stop(); go(index - 1); });
  controls.querySelector('.gallery-next').addEventListener('click', () => { stop(); go(index + 1); });
  pauseButton.addEventListener('click', () => { paused = !paused; schedule(); });
  track.addEventListener('pointerdown', stop);
  track.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); stop(); go(index + (event.key === 'ArrowRight' ? 1 : -1)); }
  });
  track.addEventListener('scroll', () => {
    if (programmatic) return;
    const offset = track.scrollLeft;
    index = cards.reduce((best, card, i) => Math.abs(card.offsetLeft - cards[0].offsetLeft - offset) < Math.abs(cards[best].offsetLeft - cards[0].offsetLeft - offset) ? i : best, 0);
    updateControls();
  }, {passive: true});
  const observer = new IntersectionObserver(entries => { inView = entries[0].isIntersecting; schedule(); }, {threshold: .25});
  observer.observe(document.querySelector('.examples-gallery'));
  document.addEventListener('visibilitychange', schedule);
  window.addEventListener('resize', () => { index = Math.min(index, lastPosition()); updateControls(); });
  reduced.addEventListener('change', () => { if (reduced.matches) paused = true; schedule(); });
  schedule();

  const dialog = document.querySelector('#example-dialog');
  const dialogImage = dialog.querySelector('img');
  document.querySelectorAll('.example-zoom').forEach(button => {
    const image = button.querySelector('img');
    function showPlaceholder() { button.hidden = true; button.style.display = 'none'; button.previousElementSibling.removeAttribute('aria-hidden'); }
    image.addEventListener('error', showPlaceholder);
    if (image.complete && !image.naturalWidth) showPlaceholder();
    button.addEventListener('click', () => { stop(); dialogImage.src = image.currentSrc; dialogImage.alt = image.alt; dialog.showModal(); });
  });
  dialog.querySelector('.example-dialog-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
})();
