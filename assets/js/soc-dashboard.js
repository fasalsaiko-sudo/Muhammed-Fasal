(function () {
  const feed = document.getElementById('threat-feed');
  if (!feed) return;

  const activeEl = document.getElementById('soc-active-threats');
  const blockedEl = document.getElementById('soc-blocked-attacks');
  const countriesEl = document.getElementById('soc-countries-count');
  const riskEl = document.getElementById('soc-risk-level');

  const countries = ['Germany', 'Russia', 'India', 'USA', 'Brazil', 'Japan', 'UK', 'Canada'];
  const attacks = [
    'SQL Injection attempt blocked',
    'Port scan detected',
    'Suspicious login attempt',
    'Brute force attack prevented',
    'Malware signature detected',
    'Privilege escalation attempt'
  ];
  const severities = ['INFO', 'WARNING', 'CRITICAL'];

  const seenCountries = new Set();
  let active = 3;
  let blocked = 114;

  function ts() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  }

  function updateStats(sev, country) {
    seenCountries.add(country);
    const shift = Math.random() > 0.5 ? 1 : -1;
    active = Math.max(1, active + shift);
    blocked += 1;

    if (sev === 'CRITICAL') riskEl.textContent = 'HIGH';
    else if (sev === 'WARNING') riskEl.textContent = 'MEDIUM';
    else riskEl.textContent = active > 6 ? 'MEDIUM' : 'LOW';

    activeEl.textContent = String(active);
    blockedEl.textContent = String(blocked);
    countriesEl.textContent = String(seenCountries.size);
  }

  function typeEntry(text, sev) {
    const line = document.createElement('div');
    line.className = `feed-line ${sev}`;
    feed.prepend(line);

    let i = 0;
    const timer = setInterval(() => {
      line.textContent = text.slice(0, i);
      i += 1;
      if (i > text.length) clearInterval(timer);
    }, 8);

    while (feed.children.length > 50) {
      feed.removeChild(feed.lastElementChild);
    }
    feed.scrollTop = 0;
  }

  function emit() {
    const sev = severities[Math.floor(Math.random() * severities.length)];
    const country = countries[Math.floor(Math.random() * countries.length)];
    const attack = attacks[Math.floor(Math.random() * attacks.length)];
    const line = `[${ts()}] ${sev} - ${attack} - ${country}`;

    typeEntry(line, sev);
    updateStats(sev, country);

    const delay = 2000 + Math.floor(Math.random() * 3000);
    setTimeout(emit, delay);
  }

  emit();
})();
