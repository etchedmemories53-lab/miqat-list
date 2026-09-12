(function () {
  "use strict";

  var hijriRadio = document.getElementById("recur-hijri");
  var weeklyRadio = document.getElementById("recur-weekly");
  var rangeRadio = document.getElementById("recur-range");
  var hijriFields = document.getElementById("hijri-fields");
  var weeklyFields = document.getElementById("weekly-fields");
  var rangeFields = document.getElementById("range-fields");
  if (hijriRadio && weeklyRadio && rangeRadio && hijriFields && weeklyFields && rangeFields) {
    var syncRecurrence = function () {
      hijriFields.hidden = !hijriRadio.checked;
      weeklyFields.hidden = !weeklyRadio.checked;
      rangeFields.hidden = !rangeRadio.checked;
    };
    hijriRadio.addEventListener("change", syncRecurrence);
    weeklyRadio.addEventListener("change", syncRecurrence);
    rangeRadio.addEventListener("change", syncRecurrence);
    syncRecurrence();
  }

  var tabButtons = document.querySelectorAll(".form-tab");
  var panels = {
    miqaat: document.getElementById("tab-panel-miqaat"),
    personal: document.getElementById("tab-panel-personal"),
  };
  if (tabButtons.length && (panels.miqaat || panels.personal)) {
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

  var typeSelect = document.getElementById("personal-type");
  var customField = document.getElementById("personal-custom-type-field");
  if (typeSelect && customField) {
    var syncCustomField = function () {
      customField.hidden = typeSelect.value !== "other";
    };
    typeSelect.addEventListener("change", syncCustomField);
    syncCustomField();
  }
})();
