const footerToggle = document.querySelector('.footer-navigation-toggle');
const footerNavigation = document.querySelector('#FuterPodListBlockNavig');
const mobileFooter = window.matchMedia('(max-width: 767px)');

function updateFooterLayout() {
    footerNavigation.hidden = mobileFooter.matches;
    footerToggle.setAttribute('aria-expanded', String(!mobileFooter.matches));
}

footerToggle.addEventListener('click', () => {
    const opening = footerNavigation.hidden;
    footerNavigation.hidden = !opening;
    footerToggle.setAttribute('aria-expanded', String(opening));
});
mobileFooter.addEventListener('change', updateFooterLayout);
updateFooterLayout();
