// lens-bg.js — Animated floating lens background
// Semi-transparent blurred lens circles drifting slowly like stars

(function () {
  const canvas = document.getElementById("lens-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");

  function resize() {
    canvas.width  = document.body.scrollWidth  || 340;
    canvas.height = document.body.scrollHeight || 520;
  }
  resize();

  const ACCENT = "76, 92, 45"; // RGB of #4C5C2D

  // Generate lenses
  const lenses = Array.from({ length: 14 }, () => ({
    x:    Math.random() * canvas.width,
    y:    Math.random() * canvas.height,
    r:    Math.random() * 28 + 10,          // radius 10–38px
    vx:   (Math.random() - 0.5) * 0.18,     // very slow drift
    vy:   (Math.random() - 0.5) * 0.18,
    op:   Math.random() * 0.10 + 0.04,      // opacity 0.04–0.14 (subtle-visible range)
    phase: Math.random() * Math.PI * 2,     // for breathing pulse
  }));

  function drawLens(l, t) {
    // Gentle breathing pulse ±15% over ~4 seconds
    const pulse  = 1 + 0.15 * Math.sin(t * 0.0008 + l.phase);
    const radius = l.r * pulse;
    const op     = l.op * pulse;

    // Outer glow ring
    const glow = ctx.createRadialGradient(l.x, l.y, 0, l.x, l.y, radius * 2.2);
    glow.addColorStop(0,   `rgba(${ACCENT}, ${op * 0.5})`);
    glow.addColorStop(0.5, `rgba(${ACCENT}, ${op * 0.15})`);
    glow.addColorStop(1,   `rgba(${ACCENT}, 0)`);
    ctx.beginPath();
    ctx.arc(l.x, l.y, radius * 2.2, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    // Lens body — thin circle stroke
    ctx.beginPath();
    ctx.arc(l.x, l.y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${ACCENT}, ${op * 1.6})`;
    ctx.lineWidth   = 0.8;
    ctx.stroke();

    // Inner highlight dot
    ctx.beginPath();
    ctx.arc(l.x - radius * 0.25, l.y - radius * 0.25, radius * 0.12, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${ACCENT}, ${op * 2})`;
    ctx.fill();
  }

  let rafId;
  function animate(t) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    lenses.forEach(l => {
      // Drift
      l.x += l.vx;
      l.y += l.vy;

      // Wrap around edges
      if (l.x < -50)              l.x = canvas.width  + 50;
      if (l.x > canvas.width + 50) l.x = -50;
      if (l.y < -50)              l.y = canvas.height + 50;
      if (l.y > canvas.height + 50) l.y = -50;

      drawLens(l, t);
    });

    rafId = requestAnimationFrame(animate);
  }

  rafId = requestAnimationFrame(animate);
})();