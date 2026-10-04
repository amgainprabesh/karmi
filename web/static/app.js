/* Karmi web UI — progressive enhancement only.
   Without this file the site still works: the form posts to /analyze and the
   server redirects to the results page; the delta table simply shows all rows. */
(function () {
  "use strict";

  // mark that JS is available (CSS uses body:not(.js) to hide .js-only bits)
  document.body.classList.add("js");

  /* ---------------- delta table: filter by severity ---------------- */
  var filterBtns = document.querySelectorAll("[data-sev-filter]");
  var rows = document.querySelectorAll("tr[data-sev]");
  if (filterBtns.length && rows.length) {
    var emptyMsg = document.getElementById("delta-empty-filter");
    var applyFilter = function (sev) {
      var shown = 0;
      rows.forEach(function (row) {
        var show = sev === "all" || row.getAttribute("data-sev") === sev;
        row.hidden = !show;
        if (show) shown++;
      });
      if (emptyMsg) emptyMsg.hidden = shown !== 0;
    };
    filterBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        filterBtns.forEach(function (b) { b.classList.toggle("active", b === btn); });
        applyFilter(btn.getAttribute("data-sev-filter"));
      });
    });
  }

  /* ---------------- upload form: progress + friendly errors ---------------- */
  var form = document.getElementById("upload-form");
  if (!form || !window.XMLHttpRequest || !window.FormData) return;

  var submitBtn = document.getElementById("upload-submit");
  var statusEl = document.getElementById("upload-status");
  var progressWrap = document.getElementById("upload-progress");
  var progressBar = document.getElementById("upload-bar");
  var errorBox = document.getElementById("upload-error");

  var showError = function (en, np) {
    if (!errorBox) return;
    errorBox.textContent = np ? en + " / " + np : en;
    errorBox.hidden = false;
    if (progressWrap) progressWrap.hidden = true;
    if (submitBtn) submitBtn.disabled = false;
    if (statusEl) statusEl.textContent = "";
  };

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (errorBox) errorBox.hidden = true;
    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Uploading\u2026";
    if (progressWrap) progressWrap.hidden = false;
    if (progressBar) progressBar.style.width = "0%";

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/analyze", true);

    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable && progressBar) {
        var pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + "%";
        if (statusEl) statusEl.textContent = "Uploading\u2026 " + pct + "%";
      }
    };

    xhr.onload = function () {
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) { data = null; }
      if (data && data.run_id) {
        if (statusEl) {
          statusEl.textContent = data.degraded
            ? "Finished with limitations \u2014 opening results\u2026"
            : "Done \u2014 opening results\u2026";
        }
        window.location.href = "/run/" + encodeURIComponent(data.run_id);
        return;
      }
      var msg = (data && data.error) || ("The request failed (" + xhr.status + ").");
      var np = (data && data.error_np) || "";
      showError(msg, np);
    };

    xhr.onerror = function () {
      showError("Could not reach the Karmi server. Is it still running?",
                "\u0915\u0930\u094d\u092e\u0940 \u0938\u0930\u094d\u092d\u0930\u092e\u093e \u092a\u0941\u0917\u094d\u0928 \u0938\u0915\u093f\u090f\u0928\u0964");
    };

    xhr.send(new FormData(form));
  });
})();