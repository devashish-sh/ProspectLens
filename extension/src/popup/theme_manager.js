// theme_manager.js — Pre-renders and validates font/theme configurations.
(function () {
  // Restore persisted font-family on load if exists to prevent layout reflow races
  const currentFont = localStorage.getItem("prospectlens-font");
  if (currentFont) {
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
    if (fontStacks[currentFont]) {
      document.documentElement.style.setProperty("--font-family", fontStacks[currentFont]);
    }
  }
})();
