(function () {
  const counters = Array.from(document.querySelectorAll('[data-bounty-count]'));
  const log = document.getElementById('bounty-activity-log');
  if (!counters.length || !log) return;

  const entries = [
    '[+] Critical vulnerability reported - Shopify',
    '[+] XSS discovered - Internal CMS',
    '[+] Privilege escalation found - staging cluster',
    '[+] IDOR chain confirmed - customer portal',
    '[+] SSRF payload validated - API gateway'
  ];

  function animateCounter(el) {
    const target = Number(el.dataset.bountyCount || 0);
    const start = performance.now();

    function step(now) {
      const p = Math.min((now - start) / 1300, 1);
      el.textContent = String(Math.floor(p * target));
      if (p < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
  }

  const observer = new IntersectionObserver((items) => {
    items.forEach((item) => {
      if (!item.isIntersecting) return;
      counters.forEach(animateCounter);
      observer.disconnect();
    });
  }, { threshold: 0.4 });

  observer.observe(counters[0]);

  let idx = 0;
  function pushLog() {
    const row = document.createElement('div');
    row.className = 'bounty-log-entry';
    row.textContent = entries[idx % entries.length];
    log.prepend(row);
    idx += 1;

    while (log.children.length > 8) {
      log.removeChild(log.lastElementChild);
    }
  }

  pushLog();
  setInterval(pushLog, 2800);
})();
