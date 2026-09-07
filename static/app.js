(function () {
  "use strict";

  var input = document.getElementById("city-search");
  var hidden = document.getElementById("city-id");
  var results = document.getElementById("city-results");
  if (!input || !hidden || !results) return;

  var debounceTimer = null;

  function clearResults() {
    results.innerHTML = "";
    results.hidden = true;
  }

  input.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    var query = input.value.trim();
    if (query.length < 2) {
      clearResults();
      return;
    }
    debounceTimer = setTimeout(function () {
      fetch("/api/cities?q=" + encodeURIComponent(query))
        .then(function (r) { return r.json(); })
        .then(function (list) {
          results.innerHTML = "";
          if (!list.length) {
            clearResults();
            return;
          }
          list.forEach(function (c) {
            var option = document.createElement("div");
            option.className = "city-option";
            option.textContent = c.name + ", " + c.country;
            option.addEventListener("click", function () {
              input.value = c.name + ", " + c.country;
              hidden.value = c.id;
              clearResults();
            });
            results.appendChild(option);
          });
          results.hidden = false;
        });
    }, 200);
  });

  document.addEventListener("click", function (e) {
    if (e.target !== input && !results.contains(e.target)) {
      clearResults();
    }
  });
})();
