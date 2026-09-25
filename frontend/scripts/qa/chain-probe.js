/**
 * QA 行盒链路检查：定位 .run-list 行溢出的根因（逐级测量祖先与子元素）。
 */
(() => {
  const btn = document.querySelector('.run-list__btn') || document.querySelector('.run-list__row');
  if (!btn) return { error: 'no run-list row found' };
  const cls = (el) => (el && typeof el.className === 'string' ? el.className : '').slice(0, 48);
  const chain = [];
  let el = btn;
  while (el && el !== document.body) {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    chain.push({
      tag: el.tagName,
      cls: cls(el),
      w: Math.round(r.width),
      scrollW: el.scrollWidth,
      display: s.display,
      minWidth: s.minWidth,
      overflowX: s.overflowX,
      gridTemplateColumns: s.gridTemplateColumns,
      flex: s.flex,
    });
    el = el.parentElement;
  }
  const kids = [...btn.children].map((k) => {
    const s = getComputedStyle(k);
    const r = k.getBoundingClientRect();
    return {
      tag: k.tagName,
      cls: cls(k),
      w: Math.round(r.width),
      scrollW: k.scrollWidth,
      flex: s.flex,
      minWidth: s.minWidth,
      overflow: s.overflow,
      whiteSpace: s.whiteSpace,
    };
  });
  return { vw: window.innerWidth, btnText: (btn.textContent || '').trim().slice(0, 40), chain, kids };
})()
