const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function qs(sel, root = document) {
  return root.querySelector(sel);
}

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function initNav() {
  const menu = qs('#menuToggle');
  const navLinks = qs('#navLinks');
  if (!menu || !navLinks) return;

  menu.addEventListener('click', () => navLinks.classList.toggle('open'));
  qsa('a', navLinks).forEach((link) => {
    link.addEventListener('click', () => navLinks.classList.remove('open'));
  });

  const pathname = location.pathname.split('/').pop() || 'index.html';
  qsa('a', navLinks).forEach((a) => {
    const href = a.getAttribute('href');
    if (href === pathname) a.classList.add('active');
  });
}

function initReveal() {
  const items = qsa('.reveal');
  if (!items.length) return;

  if (window.gsap && window.ScrollTrigger && !prefersReduced) {
    gsap.registerPlugin(ScrollTrigger);
    items.forEach((el) => {
      gsap.fromTo(
        el,
        { y: 28, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.6,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: el,
            start: 'top 86%'
          }
        }
      );
    });
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  items.forEach((item) => observer.observe(item));
}

function initTyping() {
  const el = qs('[data-typing]');
  if (!el) return;

  const phrases = [
    'Cybersecurity Researcher',
    'VAPT Specialist',
    'Bug Bounty Hunter',
    'Security Trainer'
  ];

  let phraseIndex = 0;
  let charIndex = 0;
  let deleting = false;

  function tick() {
    const current = phrases[phraseIndex];
    el.textContent = current.slice(0, charIndex);

    if (!deleting) charIndex += 1;
    if (deleting) charIndex -= 1;

    if (charIndex === current.length + 1) {
      deleting = true;
      setTimeout(tick, 900);
      return;
    }

    if (charIndex === 0 && deleting) {
      deleting = false;
      phraseIndex = (phraseIndex + 1) % phrases.length;
    }

    setTimeout(tick, deleting ? 45 : 95);
  }

  tick();
}

function initCounters() {
  const counters = qsa('[data-count]');
  if (!counters.length) return;

  const run = (counter) => {
    const target = Number(counter.dataset.count || 0);
    const start = performance.now();
    const duration = 1400;

    function animate(now) {
      const progress = Math.min((now - start) / duration, 1);
      const value = Math.floor(progress * target);
      counter.textContent = value.toString();
      if (progress < 1) requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          run(entry.target);
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.55 }
  );

  counters.forEach((counter) => observer.observe(counter));
}

function initCursor() {
  if (window.innerWidth < 1024) return;

  const dot = qs('.cursor-dot');
  const ring = qs('.cursor-ring');
  if (!dot || !ring) return;

  let x = window.innerWidth / 2;
  let y = window.innerHeight / 2;
  let rx = x;
  let ry = y;

  window.addEventListener('mousemove', (e) => {
    x = e.clientX;
    y = e.clientY;
    dot.style.left = `${x}px`;
    dot.style.top = `${y}px`;
  });

  function smooth() {
    rx += (x - rx) * 0.15;
    ry += (y - ry) * 0.15;
    ring.style.left = `${rx}px`;
    ring.style.top = `${ry}px`;
    requestAnimationFrame(smooth);
  }
  smooth();

  qsa('a, button, .project-card, .cert-flip').forEach((item) => {
    item.addEventListener('mouseenter', () => ring.classList.add('hover'));
    item.addEventListener('mouseleave', () => ring.classList.remove('hover'));
  });

  window.addEventListener('mousedown', () => {
    ring.classList.remove('click');
    void ring.offsetWidth;
    ring.classList.add('click');
  });
}

