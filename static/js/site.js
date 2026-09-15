// Prev/next buttons for horizontal rails. In RTL the "next" items sit to the
// left, which is the negative scroll direction.
document.querySelectorAll('[data-rail-target]').forEach((button) => {
  const rail = document.getElementById(button.dataset.railTarget);
  if (!rail) return;
  button.addEventListener('click', () => {
    const step = rail.clientWidth * 0.9 * (button.dataset.dir === 'next' ? 1 : -1);
    const rtl = getComputedStyle(rail).direction === 'rtl';
    rail.scrollBy({ left: rtl ? -step : step, behavior: 'smooth' });
  });
});

// Car picker (sport / accessory pages): collapsible on phones.
document.querySelectorAll('.browser__toggle').forEach((button) => {
  const target = document.getElementById(button.getAttribute('aria-controls'));
  button.addEventListener('click', () => {
    const open = button.getAttribute('aria-expanded') !== 'true';
    button.setAttribute('aria-expanded', String(open));
    target.classList.toggle('is-open', open);
  });
});

// Car picker: live search over brand and model names. Arabic ي/ك and
// zero-width non-joiners are normalized so "کوییک" matches however it's typed.
const normalizeName = (text) =>
  text.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/‌/g, ' ').toLowerCase().trim();

document.querySelectorAll('[data-car-search]').forEach((input) => {
  const picker = input.closest('.car-picker');
  const brands = [...picker.querySelectorAll('[data-car-brand]')];
  const empty = picker.querySelector('[data-car-empty]');
  const initiallyOpen = new Map(brands.map((brand) => [brand, brand.querySelector('details').open]));

  input.addEventListener('input', () => {
    const query = normalizeName(input.value);
    let visibleBrands = 0;
    brands.forEach((brand) => {
      const details = brand.querySelector('details');
      const brandMatches = normalizeName(brand.dataset.name).includes(query);
      let modelMatches = false;
      brand.querySelectorAll('[data-car-model]').forEach((model) => {
        const matches = normalizeName(model.dataset.name).includes(query);
        model.hidden = Boolean(query) && !brandMatches && !matches;
        modelMatches ||= Boolean(query) && matches;
      });
      brand.hidden = Boolean(query) && !brandMatches && !modelMatches;
      if (!brand.hidden) visibleBrands += 1;
      // Open brands whose models matched; restore the original state when cleared.
      details.open = query ? modelMatches || details.open : initiallyOpen.get(brand);
    });
    if (empty) empty.hidden = visibleBrands > 0;
  });
});

// Star rating: submit as soon as a star is clicked. Arrow keys also change the
// selection, so keyboard users confirm with the button instead.
document.querySelectorAll('[data-rate-form]').forEach((form) => {
  let usingPointer = false;
  form.addEventListener('pointerdown', () => { usingPointer = true; });
  form.addEventListener('keydown', () => { usingPointer = false; });
  form.querySelectorAll('input[name="stars"]').forEach((input) => {
    input.addEventListener('change', () => { if (usingPointer) form.requestSubmit(); });
  });
});

// Filter form: apply selects and checkboxes as soon as they change.
document.querySelectorAll('form[data-auto-submit]').forEach((form) => {
  form.querySelectorAll('select, input[type="checkbox"]').forEach((field) => {
    field.addEventListener('change', () => form.requestSubmit());
  });
});
