(() => {
  const form = document.querySelector('#individual-request');

  const coinFields = document.querySelector('#coin-fields');
  const otherFields = document.querySelector('#other-fields');
  const secondSide = document.querySelector('#side-two-field');
  const error = document.querySelector('#request-error');
  const initialSide = new URLSearchParams(location.search).get('side');
  if (initialSide === 'one' || initialSide === 'two') form.querySelector(`input[name="side"][value="${initialSide}"]`).checked = true;
  function updateForm() {
    const isCoin = form.elements.kind.value === 'coin';
    coinFields.hidden = !isCoin;
    otherFields.hidden = isCoin;
    secondSide.hidden = form.elements.side.value !== 'two';
    error.hidden = true;
  }
  form.addEventListener('change', updateForm);
  form.addEventListener('input', () => { error.hidden = true; });
  updateForm();
  form.addEventListener('submit', event => {
    event.preventDefault();
    const value = id => document.getElementById(id).value.trim();
    const isCoin = form.elements.kind.value === 'coin';
    const two = form.elements.side.value === 'two';
    const oneText = value('side-one'), twoText = value('side-two'), symbol = value('symbol');
    const idea = value('other-idea');
    if (isCoin ? !(oneText || (two && twoText) || symbol) : !idea) {
      error.textContent = isCoin ? 'Напиши текст или опиши символ, рисунок либо пожелания.' : 'Расскажи немного о своей идее.';
      error.hidden = false;
      (isCoin ? document.getElementById('side-one') : document.getElementById('other-idea')).focus();
      return;
    }
    const lines = [];
    if (isCoin) {
      lines.push('Здравствуйте! Хочу заказать гравировку на монетке.', `Гравировка: ${two ? 'с двух сторон' : 'с одной стороны'}`);
      if (oneText) lines.push(`Первая сторона: ${oneText}`);
      if (two && twoText) lines.push(`Вторая сторона: ${twoText}`);
      if (symbol) lines.push(`Пожелания: ${symbol}`);
      if (value('example-choice')) lines.push(`Понравившийся пример: ${value('example-choice')}`);
    } else {
      lines.push('Здравствуйте! Хочу обсудить индивидуальное украшение.', `Идея: ${idea}`);
      if (value('other-wishes')) lines.push(`Пожелания: ${value('other-wishes')}`);
    }
    const chat = new URL(form.dataset.whatsappUrl);
    chat.searchParams.set('text', lines.join('\n'));
    const link = document.createElement('a');
    link.href = chat.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.click();
  });
  form.querySelector('.request-submit').disabled = false;
})();