function initTilt() {
  if (prefersReduced) return;
  qsa('.project-card').forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left - rect.width / 2) / rect.width;
      const y = (e.clientY - rect.top - rect.height / 2) / rect.height;
      card.style.transform = `rotateX(${(-y * 10).toFixed(2)}deg) rotateY(${(x * 10).toFixed(2)}deg)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = 'rotateX(0deg) rotateY(0deg)';
    });
  });
}

function initProjectFilters() {
  const filters = qsa('[data-filter]');
  if (!filters.length) return;

  const cards = qsa('[data-project-category]');
  filters.forEach((btn) => {
    btn.addEventListener('click', () => {
      filters.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const key = btn.dataset.filter;
      cards.forEach((card) => {
        const visible = key === 'all' || card.dataset.projectCategory === key;
        card.style.display = visible ? '' : 'none';
      });
    });
  });
}

function initModal() {
  const modal = qs('#globalModal');
  if (!modal) return;
  const close = qs('.modal-close', modal);
  const title = qs('#modalTitle', modal);
  const body = qs('#modalBody', modal);

  qsa('[data-modal-title]').forEach((btn) => {
    btn.addEventListener('click', () => {
      title.textContent = btn.dataset.modalTitle;
      if (btn.dataset.modalImage) {
        body.innerHTML = `<img src="${btn.dataset.modalImage}" alt="Preview" loading="lazy" style="width:100%;border-radius:12px;" />`;
      } else {
        body.textContent = btn.dataset.modalBody || '';
      }
      modal.classList.add('open');
    });
  });

  close?.addEventListener('click', () => modal.classList.remove('open'));
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('open');
  });
}

function initChatbot() {
  const root = qs('.chatbot');
  if (!root) return;

  const toggle = qs('.chat-toggle', root);
  const windowEl = qs('.chat-window', root);
  const close = qs('.close-chat', root);
  const body = qs('.chat-body', root);
  const form = qs('.chat-form', root);
  const input = qs('#chatInput', root);

  const send = (text, role = 'bot') => {
    const msg = document.createElement('div');
    msg.className = `chat-msg ${role}`;
    msg.textContent = text;
    body.appendChild(msg);
    body.scrollTop = body.scrollHeight;
  };

  const answer = (q) => {
    const text = q.toLowerCase();
    if (text.includes('who is') || text.includes('muhammed fasal')) {
      return 'Muhammed Fasal is a cybersecurity researcher, VAPT specialist, and bug bounty hunter focused on web and infrastructure security.';
    }
    if (text.includes('services') || text.includes('offer')) {
      return 'Services include penetration testing, vulnerability assessments, secure code reviews, and security awareness training.';
    }
    if (text.includes('project')) {
      return 'Highlighted projects include hospital management pentest, a custom privilege-escalation CTF machine, and security automation tooling.';
    }
    if (text.includes('contact')) {
      return 'You can contact via fasalmuhammad44@gmail.com or through LinkedIn and GitHub links on the site.';
    }
    return 'I can help with profile, services, projects, certifications, and contact details. Ask a direct question and I will answer quickly.';
  };

  send('Security Assistant online. Ask about profile, services, projects, or contact.');

  toggle?.addEventListener('click', () => windowEl.classList.toggle('open'));
  close?.addEventListener('click', () => windowEl.classList.remove('open'));

  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    send(q, 'user');
    setTimeout(() => send(answer(q), 'bot'), 220);
    form.reset();
  });
}

function initThreeScene() {
  const canvas = qs('#cyberScene');
  if (!canvas || !window.THREE || prefersReduced || window.innerWidth < 900) return;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

  camera.position.set(0, 8, 24);

  const globe = new THREE.Mesh(
    new THREE.SphereGeometry(3.2, 24, 24),
    new THREE.MeshBasicMaterial({
      color: 0x00d9ff,
      wireframe: true,
      transparent: true,
      opacity: 0.42
    })
  );
  scene.add(globe);

  const grid = new THREE.GridHelper(90, 40, 0x00d9ff, 0x00314a);
  grid.position.y = -6;
  scene.add(grid);

  const nodes = new THREE.Group();
  const nodeMat = new THREE.MeshBasicMaterial({ color: 0x00ff9f });
  for (let i = 0; i < 80; i += 1) {
    const node = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), nodeMat);
    node.position.set((Math.random() - 0.5) * 34, Math.random() * 14 - 3, (Math.random() - 0.5) * 34);
    nodes.add(node);
  }
  scene.add(nodes);

  const streams = new THREE.Group();
  const lineMat = new THREE.LineBasicMaterial({ color: 0x00ff9f, transparent: true, opacity: 0.32 });
  for (let i = 0; i < 22; i += 1) {
    const points = [
      new THREE.Vector3((Math.random() - 0.5) * 26, Math.random() * 12 - 4, (Math.random() - 0.5) * 26),
      new THREE.Vector3((Math.random() - 0.5) * 26, Math.random() * 12 - 4, (Math.random() - 0.5) * 26)
    ];
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    streams.add(new THREE.Line(geo, lineMat));
  }
  scene.add(streams);

  let raf;
  const animate = () => {
    globe.rotation.y += 0.003;
    nodes.rotation.y -= 0.0012;
    streams.rotation.y += 0.001;
    renderer.render(scene, camera);
    raf = requestAnimationFrame(animate);
  };

  animate();

  const onResize = () => {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  };

  window.addEventListener('resize', onResize);

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else animate();
  });
}

function initTheme() {
  const btn = qs('#theme-btn');
  if (!btn) return;

  const stored = localStorage.getItem('theme');
  if (stored === 'dim') {
    document.documentElement.style.setProperty('--bg', '#0e1218');
    document.documentElement.style.setProperty('--panel', 'rgba(20, 28, 40, 0.65)');
  }

  btn.addEventListener('click', () => {
    const current = localStorage.getItem('theme') || 'cyber';
    if (current === 'cyber') {
      document.documentElement.style.setProperty('--bg', '#0e1218');
      document.documentElement.style.setProperty('--panel', 'rgba(20, 28, 40, 0.65)');
      localStorage.setItem('theme', 'dim');
    } else {
      document.documentElement.style.setProperty('--bg', '#0b0f14');
      document.documentElement.style.setProperty('--panel', 'rgba(16, 24, 38, 0.6)');
      localStorage.setItem('theme', 'cyber');
    }
  });
}

function initPageTransitions() {
  if (!window.gsap || prefersReduced) return;
  gsap.from('main', { opacity: 0, y: 20, duration: 0.5, ease: 'power2.out' });
}

document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initReveal();
  initTyping();
  initCounters();
  initCursor();
  initTilt();
  initProjectFilters();
  initModal();
  initChatbot();
  initThreeScene();
  initTheme();
  initPageTransitions();
});
