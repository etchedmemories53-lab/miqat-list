(function () {
  "use strict";

  var hijriRadio = document.getElementById("recur-hijri");
  var weeklyRadio = document.getElementById("recur-weekly");
  var hijriFields = document.getElementById("hijri-fields");
  var weeklyFields = document.getElementById("weekly-fields");
  if (!hijriRadio || !weeklyRadio || !hijriFields || !weeklyFields) return;

  function sync() {
    hijriFields.hidden = !hijriRadio.checked;
    weeklyFields.hidden = !weeklyRadio.checked;
  }

  hijriRadio.addEventListener("change", sync);
  weeklyRadio.addEventListener("change", sync);
  sync();
})();
