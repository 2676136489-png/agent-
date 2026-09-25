/**
 * QA 浏览器探针（严过关独立取证）— 在页面上下文执行，返回 JSON。
 * 覆盖：每页横向溢出 / 导航可见性 / 首屏主操作可见性 / 首页易用性。
 */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const de = document.documentElement;
  const pages = ['概览', '深度研究', '研究规划', '智能体', '知识库', '教程', '研究报告', '效果评估', '系统设置'];

  const isVisible = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const firstScreen = (el) => {
    if (!isVisible(el)) return false;
    const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.top < window.innerHeight;
  };
  const rectOf = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const clickNav = (label) => {
    const b = [...document.querySelectorAll('.nav-link')].find((x) => x.textContent.trim() === label);
    if (!b) return false;
    b.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    return true;
  };
  const navState = () => {
    const items = [...document.querySelectorAll('.nav-menu .nav-link')];
    const vis = items.filter(isVisible);
    const navInner = document.querySelector('.nav-inner');
    return {
      menuTotal: items.length,
      menuVisible: vis.length,
      menuVisibleLabels: vis.map((x) => x.textContent.trim()),
      coreVisible: items.filter((x) => x.dataset.navCore === 'true' && isVisible(x)).length,
      nonCoreVisible: items.filter((x) => x.dataset.navCore === 'false' && isVisible(x)).length,
      moreBtnVisible: isVisible(document.querySelector('.nav-more__btn')),
      toggleVisible: isVisible(document.querySelector('.nav-toggle')),
      drawerInDom: !!document.querySelector('.nav-drawer'),
      navInnerScrollW: navInner ? navInner.scrollWidth : null,
      navInnerW: navInner ? Math.round(navInner.getBoundingClientRect().width) : null,
    };
  };
  const primary = (label) => {
    const main = document.querySelector('main');
    if (!main) return null;
    if (label === '概览') {
      const p = main.querySelector('.hero-actions .button--primary');
      const h1 = main.querySelector('h1');
      const lede = main.querySelector('.hero-lede');
      const grid = main.querySelector('.entry-grid');
      const cards = [...main.querySelectorAll('.card--entry')];
      const primaryCard = main.querySelector('.card--primary');
      const badge = main.querySelector('.card--primary .card__badge');
      return {
        primaryButton: { text: p?.textContent.trim(), ...rectOf(p), firstScreen: firstScreen(p) },
        h1: { text: (h1?.textContent || '').trim().slice(0, 40), firstScreen: firstScreen(h1) },
        ledeFirstScreen: firstScreen(lede),
        entryGrid: { ...rectOf(grid), firstScreen: firstScreen(grid) },
        entryCardCount: cards.length,
        entryCardsFirstScreen: cards.filter(firstScreen).length,
        primaryCardBadge: badge ? badge.textContent.trim() : null,
        primaryCardBorderColor: primaryCard ? getComputedStyle(primaryCard).borderColor : null,
        secondaryCardBorderColor: cards[1] ? getComputedStyle(cards[1]).borderColor : null,
      };
    }
    if (['教程', '研究报告', '效果评估', '系统设置'].includes(label)) return null;
    let el = main.querySelector('button.button--primary');
    if (label === '知识库') el = main.querySelector('.file-field');
    return { tag: el ? el.tagName : null, text: (el?.textContent || '').trim().slice(0, 24), ...rectOf(el), firstScreen: firstScreen(el) };
  };

  const out = { viewport: { w: window.innerWidth, h: window.innerHeight }, navInit: navState(), pages: [] };
  for (const p of pages) {
    const clicked = clickNav(p);
    await sleep(340);
    out.pages.push({
      page: p,
      clicked,
      activeTitle: (document.querySelector('main .panel__title, main h1')?.textContent || '').trim().slice(0, 40),
      scrollW: de.scrollWidth,
      innerW: window.innerWidth,
      overflowPx: de.scrollWidth - window.innerWidth,
      bodyScrollW: document.body.scrollWidth,
      primary: primary(p),
    });
  }
  return out;
})()
