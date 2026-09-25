/**
 * QA 深色主题对比度扫描：逐页对可见文本节点计算 WCAG 对比度，返回最低的若干项。
 * 依据：设计文档要求深色下"文字与背景对比度可辨"。低于 3.0 视为可疑（大字号可放宽）。
 */
(() => {
  const parse = (c) => {
    const m = c.match(/[\d.]+/g);
    return m ? m.map(Number) : null;
  };
  const lum = (rgb) => {
    const f = rgb.slice(0, 3).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  };
  const alpha = (c) => (c.length > 3 ? c[3] : 1);
  const over = (src, dst) => {
    const a = alpha(src);
    return [0, 1, 2].map((i) => Math.round(src[i] * a + dst[i] * (1 - a)));
  };
  const effBg = (el) => {
    const layers = [];
    let node = el;
    while (node && node !== document.documentElement) {
      const c = parse(getComputedStyle(node).backgroundColor);
      if (c && (c.length === 3 || c[3] > 0.05)) {
        layers.push(c);
        if (alpha(c) >= 0.95) break;
      }
      node = node.parentElement;
    }
    const rootC = parse(getComputedStyle(document.documentElement).backgroundColor);
    let base = rootC ? rootC.slice(0, 3) : [0, 0, 0];
    if (layers.length && alpha(layers[layers.length - 1]) >= 0.95) base = layers.pop().slice(0, 3);
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
    return base;
  };
  const ratio = (a, b) => {
    const l1 = lum(a);
    const l2 = lum(b);
    const hi = Math.max(l1, l2);
    const lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  };

  const results = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('main *')) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) < 0.5) continue;
    // 仅取"直接包含文本"的元素
    const direct = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!direct) continue;
    const text = (el.textContent || '').trim().slice(0, 24);
    if (!text) continue;
    const fg = parse(s.color);
    if (!fg) continue;
    const bg = effBg(el);
    const fgBlend = fg.length > 3 && fg[3] < 0.95 ? over(fg, bg) : fg;
    const r = ratio(fgBlend, bg);
    const fontSize = parseFloat(s.fontSize);
    const isLarge = fontSize >= 24 || (fontSize >= 18.66 && Number(s.fontWeight) >= 700);
    const key = `${text}|${Math.round(r * 10)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    results.push({
      text,
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 40),
      ratio: Math.round(r * 100) / 100,
      fontSize,
      isLarge,
      color: s.color,
      bg: `rgb(${bg.slice(0, 3).join(',')})`,
    });
  }
  results.sort((a, b) => a.ratio - b.ratio);
  const bad = results.filter((x) => x.ratio < 3 && !x.isLarge);
  return { theme: document.documentElement.dataset.theme, total: results.length, worst: results.slice(0, 12), suspectCount: bad.length, suspects: bad.slice(0, 8) };
})()
