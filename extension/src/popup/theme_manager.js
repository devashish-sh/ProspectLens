// theme_manager.js — Pre-renders the user's selected font dynamically to prevent FOUT (flash of unstyled text).
// Runs immediately on loading in the document <head>.

(function () {
  const savedFont = localStorage.getItem("prospectlens-font");
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

  if (savedFont && fontStacks[savedFont]) {
    document.documentElement.style.setProperty("--font-family", fontStacks[savedFont]);
  }
})();
