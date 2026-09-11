(function () {
  const toggle = document.getElementById('ai-toggle');
  const closeBtn = document.getElementById('ai-close');
  const win = document.getElementById('ai-window');
  const form = document.getElementById('ai-form');
  const input = document.getElementById('ai-input');
  const messages = document.getElementById('ai-messages');
  if (!toggle || !closeBtn || !win || !form || !input || !messages) return;

  const OPENAI_API_KEY = window.OPENAI_API_KEY || '';
  const MODEL = 'gpt-4o-mini';

  const fallbackAnswers = [
    {
      keys: ['sql injection', 'sqli'],
      text: 'SQL injection testing: identify dynamic query points, use boolean/time-based payloads, verify DB behavior changes, then recommend parameterized queries and strict input handling.'
    },
    {
      keys: ['idor'],
      text: 'IDOR testing: change numeric/UUID object references across accounts, validate missing authorization checks, and document impact with secure direct object controls.'
    },
    {
      keys: ['xss'],
      text: 'XSS testing: check reflected/stored vectors, context-break payloads, CSP bypass opportunities, and propose output encoding plus strong CSP as remediation.'
    },
    {
      keys: ['recon', 'tools'],
      text: 'Recon stack: amass/subfinder for asset discovery, httpx for probing, nuclei for templated checks, and burp for manual verification.'
    },
    {
      keys: ['bug bounty'],
      text: 'Bug bounty tip: focus on attack chains and business-impact clarity. High-value reports combine reproducibility, impact proof, and remediation guidance.'
    }
  ];

  function addMessage(text, role) {
    const row = document.createElement('div');
    row.className = `ai-msg ${role}`;
    row.textContent = text;
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
  }

  function typeMessage(text, role) {
    const row = document.createElement('div');
    row.className = `ai-msg ${role}`;
    messages.appendChild(row);

    let i = 0;
    const timer = setInterval(() => {
      row.textContent = text.slice(0, i);
      i += 1;
      messages.scrollTop = messages.scrollHeight;
      if (i > text.length) clearInterval(timer);
    }, 10);
  }

  function localAnswer(q) {
    const text = q.toLowerCase();
    const hit = fallbackAnswers.find((item) => item.keys.some((k) => text.includes(k)));
    return hit ? hit.text : 'Ask about SQL injection, IDOR, XSS, recon tools, or bug bounty strategy.';
  }

  async function askOpenAI(prompt) {
    const resp = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${OPENAI_API_KEY}`
      },
      body: JSON.stringify({
        model: MODEL,
        messages: [
          { role: 'system', content: 'You are an AI pentesting assistant. Give concise, ethical, defensive security guidance and safe testing methodology.' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.4
      })
    });

    if (!resp.ok) throw new Error('OpenAI request failed');
    const data = await resp.json();
    return data.choices?.[0]?.message?.content || 'No response generated.';
  }

  addMessage('AI Pentesting Assistant online. Ask: "Explain SQL injection" or "How to test IDOR".', 'bot');

  toggle.addEventListener('click', () => {
    win.classList.toggle('open');
    win.setAttribute('aria-hidden', win.classList.contains('open') ? 'false' : 'true');
  });

  closeBtn.addEventListener('click', () => {
    win.classList.remove('open');
    win.setAttribute('aria-hidden', 'true');
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;

    addMessage(q, 'user');
    input.value = '';

    if (!OPENAI_API_KEY) {
      typeMessage(localAnswer(q), 'bot');
      return;
    }

    typeMessage('Analyzing request...', 'bot');
    try {
      const ans = await askOpenAI(q);
      messages.lastElementChild.remove();
      typeMessage(ans, 'bot');
    } catch (err) {
      messages.lastElementChild.remove();
      typeMessage(`Live API unavailable. Fallback: ${localAnswer(q)}`, 'bot');
    }
  });
})();
