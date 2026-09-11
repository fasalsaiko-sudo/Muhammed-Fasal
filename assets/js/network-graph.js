(function () {
  const canvas = document.getElementById('network-canvas');
  const section = document.getElementById('network-graph');
  const tooltip = document.getElementById('network-tooltip');
  if (!canvas || !section) return;

  const lowMode = window.innerWidth < 860 || window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function init() {
    if (!window.THREE || lowMode) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(52, canvas.clientWidth / canvas.clientHeight, 0.1, 500);
    camera.position.set(0, 2, 12);

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

    const nodesData = [
      { name: 'Web Server', pos: [-2.8, 1.8, 0] },
      { name: 'Database', pos: [2.2, 1.4, 0.8] },
      { name: 'Firewall', pos: [0, -0.5, 1.8] },
      { name: 'SOC Monitor', pos: [-1.2, -2, -0.5] },
      { name: 'Client Devices', pos: [2.6, -1.8, -1.2] }
    ];

    const nodes = [];
    const nodeGeo = new THREE.SphereGeometry(0.25, 16, 16);

    nodesData.forEach((n, idx) => {
      const mat = new THREE.MeshBasicMaterial({ color: idx % 2 === 0 ? 0x00ff9f : 0x00d9ff });
      const mesh = new THREE.Mesh(nodeGeo, mat);
      mesh.position.set(n.pos[0], n.pos[1], n.pos[2]);
      mesh.userData.name = n.name;
      nodes.push(mesh);
      scene.add(mesh);
    });

    const linkPairs = [[0, 2], [2, 1], [2, 3], [2, 4], [0, 1], [3, 4]];
    linkPairs.forEach(([a, b]) => {
      const pts = [nodes[a].position, nodes[b].position];
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x00d9ff, transparent: true, opacity: 0.7 }));
      scene.add(line);
    });

    const grid = new THREE.GridHelper(20, 30, 0x00ff9f, 0x003355);
    grid.position.y = -3.2;
    scene.add(grid);

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const hit = raycaster.intersectObjects(nodes)[0];
      if (!hit) {
        tooltip?.classList.add('hidden');
        return;
      }

      if (tooltip) {
        tooltip.textContent = hit.object.userData.name;
        tooltip.style.left = `${e.clientX - rect.left}px`;
        tooltip.style.top = `${e.clientY - rect.top}px`;
        tooltip.classList.remove('hidden');
      }
    });

    function animate() {
      scene.rotation.y += 0.003;
      nodes.forEach((n, i) => {
        const s = 1 + Math.sin(Date.now() * 0.002 + i) * 0.08;
        n.scale.set(s, s, s);
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
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        init();
        observer.disconnect();
      }
    });
  }, { threshold: 0.2 });

  observer.observe(section);
})();
