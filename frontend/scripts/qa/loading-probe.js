(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  if (!window.__qaOrigFetch) window.__qaOrigFetch = window.fetch;
  window.fetch = (...a) => new Promise((res) => setTimeout(() => res(window.__qaOrigFetch(...a)), 8000));
  const nav = (label) => {
    const b = [...document.querySelectorAll('.nav-link')].find((x) => x.textContent.trim() === label);
    b.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  };
  const out = [];
  for (const p of ['研究报告', '知识库', '效果评估', '深度研究']) {
    nav(p);
    await sleep(200);
    out.push({
      page: p,
      loading: !!document.querySelector('.state-loading'),
      loadingLabel: document.querySelector('.state-loading__label')?.textContent.trim() || null,
      skeletons: document.querySelectorAll('.skeleton').length,
      misleadingEmpty: !!document.querySelector('.state-empty'),
    });
  }
  window.fetch = window.__qaOrigFetch;
  return out;
})()
