const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Header: soft shadow once the page scrolls under it.
const header = document.querySelector('[data-header]');
if (header) {
  const updateHeader = () => header.classList.toggle('is-scrolled', window.scrollY > 4);
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });
}

// Sections marked data-reveal fade in as they enter the viewport. CSS only
// hides them under html.js, so without this script they simply show.
// A plain scroll check (a handful of elements) rather than IntersectionObserver,
// so a section can never stay hidden because an observer callback didn't run.
// Anything above the fold line counts, including sections jumped past via #links.
const pendingReveals = new Set(document.querySelectorAll('[data-reveal]'));
const revealInView = () => {
  const foldLine = window.innerHeight * 0.92;
  pendingReveals.forEach((element) => {
    if (element.getBoundingClientRect().top >= foldLine) return;
    element.classList.add('is-visible');
    pendingReveals.delete(element);
  });
  if (!pendingReveals.size) {
    window.removeEventListener('scroll', revealInView);
    window.removeEventListener('resize', revealInView);
  }
};
if (prefersReducedMotion) {
  pendingReveals.forEach((element) => element.classList.add('is-visible'));
} else if (pendingReveals.size) {
  revealInView();
  window.addEventListener('scroll', revealInView, { passive: true });
  window.addEventListener('resize', revealInView, { passive: true });
}

// Images marked data-fade sit on a shimmer placeholder until they load.
document.querySelectorAll('img[data-fade]').forEach((image) => {
  const show = () => image.classList.add('is-loaded');
  if (image.complete) {
    show();
  } else {
    image.addEventListener('load', show, { once: true });
    image.addEventListener('error', show, { once: true });
  }
});

// Bottom sheets (<dialog class="sheet">). Triggers are real links, so where
// <dialog> isn't supported they keep their own behaviour (e.g. tel:).
document.querySelectorAll('[data-sheet-open]').forEach((trigger) => {
  const sheet = document.getElementById(trigger.dataset.sheetOpen);
  if (!sheet || typeof sheet.showModal !== 'function') return;
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    sheet.showModal();
  });
});
document.querySelectorAll('dialog.sheet').forEach((sheet) => {
  // The dialog element itself is only the target when the backdrop is tapped.
  sheet.addEventListener('click', (event) => { if (event.target === sheet) sheet.close(); });
  sheet.querySelectorAll('[data-sheet-close]').forEach((button) => {
    button.addEventListener('click', () => sheet.close());
  });
});

// Prev/next buttons for horizontal rails. In RTL the "next" items sit to the
// left, which is the negative scroll direction.
document.querySelectorAll('[data-rail-target]').forEach((button) => {
  const rail = document.getElementById(button.dataset.railTarget);
  if (!rail) return;
  button.addEventListener('click', () => {
    const step = rail.clientWidth * 0.9 * (button.dataset.dir === 'next' ? 1 : -1);
    const rtl = getComputedStyle(rail).direction === 'rtl';
    rail.scrollBy({ left: rtl ? -step : step, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
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

// Quantity steppers next to a number input (product page).
document.querySelectorAll('[data-qty-step]').forEach((button) => {
  const input = button.parentElement.querySelector('input[type="number"]');
  if (!input) return;
  button.addEventListener('click', () => {
    const min = Number(input.min || 1);
    const max = input.max ? Number(input.max) : Infinity;
    const next = Math.min(max, Math.max(min, (Number(input.value) || min) + Number(button.dataset.qtyStep)));
    input.value = String(next);
  });
});

// Order tracking: submit in place and show the result under the form (homepage
// sheet and tracking page). Without this script the form posts to the full page.
document.querySelectorAll('[data-track-form]').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    const result = form.parentElement.querySelector('[data-track-result]');
    if (!result || !window.fetch) return;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    form.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch' },
      });
      if (!response.ok) throw new Error(String(response.status));
      result.outerHTML = await response.text();
    } catch (error) {
      form.submit();
    } finally {
      button.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });
});

// Destructive actions (e.g. deleting an address) ask first.
document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// Filter form: apply selects and checkboxes as soon as they change.
document.querySelectorAll('form[data-auto-submit]').forEach((form) => {
  form.querySelectorAll('select, input[type="checkbox"]').forEach((field) => {
    field.addEventListener('change', () => form.requestSubmit());
  });
});
