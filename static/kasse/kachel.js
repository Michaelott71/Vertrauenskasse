(function () {
  "use strict";

  var LONG_PRESS_MS = 500;

  function initKachel(el) {
    var input = el.querySelector(".kachel-input");
    var valueEl = el.querySelector(".kachel-value");
    var tapArea = el.querySelector(".kachel-tap");
    var minusBtn = el.querySelector(".kachel-minus");
    var min = parseInt(el.dataset.min || "0", 10);

    function getVal() {
      return parseInt(input.value || "0", 10);
    }

    function setVal(v) {
      if (v < min) v = min;
      input.value = v;
      valueEl.textContent = v;
    }

    var pressTimer = null;
    var longPressed = false;

    function startPress() {
      longPressed = false;
      pressTimer = window.setTimeout(function () {
        longPressed = true;
        setVal(getVal() - 1);
        if (window.navigator.vibrate) window.navigator.vibrate(15);
      }, LONG_PRESS_MS);
    }

    function endPress(e) {
      window.clearTimeout(pressTimer);
      if (!longPressed) {
        setVal(getVal() + 1);
      }
      if (e && e.preventDefault) e.preventDefault();
    }

    function cancelPress() {
      window.clearTimeout(pressTimer);
    }

    tapArea.addEventListener("pointerdown", startPress);
    tapArea.addEventListener("pointerup", endPress);
    tapArea.addEventListener("pointerleave", cancelPress);
    tapArea.addEventListener("pointercancel", cancelPress);
    tapArea.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setVal(getVal() + 1);
      } else if (e.key === "-" || e.key === "Backspace") {
        e.preventDefault();
        setVal(getVal() - 1);
      }
    });

    if (minusBtn) {
      minusBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        setVal(getVal() - 1);
      });
    }

    setVal(getVal());
  }

  document.addEventListener("DOMContentLoaded", function () {
    var kacheln = document.querySelectorAll(".kachel");
    for (var i = 0; i < kacheln.length; i++) {
      initKachel(kacheln[i]);
    }
  });
})();
