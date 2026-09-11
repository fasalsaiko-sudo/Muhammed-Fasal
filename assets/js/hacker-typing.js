(function () {
  const wrap = document.getElementById('hacker-terminal');
  const out = document.getElementById('terminal-output');
  if (!wrap || !out) return;

  if (sessionStorage.getItem('hackerIntroSeen') === '1') return;

  const script = [
    'Initializing security console...',
    'Loading threat intelligence...',
    'Connecting to darknet nodes...',
    '',
    '> nmap -sV target-server',
    'Scanning open ports...',
    '22/tcp   open  ssh',
    '80/tcp   open  http',
    '443/tcp  open  https',
    '',
    '> running vulnerability scan...',
    'Checking OWASP Top 10...',
    '[OK] SQL Injection: Not detected',
    '[OK] XSS: Not detected',
    '[OK] IDOR: Not detected',
    '',
    'System secure.'
    '',
    'Use Desktop Site.'
  ];

  wrap.classList.add('active');
  let lineIdx = 0;

  function typeLine(text, done) {
    let i = 0;
    const speed = 18 + Math.floor(Math.random() * 40);
    const timer = setInterval(() => {
      out.textContent += text.charAt(i);
      i += 1;
      if (i >= text.length) {
        clearInterval(timer);
        out.textContent += '\n';
        setTimeout(done, 150);
      }
    }, speed);
  }

  function next() {
    if (lineIdx >= script.length) {
      setTimeout(() => {
        wrap.classList.remove('active');
        sessionStorage.setItem('hackerIntroSeen', '1');
      }, 900);
      return;
    }

    typeLine(script[lineIdx], () => {
      lineIdx += 1;
      next();
    });
  }

  next();
})();
