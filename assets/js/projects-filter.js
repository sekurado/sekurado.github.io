document.addEventListener("DOMContentLoaded", function () {
  var grid = document.getElementById("project-grid");
  var countEl = document.getElementById("projects-count");
  var emptyEl = document.getElementById("projects-empty");
  var ideasOnly = document.getElementById("ideas-only");
  var categoryChips = document.querySelectorAll('[data-filter="category"] .filter-chip');

  if (!grid) return;

  var cards = Array.from(grid.querySelectorAll(".project-card"));
  var activeCategory = "all";

  function sortCards() {
    cards.sort(function (a, b) {
      var statusDiff =
        Number(a.dataset.statusOrder) - Number(b.dataset.statusOrder);
      if (statusDiff !== 0) return statusDiff;
      return a.dataset.title.localeCompare(b.dataset.title);
    });

    cards.forEach(function (card) {
      grid.appendChild(card);
    });
  }

  function updateCount(visible) {
    if (!countEl) return;
    countEl.textContent = visible + " of " + cards.length + " projects";
  }

  function applyFilters() {
    var ideasOnlyActive = ideasOnly && ideasOnly.checked;
    var visible = 0;

    cards.forEach(function (card) {
      var matchesCategory =
        activeCategory === "all" || card.dataset.category === activeCategory;
      var matchesIdeas = !ideasOnlyActive || card.dataset.status === "idea";
      var show = matchesCategory && matchesIdeas;

      card.hidden = !show;
      if (show) visible += 1;
    });

    if (emptyEl) emptyEl.hidden = visible > 0;
    updateCount(visible);
  }

  categoryChips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      categoryChips.forEach(function (c) {
        c.classList.remove("is-active");
        c.setAttribute("aria-pressed", "false");
      });
      chip.classList.add("is-active");
      chip.setAttribute("aria-pressed", "true");
      activeCategory = chip.dataset.value;
      applyFilters();
    });
  });

  if (ideasOnly) {
    ideasOnly.addEventListener("change", applyFilters);
  }

  sortCards();
  applyFilters();
});
