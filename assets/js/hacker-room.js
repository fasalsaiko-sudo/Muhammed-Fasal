(function () {
  const canvas = document.getElementById('hacker-room-canvas');
  if (!canvas || !window.THREE) return;

  const lowMode = window.innerWidth < 900 || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (lowMode) {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
    ctx.fillStyle = '#0b0f14';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#00ff9f';
    ctx.font = '18px JetBrains Mono';
    ctx.fillText('3D room disabled on this device. Use desktop for full scene.', 30, 50);
    return;
  }

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0b0f14, 18, 60);

  const camera = new THREE.PerspectiveCamera(70, canvas.clientWidth / canvas.clientHeight, 0.1, 200);
  camera.position.set(0, 2, 8);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

  const ambient = new THREE.AmbientLight(0x00aaff, 0.45);
  const neon = new THREE.PointLight(0x00ff9f, 1.2, 35);
  neon.position.set(0, 6, 0);
  scene.add(ambient, neon);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(60, 60, 40, 40),
    new THREE.MeshBasicMaterial({ color: 0x03202f, wireframe: true, transparent: true, opacity: 0.45 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -1.5;
  scene.add(floor);

  const roomShell = new THREE.Mesh(
    new THREE.BoxGeometry(28, 12, 28),
    new THREE.MeshBasicMaterial({ color: 0x060a10, wireframe: true, transparent: true, opacity: 0.1 })
  );
  roomShell.position.y = 3;
  scene.add(roomShell);

  const serverRack = new THREE.Mesh(
    new THREE.BoxGeometry(1.8, 4.8, 1.8),
    new THREE.MeshPhongMaterial({ color: 0x0f1f2a, emissive: 0x002b3b })
  );
  serverRack.position.set(5, 1, -2);
  scene.add(serverRack);

  const netLines = new THREE.Group();
  for (let i = 0; i < 25; i += 1) {
    const p1 = new THREE.Vector3((Math.random() - 0.5) * 18, Math.random() * 6, (Math.random() - 0.5) * 18);
    const p2 = new THREE.Vector3((Math.random() - 0.5) * 18, Math.random() * 6, (Math.random() - 0.5) * 18);
    const g = new THREE.BufferGeometry().setFromPoints([p1, p2]);
    const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x00d9ff, transparent: true, opacity: 0.28 }));
    netLines.add(l);
  }
  scene.add(netLines);

  const particles = new THREE.Group();
  const pMat = new THREE.MeshBasicMaterial({ color: 0x00ff9f });
  for (let i = 0; i < 120; i += 1) {
    const p = new THREE.Mesh(new THREE.SphereGeometry(0.03, 6, 6), pMat);
    p.position.set((Math.random() - 0.5) * 24, Math.random() * 8 - 1, (Math.random() - 0.5) * 24);
    particles.add(p);
  }
  scene.add(particles);

  const monitorData = [
    { name: 'Monitor1', label: 'Projects', x: -4.5, y: 1.8, z: -5, url: 'writeups.html' },
    { name: 'Monitor2', label: 'Certifications', x: -1.5, y: 1.8, z: -5, url: 'profile.html#certifications' },
    { name: 'Monitor3', label: 'GitHub', x: 1.5, y: 1.8, z: -5, url: 'https://github.com/Fasal17' },
    { name: 'Monitor4', label: 'Blog', x: 4.5, y: 1.8, z: -5, url: 'blog/' }
  ];

  const monitorMeshes = [];
  monitorData.forEach((m) => {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(2.2, 1.3, 0.15),
      new THREE.MeshPhongMaterial({ color: 0x08131f, emissive: 0x00d9ff, emissiveIntensity: 0.4 })
    );
    mesh.position.set(m.x, m.y, m.z);
    mesh.userData.url = m.url;
    mesh.userData.label = m.label;
    monitorMeshes.push(mesh);
    scene.add(mesh);
  });

  const keys = { w: false, a: false, s: false, d: false };
  let yaw = 0;
  let pitch = 0;
  let dragging = false;

  window.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    if (k in keys) keys[k] = true;
  });
  window.addEventListener('keyup', (e) => {
    const k = e.key.toLowerCase();
    if (k in keys) keys[k] = false;
  });

  canvas.addEventListener('mousedown', () => {
    dragging = true;
  });
  window.addEventListener('mouseup', () => {
    dragging = false;
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    yaw -= e.movementX * 0.0024;
    pitch -= e.movementY * 0.0024;
    pitch = Math.max(-1.1, Math.min(1.1, pitch));
    camera.rotation.order = 'YXZ';
    camera.rotation.y = yaw;
    camera.rotation.x = pitch;
  });

  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hit = raycaster.intersectObjects(monitorMeshes)[0];
    if (!hit) return;

    const url = hit.object.userData.url;
    if (url.startsWith('http')) window.open(url, '_blank', 'noopener');
    else window.location.href = url;
  });

  function updateMovement() {
    const speed = 0.09;
    const dir = new THREE.Vector3();

    if (keys.w) dir.z -= 1;
    if (keys.s) dir.z += 1;
    if (keys.a) dir.x -= 1;
    if (keys.d) dir.x += 1;

    dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw).multiplyScalar(speed);
    camera.position.add(dir);
    camera.position.y = 2;
  }

  function animate() {
    updateMovement();

    serverRack.rotation.y += 0.01;
    netLines.rotation.y += 0.0015;
    particles.rotation.y -= 0.0012;
    floor.material.opacity = 0.35 + Math.sin(Date.now() * 0.001) * 0.1;

    monitorMeshes.forEach((m, i) => {
      m.material.emissiveIntensity = 0.3 + Math.sin(Date.now() * 0.002 + i) * 0.2;
    });

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
})();
