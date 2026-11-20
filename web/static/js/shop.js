// Enhance the complete server-rendered catalogue; keep links and card markup intact.
const cards = Array.from(document.querySelectorAll('.shop-collection .product-card'));
const filterPanel = document.querySelector('#BockMenu');
const filterTrigger = document.querySelector('#Divfiltr');
const filterClose = document.querySelector('#BockMenuClose');
const filterBackdrop = document.querySelector('#Darker');
const more = document.querySelector('#shopBthMore');
const moreContainer = document.querySelector('#shopDivBthMore');
const resultStatus = document.querySelector('#catalog-result');
const priceBands = ['10000₸ - 40000₸', '40000₸ - 64000₸', 'Больше 64000₸'];
let showAll = false;
let appliedFilters = {};
let previousOverflow = '';

function selectedFilters() {
  const filters = {};
  filterPanel.querySelectorAll('input:checked').forEach(input => {
    (filters[input.dataset.category] ||= []).push(input.dataset.value);
  });
  return filters;
}

function matches(card, filters) {
  const price = Number(card.dataset.price);
  return (!filters['Категория'] || filters['Категория'].includes(card.dataset.category)) &&
    (!filters['Концепция'] || filters['Концепция'].includes(card.dataset.concept)) &&
    (!filters['Цена'] || filters['Цена'].some(band =>
      band === priceBands[0] ? price >= 10000 && price <= 40000 :
      band === priceBands[1] ? price >= 40000 && price <= 64000 : price > 64000));
}

function renderCatalogue() {
  const filtered = cards.filter(card => matches(card, appliedFilters));
  const visible = new Set(showAll ? filtered : filtered.slice(0, 12));
  cards.forEach(card => { card.hidden = !visible.has(card); });
  document.querySelectorAll('.shop-collection').forEach(section => {
    section.hidden = !section.querySelector('.product-card:not([hidden])');
  });
  moreContainer.hidden = showAll || filtered.length <= 12;
  more.hidden = moreContainer.hidden;
  resultStatus.textContent = filtered.length ? `Показано ${visible.size} из ${filtered.length}` :
    'По этим фильтрам изделий нет. Измените выбор или сбросьте фильтры.';
  window.AOS?.refreshHard();
}

function setPanel(open) {
  filterPanel.inert = !open;
  filterPanel.setAttribute('aria-hidden', String(!open));
  filterTrigger.setAttribute('aria-expanded', String(open));
  filterPanel.classList.toggle('is-open', open);
  filterBackdrop.classList.toggle('is-open', open);
  if (open) {
    // Reopening reflects the applied choice; dismissing does not silently apply drafts.
    filterPanel.querySelectorAll('input').forEach(input => {
      input.checked = (appliedFilters[input.dataset.category] || []).includes(input.dataset.value);
    });
    updateCount();
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    filterClose.focus();
  } else {
    document.body.style.overflow = previousOverflow;
    filterTrigger.focus();
  }
}

function updateCount() {
  const filters = selectedFilters();
  document.querySelector('#filter-count').textContent = `Найдено изделий: ${cards.filter(card => matches(card, filters)).length}`;
}

const sections = [
  ['Концепция', [...new Set(cards.map(card => card.dataset.concept).filter(Boolean))]],
  ['Категория', [...new Set([...cards.map(card => card.dataset.category).filter(Boolean), 'Колье'])]],
  ['Цена', priceBands]
];
sections.forEach(([name, values], groupIndex) => {
  const group = document.createElement('div');
  group.className = 'ShopDivFilters';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.id = `ShopDivId${name}`;
  toggle.className = 'ShopFiltersTitle';
  toggle.textContent = name;
  toggle.setAttribute('aria-expanded', 'false');
  const list = document.createElement('ul');
  list.id = `ShopPodId${name}`;
  list.className = 'ShopFiltersDivSpisok';
  list.hidden = true;
  toggle.setAttribute('aria-controls', list.id);
  toggle.addEventListener('click', () => {
    list.hidden = !list.hidden;
    toggle.setAttribute('aria-expanded', String(!list.hidden));
  });
  values.forEach((value, index) => {
    const row = document.createElement('li');
    row.className = 'ShopFiltersPodSpisok';
    const box = document.createElement('label');
    box.className = 'customCheckbox';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.className = 'ShopFiltersRadio';
    input.id = `FiltersCheckBox${groupIndex}-${index}`;
    input.dataset.category = name;
    input.dataset.value = value;
    input.addEventListener('change', updateCount);
    box.append(input, document.createElement('span'));
    const label = document.createElement('label');
    label.htmlFor = input.id;
    label.className = 'ShopFiltersItems';
    label.textContent = value;
    row.append(box, label);
    list.append(row);
  });
  group.append(toggle, list);
  document.querySelector('#BockMenuMain').append(group);
});

filterTrigger.hidden = false;
filterTrigger.addEventListener('click', () => setPanel(true));
filterClose.addEventListener('click', () => setPanel(false));
filterBackdrop.addEventListener('click', () => setPanel(false));
filterPanel.addEventListener('keydown', event => {
  if (event.key === 'Escape') setPanel(false);
  if (event.key !== 'Tab') return;
  const focusable = Array.from(filterPanel.querySelectorAll('button,input')).filter(el => el.getClientRects().length);
  const first = focusable[0], last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
document.querySelector('#BockMenuDivBthShow').addEventListener('click', () => {
  appliedFilters = selectedFilters();
  showAll = false;
  renderCatalogue();
  setPanel(false);
});
document.querySelector('#BockMenuBthSbros').addEventListener('click', () => {
  appliedFilters = {};
  filterPanel.querySelectorAll('input').forEach(input => { input.checked = false; });
  showAll = false;
  updateCount();
  renderCatalogue();
  setPanel(false);
});
more.addEventListener('click', () => { showAll = true; renderCatalogue(); });
const initial = (new URLSearchParams(location.search).get('filter') || '').split(',');
filterPanel.querySelectorAll('input').forEach(input => { input.checked = initial.includes(input.dataset.value); });
appliedFilters = selectedFilters();
if (performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
  try {
    const saved = JSON.parse(sessionStorage.getItem('kodee-catalog-state') || 'null');
    if (saved) { appliedFilters = saved.filters || {}; showAll = !!saved.showAll; }
  } catch (_) { /* The catalogue remains usable without storage. */ }
}
window.addEventListener('pagehide', () => {
  try { sessionStorage.setItem('kodee-catalog-state', JSON.stringify({filters: appliedFilters, showAll})); } catch (_) {}
});
renderCatalogue();
