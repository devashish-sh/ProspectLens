// font_picker.js — Handles sliding side-drawer events, item highlights, and font selection persistence.

(function () {
  const toggle   = document.getElementById("font-picker-toggle");
  const drawer   = document.getElementById("font-picker-drawer");
  const closeBtn = document.getElementById("font-picker-close");
  const options  = document.querySelectorAll(".font-option-item");

  const fontStacks = {
    "Rubik Iso": "'Rubik Iso', cursive",
    "Bitcount Single": "'Bitcount Single', monospace",
    "Roboto Slab": "'Roboto Slab', serif",
    "Nunito": "'Nunito', sans-serif",
    "Quicksand": "'Quicksand', sans-serif",
    "Dosis": "'Dosis', sans-serif",
    "Syne Mono": "'Syne Mono', monospace",
    "Advent Pro": "'Advent Pro', sans-serif"
  };

  if (!toggle || !drawer || !closeBtn) return;

  // Toggle open
  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    drawer.classList.add("open");
  });

  // Toggle close
  closeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    drawer.classList.remove("open");
  });

  // Close when clicking outside the drawer
  window.addEventListener("click", (e) => {
    if (!drawer.contains(e.target) && !toggle.contains(e.target)) {
      drawer.classList.remove("open");
    }
  });

  // Initial active configuration load
  const currentFont = localStorage.getItem("prospectlens-font") || "System Default";
  options.forEach((opt) => {
    if (opt.getAttribute("data-font") === currentFont) {
      opt.classList.add("active");
    }

    opt.addEventListener("click", () => {
      // Clear active states and highlight clicked option
      options.forEach((o) => o.classList.remove("active"));
      opt.classList.add("active");

      const selected = opt.getAttribute("data-font");
      if (selected === "System Default") {
        localStorage.removeItem("prospectlens-font");
        document.documentElement.style.removeProperty("--font-family");
      } else {
        localStorage.setItem("prospectlens-font", selected);
        if (fontStacks[selected]) {
          document.documentElement.style.setProperty("--font-family", fontStacks[selected]);
        }
      }
    });
  });
})();
