(function () {
  const canvas = document.getElementById('globe');
  const section = document.getElementById('threat-map');
  if (!canvas || !section) return;

  const activeEl = document.getElementById('active-attacks');
  const totalEl = document.getElementById('total-attacks');
  const topEl = document.getElementById('top-country');
  const fallback = document.getElementById('threat-map-fallback');

  const isMobile = window.innerWidth < 900;
  const lowPower = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const points = {
    USA: { lat: 38, lon: -97 },
    Germany: { lat: 51, lon: 10 },
    India: { lat: 22, lon: 78 },
    Brazil: { lat: -14, lon: -52 },
    Russia: { lat: 61, lon: 100 },
    China: { lat: 35, lon: 103 },
    UK: { lat: 55, lon: -3 },
    Japan: { lat: 36, lon: 138 },
    Canada: { lat: 56, lon: -106 },
    Australia: { lat: -25, lon: 133 }
  };

  const attackCounts = {};
  let totalAttacks = 0;
  let activeAttacks = 0;

  function toVec3(lat, lon, radius) {
    const phi = (90 - lat) * (Math.PI / 180);
    const theta = (lon + 180) * (Math.PI / 180);
    return new THREE.Vector3(
      -radius * Math.sin(phi) * Math.cos(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta)
    );
  }

  function updateCounters() {
    if (activeEl) activeEl.textContent = String(activeAttacks);
    if (totalEl) totalEl.textContent = String(totalAttacks);

    let topCountry = '-';
    let max = 0;
    Object.keys(attackCounts).forEach((name) => {
      if (attackCounts[name] > max) {
        max = attackCounts[name];
        topCountry = name;
      }
    });
    if (topEl) topEl.textContent = topCountry;
  }

  function initThreatMap() {
    if (!window.THREE || isMobile || lowPower) {
      fallback?.classList.remove('hidden');
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
    camera.position.z = 13;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

    const ambient = new THREE.AmbientLight(0x337799, 0.8);
    scene.add(ambient);

    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(4, 56, 56),
      new THREE.MeshPhongMaterial({ color: 0x0d1d29, emissive: 0x012233, wireframe: true })
    );
    scene.add(globe);

    const attacks = new THREE.Group();
    scene.add(attacks);

    function spawnAttack() {
      const names = Object.keys(points);
      let src = names[Math.floor(Math.random() * names.length)];
      let dst = names[Math.floor(Math.random() * names.length)];
      while (src === dst) dst = names[Math.floor(Math.random() * names.length)];

      attackCounts[src] = (attackCounts[src] || 0) + 1;
      totalAttacks += 1;
      activeAttacks += 1;
      updateCounters();

      const from = toVec3(points[src].lat, points[src].lon, 4.05);
      const to = toVec3(points[dst].lat, points[dst].lon, 4.05);
      const mid = from.clone().add(to).multiplyScalar(0.5).normalize().multiplyScalar(5.6);

      const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
      const pts = curve.getPoints(44);
      const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: 0xff0055, transparent: true, opacity: 0.95 }));

      const pulseMat = new THREE.MeshBasicMaterial({ color: 0xff0055 });
      const dotA = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), pulseMat);
      const dotB = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8), pulseMat);
      dotA.position.copy(from);
      dotB.position.copy(to);

      const bundle = new THREE.Group();
      bundle.add(line);
      bundle.add(dotA);
      bundle.add(dotB);
      attacks.add(bundle);

      let t = 0;
      const life = setInterval(() => {
        t += 0.06;
        const s = 1 + Math.sin(t * 8) * 0.35;
        dotA.scale.set(s, s, s);
        dotB.scale.set(s, s, s);
      }, 60);

      setTimeout(() => {
        clearInterval(life);
        attacks.remove(bundle);
        lineGeo.dispose();
        line.material.dispose();
        pulseMat.dispose();
        activeAttacks = Math.max(0, activeAttacks - 1);
        updateCounters();
      }, 4200);
    }

    updateCounters();
    spawnAttack();
    setInterval(spawnAttack, 2400);

    function animate() {
      globe.rotation.y += 0.002;
      attacks.rotation.y += 0.001;
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }

    animate();

    window.addEventListener('resize', () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    });
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        initThreatMap();
        observer.disconnect();
      }
    });
  }, { threshold: 0.2 });

  observer.observe(section);
})();
