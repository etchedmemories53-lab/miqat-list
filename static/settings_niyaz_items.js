(function () {
  "use strict";

  var rows = document.getElementById("niyaz-default-item-rows");
  var addBtn = document.getElementById("niyaz-add-default-item");
  if (!rows || !addBtn) return;

  function bindRow(row) {
    row.querySelector(".niyaz-remove-item").addEventListener("click", function () {
      row.remove();
    });
  }

  rows.querySelectorAll(".niyaz-item-row").forEach(bindRow);

  addBtn.addEventListener("click", function () {
    var row = document.createElement("div");
    row.className = "niyaz-item-row";
    row.innerHTML =
      '<input type="text" name="item_label" placeholder="Item name" required>' +
      '<button type="button" class="niyaz-remove-item" aria-label="Remove item">&times;</button>';
    rows.appendChild(row);
    bindRow(row);
    row.querySelector("input").focus();
  });
})();
