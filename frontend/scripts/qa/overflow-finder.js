/**
 * QA 溢出定位：列出当前页面中宽度超出视口的元素（含祖先链），用于定位横向溢出根因。
 * 参数：无（作用于当前页面）。
 */
(() => {
  const vw = window.innerWidth;
  const de = document.documentElement;
  const out = [];
  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    // 超出右侧或左侧
    if (r.right > vw + 1 || r.left < -1) {
      out.push({
        tag: el.tagName,
        cls: (el.className && typeof el.className === 'string' ? el.className : '').slice(0, 60),
        left: Math.round(r.left),
        right: Math.round(r.right),
        w: Math.round(r.width),
        overflowRight: Math.round(r.right - vw),
        scrollW: el.scrollWidth,
        text: (el.textContent || '').trim().slice(0, 30),
      });
    }
  }
  // 只保留“最外层”的若干个（按 right 降序）
  out.sort((a, b) => b.right - a.right);
  return { vw, docScrollW: de.scrollWidth, bodyScrollW: document.body.scrollWidth, count: out.length, top: out.slice(0, 25) };
})()
