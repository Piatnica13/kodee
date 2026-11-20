(() => {
    const panel = document.getElementById('cookie-preferences');
    const storageKey = 'kodee-cookie-choice-v1';
    let choice;
    let analyticsScript;
    let counterStarted = false;
    const counter = Number(panel.dataset.metrika);

    // On phones, dock only where the banner leaves page controls accessible.
    // Otherwise its normal place is after the footer.
    const phone = window.matchMedia('(max-width: 767px)');
    function placePanel() {
        if (!phone.matches || panel.hidden) return;
        const top = window.innerHeight - panel.offsetHeight;
        const controls = document.querySelectorAll('a[href], button, input, select, textarea');
        const overlaps = Array.from(controls).some(control => {
            if (panel.contains(control)) return false;
            const rect = control.getBoundingClientRect();
            return rect.width && rect.height && rect.bottom > top && rect.top < innerHeight &&
                rect.right > 0 && rect.left < innerWidth;
        });
        panel.classList.toggle('cookie-in-flow', overlaps);
    }
    let frame;
    function schedulePlacement() {
        if (panel.hidden || frame) return;
        frame = requestAnimationFrame(() => {
            frame = null;
            placePanel();
        });
    }
    window.addEventListener('scroll', schedulePlacement, {passive: true});
    window.addEventListener('resize', schedulePlacement);
    new ResizeObserver(schedulePlacement).observe(panel);

    function readChoice() {
        try { return localStorage.getItem(storageKey); }
        catch (_) { return null; }
    }

    function startAnalytics() {
        if (!counter || counterStarted) return;
        window.ym = window.ym || function () {
            (window.ym.a ||= []).push(arguments);
        };
        window.ym.l = Date.now();
        if (analyticsScript) {
            if (analyticsScript.dataset.loaded) analyticsScript.onload();
            return;
        }
        analyticsScript = document.createElement('script');
        analyticsScript.src = 'https://mc.yandex.ru/metrika/tag.js';
        analyticsScript.referrerPolicy = 'no-referrer';
        analyticsScript.onload = () => {
            analyticsScript.dataset.loaded = '1';
            if (choice !== 'analytics' || readChoice() !== 'analytics' || counterStarted ||
                typeof window.ym !== 'function') return;
            window.ym(counter, 'init', {
                defer: true, clickmap: false, trackLinks: false, webvisor: false,
                accurateTrackBounce: false, ecommerce: false, trackHash: false, sendTitle: false,
                url: location.origin + location.pathname, referrer: '',
            });
            counterStarted = true;
            window.ym(counter, 'hit', location.origin + location.pathname, {referer: ''});
        };
        document.head.append(analyticsScript);
    }

    function apply(next) {
        choice = next;
        panel.hidden = next === 'necessary' || next === 'analytics';
        placePanel();
        if (next === 'analytics') {
            startAnalytics();
        } else if (counterStarted) {
            const instance = window['yaCounter' + counter];
            if (typeof instance?.destruct === 'function') instance.destruct();
            else window.ym(counter, 'destruct');
            counterStarted = false;
        }
    }

    document.querySelectorAll('[data-cookie-settings]').forEach(button => {
        button.hidden = false;
        button.addEventListener('click', event => {
            event.preventDefault();
            panel.hidden = false;
            placePanel();
            panel.querySelector('button').focus();
        });
    });
    panel.querySelectorAll('[data-cookie-choice]').forEach(button => {
        button.addEventListener('click', () => {
            // Fail closed if this browser cannot save a consent choice.
            try { localStorage.setItem(storageKey, button.dataset.cookieChoice); }
            catch (_) { apply('necessary'); return; }
            apply(button.dataset.cookieChoice);
        });
    });
    window.addEventListener('storage', event => {
        if (event.key === storageKey || event.key === null) apply(readChoice());
    });
    window.addEventListener('pageshow', () => apply(readChoice()));
    apply(readChoice());
})();
