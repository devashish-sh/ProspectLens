// lens-bg-dash.js — Lens background for dashboard (larger canvas)
(function () {
  const canvas = document.getElementById("lens-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  const ACCENT = "76, 92, 45";

  const lenses = Array.from({ length: 22 }, () => ({
    x:     Math.random() * window.innerWidth,
    y:     Math.random() * window.innerHeight,
    r:     Math.random() * 45 + 12,
    vx:    (Math.random() - 0.5) * 0.14,
    vy:    (Math.random() - 0.5) * 0.14,
    op:    Math.random() * 0.09 + 0.03,
    phase: Math.random() * Math.PI * 2,
  }));

  function draw(l, t) {
    const pulse  = 1 + 0.12 * Math.sin(t * 0.0007 + l.phase);
    const r      = l.r * pulse;
    const op     = l.op * pulse;

    const glow = ctx.createRadialGradient(l.x, l.y, 0, l.x, l.y, r * 2.4);
    glow.addColorStop(0,   `rgba(${ACCENT}, ${op * 0.45})`);
    glow.addColorStop(0.5, `rgba(${ACCENT}, ${op * 0.12})`);
    glow.addColorStop(1,   `rgba(${ACCENT}, 0)`);
    ctx.beginPath();
    ctx.arc(l.x, l.y, r * 2.4, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(l.x, l.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${ACCENT}, ${op * 1.5})`;
    ctx.lineWidth   = 0.7;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(l.x - r * 0.25, l.y - r * 0.25, r * 0.1, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${ACCENT}, ${op * 2.2})`;
    ctx.fill();
  }

  function animate(t) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    lenses.forEach(l => {
      l.x += l.vx; l.y += l.vy;
      if (l.x < -60)                   l.x = canvas.width  + 60;
      if (l.x > canvas.width  + 60)    l.x = -60;
      if (l.y < -60)                   l.y = canvas.height + 60;
      if (l.y > canvas.height + 60)    l.y = -60;
      draw(l, t);
    });
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
})();