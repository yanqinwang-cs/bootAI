"use strict";

document.addEventListener("htmx:afterSwap", function (event) {
  const feedback = event.detail.target.querySelector(
    "[data-decision-feedback]"
  );
  if (feedback) {
    feedback.focus();
  }
});
