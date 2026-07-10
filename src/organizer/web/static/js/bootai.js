"use strict";

let bootaiFormSubmitting = false;

document.addEventListener("submit", function () {
  bootaiFormSubmitting = true;
});

document.addEventListener("htmx:afterRequest", function () {
  bootaiFormSubmitting = false;
});

window.addEventListener("beforeunload", function (event) {
  const dirtyReview = document.querySelector(
    '[data-review-dirty="true"]'
  );
  if (dirtyReview && !bootaiFormSubmitting) {
    event.preventDefault();
    event.returnValue = "";
  }
});
