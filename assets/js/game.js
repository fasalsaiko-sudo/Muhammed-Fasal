const quizBank = {
  easy: [
    {
      q: 'Which protocol secures websites?',
      a: [
        { t: 'HTTPS', c: true },
        { t: 'FTP', c: false },
        { t: 'Telnet', c: false },
        { t: 'HTTP', c: false }
      ]
    },
    {
      q: 'What is phishing?',
      a: [
        { t: 'A social engineering scam', c: true },
        { t: 'An encryption method', c: false },
        { t: 'A firewall mode', c: false },
        { t: 'A patching tool', c: false }
      ]
    },
    {
      q: 'Which tool is used for packet analysis?',
      a: [
        { t: 'Wireshark', c: true },
        { t: 'Figma', c: false },
        { t: 'Photoshop', c: false },
        { t: 'VS Code', c: false }
      ]
    },
    {
      q: 'What does VPN primarily provide?',
      a: [
        { t: 'Encrypted tunnel', c: true },
        { t: 'Database backup', c: false },
        { t: 'Faster RAM', c: false },
        { t: 'Email signing', c: false }
      ]
    }
  ],
  medium: [
    {
      q: 'Which OWASP category includes SQL Injection?',
      a: [
        { t: 'Injection', c: true },
        { t: 'Broken Authentication', c: false },
        { t: 'Security Logging', c: false },
        { t: 'Cryptographic Failures', c: false }
      ]
    },
    {
      q: 'Which port does SSH use by default?',
      a: [
        { t: '22', c: true },
        { t: '21', c: false },
        { t: '25', c: false },
        { t: '3389', c: false }
      ]
    },
    {
      q: 'What is least privilege?',
      a: [
        { t: 'Grant only required access', c: true },
        { t: 'Disable all accounts', c: false },
        { t: 'Run all apps as admin', c: false },
        { t: 'Allow password sharing', c: false }
      ]
    },
    {
      q: 'What does ARP map?',
      a: [
        { t: 'IP to MAC', c: true },
        { t: 'Domain to IP', c: false },
        { t: 'MAC to Domain', c: false },
        { t: 'Port to Process', c: false }
      ]
    }
  ],
  hard: [
    {
      q: 'A server allows NOPASSWD on find. Which risk is likely?',
      a: [
        { t: 'Privilege escalation via GTFOBins', c: true },
        { t: 'Only slower disk I/O', c: false },
        { t: 'No practical impact', c: false },
        { t: 'Only UI issue', c: false }
      ]
    },
    {
      q: 'Which control best mitigates token theft from XSS?',
      a: [
        { t: 'HttpOnly cookies and CSP', c: true },
        { t: 'Longer usernames', c: false },
        { t: 'Port knocking', c: false },
        { t: 'Disabling TLS', c: false }
      ]
    },
    {
      q: 'Which metric reflects combined confidentiality, integrity, and availability impact?',
      a: [
        { t: 'CVSS impact subscore', c: true },
        { t: 'Ping latency', c: false },
        { t: 'DNS TTL', c: false },
        { t: 'AES key length', c: false }
      ]
    },
    {
      q: 'Most reliable first step after gaining shell on Linux CTF?',
      a: [
        { t: 'Systematic enumeration', c: true },
        { t: 'Immediate reboot', c: false },
        { t: 'Delete logs', c: false },
        { t: 'Disable firewall', c: false }
      ]
    }
  ]
};

const state = {
  difficulty: 'easy',
  index: 0,
  score: 0,
  streak: 0,
  bestStreak: 0,
  timer: null,
  timeLeft: 0,
  answered: 0,
  correct: 0,
  deck: []
};

const el = {
  intro: document.getElementById('quiz-intro'),
  panel: document.getElementById('quiz-panel'),
  result: document.getElementById('result-section'),
  start: document.getElementById('start-quiz-btn'),
  next: document.getElementById('next-btn'),
  retry: document.getElementById('retry-btn'),
  difficulty: document.getElementById('difficulty'),
  qNo: document.getElementById('question-number'),
  question: document.getElementById('question-text'),
  answers: document.getElementById('answer-buttons'),
  fill: document.getElementById('progress-fill'),
  timer: document.getElementById('timer'),
  score: document.getElementById('score'),
  level: document.getElementById('level'),
  accuracy: document.getElementById('accuracy'),
  bestScore: document.getElementById('best-score'),
  leaderboard: document.getElementById('leaderboard')
};

function beep(freq = 540, ms = 90) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = 'triangle';
  o.frequency.value = freq;
  g.gain.value = 0.02;
  o.connect(g);
  g.connect(ctx.destination);
  o.start();
  o.stop(ctx.currentTime + ms / 1000);
  o.onended = () => ctx.close();
}

