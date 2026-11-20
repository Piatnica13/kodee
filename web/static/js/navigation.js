function fadePage() {
    document.body.classList.add('page-leaving');
}

(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let pendingNavigation;

    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.defaultPrevented || event.button !== 0 ||
            event.ctrlKey || event.metaKey || event.shiftKey || event.altKey ||
            link.hasAttribute('download') || link.hasAttribute('data-instant-navigation') ||
            (link.target && link.target.toLowerCase() !== '_self') || reducedMotion.matches) return;

        const destination = new URL(link.href, window.location.href);
        if (!['http:', 'https:'].includes(destination.protocol) ||
            destination.origin !== window.location.origin ||
            (destination.pathname === window.location.pathname &&
             destination.search === window.location.search && destination.hash)) return;

        event.preventDefault();
        if (pendingNavigation) return;

        (window.inShowPage || fadePage)();
        pendingNavigation = setTimeout(() => window.location.assign(destination.href), 500);
    });

    window.addEventListener('pageshow', () => {
        clearTimeout(pendingNavigation);
        pendingNavigation = undefined;
        document.body.classList.remove('page-leaving');
    });
})();
