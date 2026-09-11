(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const menuButton = $('.menu-toggle');
  const menu = $('#site-menu');
  const themeButton = $('.theme-toggle');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const progress = $('.scroll-progress span');
  const header = $('.site-header');
  const backToTop = $('.back-to-top');

  if (!reduceMotion) {
    document.documentElement.classList.add('motion-ready');
    const revealTargets = [
      ...$$('.section-heading, .two-column > *, .research-grid > *, .resume-panel > *, .timeline-item, .skill-card, .project-card, .cert-card, .education-card, .contact .container')
    ];
    revealTargets.forEach((element, index) => {
      element.classList.add('reveal');
      if (element.matches('.timeline-item') && index % 2 === 0) element.classList.add('reveal-left');
      if (element.matches('.skill-card')) element.classList.add('reveal-scale');
    });
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealTargets.forEach((element) => revealObserver.observe(element));
    const timeline = $('.timeline');
    if (timeline) new IntersectionObserver((entries, observer) => {
      if (entries[0].isIntersecting) { timeline.classList.add('is-visible'); observer.disconnect(); }
    }, { threshold: 0.15 }).observe(timeline);
  }

  const sections = $$('main section[id]');
  const navLinks = $$('.nav-links a');
  const updateScrollUI = () => {
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.width = `${maxScroll ? (window.scrollY / maxScroll) * 100 : 0}%`;
    header.classList.toggle('scrolled', window.scrollY > 60);
    backToTop.classList.toggle('visible', window.scrollY > 600);
  };
  window.addEventListener('scroll', updateScrollUI, { passive: true });
  updateScrollUI();
  const navObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`));
    });
  }, { rootMargin: '-28% 0px -62% 0px', threshold: 0 });
  sections.forEach((section) => navObserver.observe(section));

  const closeMenu = () => {
    menu.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
  };

  menuButton.addEventListener('click', () => {
    const isOpen = menu.classList.toggle('open');
    menuButton.setAttribute('aria-expanded', String(isOpen));
  });
  $$('.nav-links a').forEach((link) => link.addEventListener('click', closeMenu));

  themeButton.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('mf-theme', next);
    themeButton.setAttribute('aria-label', `Switch to ${next === 'dark' ? 'light' : 'dark'} theme`);
  });
  themeButton.setAttribute('aria-label', `Switch to ${document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'} theme`);

  const filters = $$('.filter');
  const projects = $$('.project-card');
  filters.forEach((filter) => filter.addEventListener('click', () => {
    filters.forEach((button) => button.classList.toggle('active', button === filter));
    const category = filter.dataset.filter;
    projects.forEach((project) => project.classList.toggle('hidden', category !== 'all' && project.dataset.category !== category));
  }));

  function makeDialog(dialog, title, category, content) {
    $('#dialog-title', dialog).textContent = title;
    $('#dialog-category', dialog).textContent = category;
    const target = $('#dialog-content', dialog);
    target.replaceChildren(content.cloneNode(true));
    dialog.showModal();
    $('.dialog-close', dialog).focus();
  }

  const projectDialog = $('#project-dialog');
  $$('.case-study').forEach((button) => button.addEventListener('click', () => {
    const card = button.closest('.project-card');
    const template = $(`#${button.dataset.dialog}`);
    makeDialog(projectDialog, $('h3', card).textContent, $('.card-kicker', card).textContent, template.content);
  }));

  const certificateDialog = $('#certificate-dialog');
  $$('.certificate').forEach((button) => button.addEventListener('click', () => {
    $('#certificate-title', certificateDialog).textContent = button.dataset.title;
    const image = $('#certificate-image', certificateDialog);
    image.src = button.dataset.certificate;
    image.alt = `${button.dataset.title} certificate`;
    certificateDialog.showModal();
    $('.dialog-close', certificateDialog).focus();
  }));

  $$('.dialog').forEach((dialog) => {
    $('.dialog-close', dialog).addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
  });
  certificateDialog.addEventListener('close', () => { $('#certificate-image', certificateDialog).removeAttribute('src'); });
  $('#year').textContent = new Date().getFullYear();
})();
