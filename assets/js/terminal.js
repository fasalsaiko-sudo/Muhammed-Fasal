(function () {
  const terminal = document.getElementById('terminal');
  const output = document.getElementById('terminal-nav-output');
  const input = document.getElementById('terminal-input');
  if (!terminal || !output || !input) return;

  const commands = {
    help: () => 'Available commands: help, about, projects, skills, certifications, contact, clear',
    about: () => 'Muhammed Fasal: cybersecurity researcher, VAPT specialist, bug bounty hunter.',
    projects: () => 'Key projects: Hospital Pentest, PrivEsc CTF, Security Tracker. Use writeups.html for full list.',
    skills: () => 'Skills: web pentesting, OWASP testing, vulnerability reporting, automation scripting.',
    certifications: () => 'Azure AI Fundamentals, Cisco CCST Cybersecurity, Junior Penetration Tester.',
    contact: () => 'Email: fasalmuhammad44@gmail.com | LinkedIn: /in/muhammed-fasal-ms/',
    clear: () => 'clear'
  };

  function printLine(text, className) {
    const line = document.createElement('div');
    line.textContent = text;
    if (className) line.className = className;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  function typeLine(text) {
    const line = document.createElement('div');
    output.appendChild(line);
    let i = 0;
    const timer = setInterval(() => {
      line.textContent = text.slice(0, i);
      i += 1;
      output.scrollTop = output.scrollHeight;
      if (i > text.length) clearInterval(timer);
    }, 12);
  }

  printLine('SOC terminal ready. Type help.');

  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const cmd = input.value.trim().toLowerCase();
    if (!cmd) return;

    printLine(`> ${cmd}`);

    if (!commands[cmd]) {
      typeLine('Unknown command. Use help.');
      input.value = '';
      return;
    }

    const result = commands[cmd]();
    if (cmd === 'clear') {
      output.innerHTML = '';
      printLine('Console cleared.');
      input.value = '';
      return;
    }

    if (cmd === 'projects') {
      setTimeout(() => { window.location.href = 'writeups.html'; }, 320);
    }
    if (cmd === 'certifications') {
      setTimeout(() => { window.location.href = 'profile.html#certifications'; }, 320);
    }
    if (cmd === 'about') {
      setTimeout(() => { window.location.href = 'profile.html'; }, 320);
    }
    if (cmd === 'contact') {
      setTimeout(() => { window.location.href = 'index.html#ai-assistant-widget'; }, 320);
    }

    typeLine(result);
    input.value = '';
  });
})();

