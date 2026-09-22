/*
 * Browser install UI. A manifest can make a page installable in modern Chrome
 * without a service worker; Safari still requires its own Share-sheet flow.
 */
(function () {
  'use strict';

  const OFFER_KEY = 'mostkultura.installOffer.v1';
  const STATE_KEY = 'mostkultura.installState.v1';
  const offer = document.getElementById('installOffer');
  const action = document.getElementById('installAction');
  const dismiss = document.getElementById('installDismiss');
  const guideToggle = document.getElementById('installGuideToggle');
  const guide = document.getElementById('installGuide');
  const error = document.getElementById('installError');
  const reopen = document.getElementById('installReopen');
  const heading = document.getElementById('installOfferTitle');
  if (!offer || !action || !dismiss || !guideToggle || !guide || !error || !reopen || !heading) return;

  const ua = navigator.userAgent || '';
  const isIOS = /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(ua);
  // These in-app browsers do not offer a reliable homescreen flow.
  const isInAppBrowser = /FBAN|FBAV|Instagram|Line\/|Twitter|Snapchat|TikTok|; wv\)|GSA\//i.test(ua);
  const params = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.replace(/^#/, ''));
  const isEmbed = params.get('embed') === '1' || hash.has('embed') || window.self !== window.top;
  const modes = ['standalone', 'minimal-ui', 'fullscreen'].map(mode =>
    window.matchMedia ? window.matchMedia('(display-mode: ' + mode + ')') : null
  ).filter(Boolean);
  const isStandalone = () => Boolean(navigator.standalone) || modes.some(query => query.matches);

  let memory = Object.create(null);
  let deferredPrompt = null;
  let promptInUse = false;
  let nativeFailure = false;
  let guideVisible = false;

  function stored(key) {
    try {
      const value = localStorage.getItem(key);
      if (value) return value;
    } catch (_) { /* Continue with a per-session fallback. */ }
    try {
      const value = sessionStorage.getItem(key);
      if (value) return value;
    } catch (_) { /* Memory remains available for this page. */ }
    return memory[key] || '';
  }
  function store(key, value) {
    memory[key] = value;
    try { localStorage.setItem(key, value); return; }
    catch (_) { /* Private browsing can deny persistent storage. */ }
    try { sessionStorage.setItem(key, value); } catch (_) { /* Memory remains for this page. */ }
  }
  function hiddenContext() { return isEmbed || isInAppBrowser || isStandalone(); }
  function canOfferManually() { return isIOS || isAndroid; }
  function isInstalled() { return stored(STATE_KEY) === 'installed'; }
  function isFirstOffer() { return !stored(OFFER_KEY); }
  function markShown() { store(OFFER_KEY, 'shown'); }
  function clearError() { error.hidden = true; error.textContent = ''; }
  function scrollToOffer() {
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    offer.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' });
  }
  function updateControls() {
    if (promptInUse) {
      action.disabled = true;
      action.dataset.mode = 'pending';
      return;
    }
    const nativeAvailable = Boolean(deferredPrompt);
    if (nativeAvailable) {
      action.textContent = isAndroid ? 'Přidat na plochu' : 'Nainstalovat';
      action.dataset.mode = 'native';
      action.disabled = promptInUse;
      action.removeAttribute('aria-controls');
      action.removeAttribute('aria-expanded');
      guideToggle.hidden = !canOfferManually();
    } else if (isIOS) {
      action.textContent = 'Jak na to';
      action.dataset.mode = 'guide';
      action.disabled = false;
      action.setAttribute('aria-controls', 'installGuide');
      action.setAttribute('aria-expanded', String(guideVisible));
      guideToggle.hidden = true;
    } else if (isAndroid) {
      action.textContent = 'Jak na to';
      action.dataset.mode = 'guide';
      action.disabled = false;
      action.setAttribute('aria-controls', 'installGuide');
      action.setAttribute('aria-expanded', String(guideVisible));
      guideToggle.hidden = true;
    } else {
      action.textContent = 'Nainstalovat';
      action.dataset.mode = 'unavailable';
      action.disabled = nativeFailure || promptInUse;
      action.removeAttribute('aria-controls');
      action.removeAttribute('aria-expanded');
      guideToggle.hidden = true;
    }
  }
  function guideMarkup() {
    if (isIOS) {
      return '<h3 class="install-guide-title">Přidání na iPhonu nebo iPadu</h3><ol><li>Otevřete Sdílet (případně nejdřív nabídku …).</li><li>Zvolte Přidat na plochu.</li><li>Zapněte Otevřít jako webovou aplikaci, pokud je dostupné, a potvrďte Přidat.</li></ol>';
    }
    return '<h3 class="install-guide-title">Přidání v Androidu</h3><ol><li>Otevřete nabídku prohlížeče (⋮).</li><li>Vyberte Přidat na plochu nebo Nainstalovat aplikaci.</li><li>Potvrďte přidání.</li></ol>';
  }
  function setGuide(show) {
    guideVisible = show;
    guideToggle.setAttribute('aria-expanded', String(show));
    if (action.dataset.mode === 'guide') action.setAttribute('aria-expanded', String(show));
    guide.hidden = !show;
    if (show) guide.innerHTML = guideMarkup();
  }
  function setFooterVisible() {
    reopen.hidden = hiddenContext() || isInstalled() || offer.hidden === false || !stored(OFFER_KEY) ||
      !(canOfferManually() || deferredPrompt);
  }
  function hideOffer({ focusFallback = false } = {}) {
    const focusedInside = offer.contains(document.activeElement);
    offer.hidden = true;
    clearError();
    setFooterVisible();
    if (focusFallback && focusedInside) {
      const target = document.getElementById('sourcesBtn') || document.getElementById('search');
      if (target) target.focus({ preventScroll: true });
    }
  }
  function showOffer({ manual = false, focus = false } = {}) {
    if (hiddenContext() || isInstalled() || document.visibilityState !== 'visible') return false;
    if (!manual && !isFirstOffer()) return false;
    if (!canOfferManually() && !deferredPrompt) return false;
    updateControls();
    offer.hidden = false;
    markShown();
    setFooterVisible();
    if (focus) {
      heading.focus({ preventScroll: true });
      scrollToOffer();
    }
    return true;
  }
  function installed() {
    store(STATE_KEY, 'installed');
    deferredPrompt = null;
    hideOffer({ focusFallback: true });
    reopen.hidden = true;
  }
  function dismissed() {
    store(STATE_KEY, 'dismissed');
    hideOffer({ focusFallback: true });
  }
  async function useNativePrompt() {
    const event = deferredPrompt;
    if (!event || promptInUse) return;
    promptInUse = true;
    deferredPrompt = null; // Chromium events can be used only once.
    updateControls();
    try {
      await event.prompt();
      const choice = await event.userChoice;
      if (choice && choice.outcome === 'accepted') installed();
      else dismissed();
    } catch (_) {
      // Keep the card truthful. A later beforeinstallprompt can enable it again.
      nativeFailure = true;
      error.textContent = canOfferManually()
        ? 'Instalační nabídku se nepodařilo otevřít. Můžete pokračovat podle návodu.'
        : 'Instalační nabídku se nepodařilo otevřít. Zkuste instalaci z nabídky prohlížeče.';
      error.hidden = false;
      if (canOfferManually()) setGuide(true);
    } finally {
      promptInUse = false;
      updateControls();
    }
  }

  action.addEventListener('click', () => {
    clearError();
    if (action.dataset.mode === 'native') useNativePrompt();
    else setGuide(true);
  });
  guideToggle.addEventListener('click', () => setGuide(!guideVisible));
  dismiss.addEventListener('click', dismissed);
  reopen.addEventListener('click', () => showOffer({ manual: true, focus: true }));

  window.addEventListener('beforeinstallprompt', event => {
    // Suppress the browser's automatic mini-infobar; installation stays opt-in.
    event.preventDefault();
    deferredPrompt = event;
    promptInUse = false;
    nativeFailure = false;
    if (hiddenContext() || isInstalled()) return;
    updateControls();
    setFooterVisible();
    // Android may already show its manual card; retain any open guide on upgrade.
    if (offer.hidden && isFirstOffer() && document.visibilityState === 'visible') showOffer();
  });
  window.addEventListener('appinstalled', installed);
  modes.forEach(query => {
    const onChange = () => { if (isStandalone()) installed(); };
    if (query.addEventListener) query.addEventListener('change', onChange);
    else if (query.addListener) query.addListener(onChange);
  });

  if (isStandalone()) {
    installed();
    return;
  }
  if (isEmbed || isInAppBrowser || isInstalled()) {
    offer.hidden = true;
    reopen.hidden = true;
    return;
  }
  setFooterVisible();
  // iOS and Android have a useful manual flow before Chromium offers its event.
  if (canOfferManually() && isFirstOffer()) {
    // Short delay lets the generated page finish its first paint without stealing focus.
    window.setTimeout(() => showOffer(), isIOS ? 120 : 0);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && isFirstOffer()) showOffer();
  });
}());
