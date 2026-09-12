(function () {
  "use strict";

  var rows = document.getElementById("niyaz-item-rows");
  var addBtn = document.getElementById("niyaz-add-item");
  var thalsInput = document.getElementById("thals-input");
  var totalEl = document.getElementById("niyaz-total");
  var perThalEl = document.getElementById("niyaz-per-thal");
  if (rows && addBtn && thalsInput && totalEl && perThalEl) {
    var recalc = function () {
      var total = 0;
      rows.querySelectorAll(".niyaz-amount").forEach(function (input) {
        var val = parseFloat(input.value);
        if (!isNaN(val)) total += val;
      });
      totalEl.textContent = total.toFixed(2);
      var thals = parseInt(thalsInput.value, 10);
      perThalEl.textContent = thals > 0 ? (total / thals).toFixed(2) : "—";
    };

    var bindRow = function (row) {
      row.querySelectorAll("input").forEach(function (input) {
        input.addEventListener("input", recalc);
      });
      row.querySelector(".niyaz-remove-item").addEventListener("click", function () {
        row.remove();
        recalc();
      });
    };

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
  }

  var menuRows = document.getElementById("niyaz-menu-item-rows");
  var addMenuBtn = document.getElementById("niyaz-add-menu-item");
  if (menuRows && addMenuBtn) {
    var bindMenuRow = function (row) {
      row.querySelector(".niyaz-remove-item").addEventListener("click", function () {
        row.remove();
      });
    };

    menuRows.querySelectorAll(".niyaz-item-row").forEach(bindMenuRow);

    addMenuBtn.addEventListener("click", function () {
      var row = document.createElement("div");
      row.className = "niyaz-item-row";
      row.innerHTML =
        '<input type="text" name="menu_item_label" placeholder="Item">' +
        '<input type="text" name="menu_item_details" placeholder="Details / specifics">' +
        '<button type="button" class="niyaz-remove-item" aria-label="Remove item">&times;</button>';
      menuRows.appendChild(row);
      bindMenuRow(row);
      row.querySelector("input").focus();
    });
  }

  var tabButtons = document.querySelectorAll(".form-tab");
  var panels = {
    finance: document.getElementById("tab-panel-finance"),
    menu: document.getElementById("tab-panel-menu"),
  };
  if (tabButtons.length && (panels.finance || panels.menu)) {
    var showTab = function (name) {
      Object.keys(panels).forEach(function (key) {
        if (panels[key]) panels[key].hidden = key !== name;
      });
      tabButtons.forEach(function (btn) {
        btn.setAttribute("aria-selected", btn.dataset.tab === name ? "true" : "false");
      });
    };
    tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        showTab(btn.dataset.tab);
      });
    });
  }
})();
