(function () {
  "use strict";

  var rows = document.getElementById("niyaz-item-rows");
  var addBtn = document.getElementById("niyaz-add-item");
  var thalsInput = document.getElementById("thals-input");
  var totalEl = document.getElementById("niyaz-total");
  var perThalEl = document.getElementById("niyaz-per-thal");
  if (!rows || !addBtn || !thalsInput || !totalEl || !perThalEl) return;

  function recalc() {
    var total = 0;
    rows.querySelectorAll(".niyaz-amount").forEach(function (input) {
      var val = parseFloat(input.value);
      if (!isNaN(val)) total += val;
    });
    totalEl.textContent = total.toFixed(2);
    var thals = parseInt(thalsInput.value, 10);
    perThalEl.textContent = thals > 0 ? (total / thals).toFixed(2) : "—";
  }

  function bindRow(row) {
    row.querySelectorAll("input").forEach(function (input) {
      input.addEventListener("input", recalc);
    });
    row.querySelector(".niyaz-remove-item").addEventListener("click", function () {
      row.remove();
      recalc();
    });
  }

  rows.querySelectorAll(".niyaz-item-row").forEach(bindRow);
  thalsInput.addEventListener("input", recalc);

  addBtn.addEventListener("click", function () {
    var row = document.createElement("div");
    row.className = "niyaz-item-row";
    row.innerHTML =
      '<input type="text" name="item_label" placeholder="Item" required>' +
      '<input type="number" name="item_amount" placeholder="Amount" min="0" step="0.01" class="niyaz-amount">' +
      '<button type="button" class="niyaz-remove-item" aria-label="Remove item">&times;</button>';
    rows.appendChild(row);
    bindRow(row);
    row.querySelector("input").focus();
  });

  recalc();
})();