function shuffle(arr) {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function readBoard() {
  return JSON.parse(localStorage.getItem('quizBoardV2') || '[]');
}

function writeBoard(row) {
  const board = readBoard();
  board.push(row);
  board.sort((a, b) => b.score - a.score || a.time - b.time);
  const top = board.slice(0, 5);
  localStorage.setItem('quizBoardV2', JSON.stringify(top));
}

function renderBoard() {
  const board = readBoard();
  el.leaderboard.innerHTML = '';
  if (!board.length) {
    el.leaderboard.innerHTML = '<li>No attempts yet.</li>';
    return;
  }

  board.forEach((r, i) => {
    const li = document.createElement('li');
    li.textContent = `#${i + 1} ${r.mode.toUpperCase()} - ${r.score}/${r.total} (${r.acc}%)`;
    el.leaderboard.appendChild(li);
  });
}

function getTimerByDifficulty(mode) {
  if (mode === 'easy') return 20;
  if (mode === 'medium') return 16;
  return 12;
}

function startRound() {
  state.difficulty = el.difficulty.value;
  state.deck = shuffle(quizBank[state.difficulty]);
  state.index = 0;
  state.score = 0;
  state.streak = 0;
  state.bestStreak = 0;
  state.answered = 0;
  state.correct = 0;

  el.intro.classList.add('hidden');
  el.result.classList.add('hidden');
  el.panel.classList.remove('hidden');

  renderQuestion();
}

function clearTimer() {
  if (state.timer) clearInterval(state.timer);
}

function runTimer() {
  clearTimer();
  state.timeLeft = getTimerByDifficulty(state.difficulty);
  el.timer.textContent = `${state.timeLeft}s`;

  state.timer = setInterval(() => {
    state.timeLeft -= 1;
    el.timer.textContent = `${state.timeLeft}s`;
    if (state.timeLeft <= 0) {
      clearTimer();
      lockAnswers(null);
      beep(220, 140);
      setTimeout(nextStep, 500);
    }
  }, 1000);
}

function updateProgress() {
  const total = state.deck.length;
  const current = state.index + 1;
  el.qNo.textContent = `Question ${current} of ${total}`;
  el.fill.style.width = `${(current / total) * 100}%`;
}

function renderQuestion() {
  updateProgress();
  const row = state.deck[state.index];
  el.question.textContent = row.q;
  el.answers.innerHTML = '';

  shuffle(row.a).forEach((ans) => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = ans.t;
    btn.dataset.correct = ans.c ? '1' : '0';
    btn.addEventListener('click', onAnswer);
    li.appendChild(btn);
    el.answers.appendChild(li);
  });

  el.next.classList.add('hidden');
  runTimer();
}

function lockAnswers(selectedButton) {
  const buttons = Array.from(el.answers.querySelectorAll('button'));
  buttons.forEach((b) => {
    b.disabled = true;
    if (b.dataset.correct === '1') b.classList.add('correct');
  });

  if (selectedButton && selectedButton.dataset.correct !== '1') {
    selectedButton.classList.add('wrong');
  }

  el.next.classList.remove('hidden');
}

function onAnswer(e) {
  clearTimer();
  const btn = e.currentTarget;
  const ok = btn.dataset.correct === '1';
  state.answered += 1;

  if (ok) {
    state.score += 1;
    state.correct += 1;
    state.streak += 1;
    state.bestStreak = Math.max(state.bestStreak, state.streak);
    btn.classList.add('correct');
    beep(820, 100);
  } else {
    state.streak = 0;
    beep(220, 120);
  }

  lockAnswers(btn);
}

function nextStep() {
  if (state.index < state.deck.length - 1) {
    state.index += 1;
    renderQuestion();
    return;
  }

  finishQuiz();
}

function finishQuiz() {
  clearTimer();
  el.panel.classList.add('hidden');
  el.result.classList.remove('hidden');

  const total = state.deck.length;
  const acc = Math.round((state.correct / total) * 100);
  const level = acc >= 85 ? 'Elite Analyst' : acc >= 65 ? 'Security Practitioner' : 'Cyber Trainee';

  el.score.textContent = `${state.score}/${total}`;
  el.level.textContent = level;
  el.accuracy.textContent = `${acc}%`;

  const best = Number(localStorage.getItem('bestScoreV2') || 0);
  const nowBest = Math.max(best, state.score);
  localStorage.setItem('bestScoreV2', String(nowBest));
  el.bestScore.textContent = `${nowBest}/${total}`;

  writeBoard({
    mode: state.difficulty,
    score: state.score,
    total,
    acc,
    time: Date.now()
  });
  renderBoard();
}

el.start?.addEventListener('click', startRound);
el.next?.addEventListener('click', nextStep);
el.retry?.addEventListener('click', startRound);

renderBoard();



