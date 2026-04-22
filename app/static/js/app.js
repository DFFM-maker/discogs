// Theme management
const THEME_KEY = "lpm_theme";

function getTheme() {
  return localStorage.getItem(THEME_KEY) ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  const btn = document.getElementById("theme-toggle-btn");
  if (btn) btn.title = t === "dark" ? "Switch to light" : "Switch to dark";
}

function toggleTheme() {
  applyTheme(getTheme() === "dark" ? "light" : "dark");
}

// Apply theme immediately to prevent flash
applyTheme(getTheme());

document.addEventListener("DOMContentLoaded", function () {
  // Scan trigger button
  const scanBtn = document.getElementById("scan-trigger-btn");
  if (scanBtn) {
    scanBtn.addEventListener("click", function () {
      scanBtn.disabled = true;
      scanBtn.textContent = "Avvio…";
      fetch("/api/scan/trigger", { method: "POST" })
        .then(r => r.json())
        .then(data => {
          if (data.status === "started") {
            showToast("Scansione avviata");
          } else if (data.status === "already_running") {
            showToast("Scansione già in corso");
          }
        })
        .catch(() => showToast("Errore avvio scansione"))
        .finally(() => {
          setTimeout(() => {
            scanBtn.disabled = false;
            scanBtn.textContent = "Scansiona ora";
          }, 3000);
        });
    });
  }

  // AI parse button
  const aiBtn = document.getElementById("ai-parse-btn");
  if (aiBtn) {
    aiBtn.addEventListener("click", function () {
      const queryInput = document.getElementById("ai_query");
      const query = queryInput ? queryInput.value.trim() : "";
      if (!query) return;

      aiBtn.disabled = true;
      aiBtn.textContent = "Analisi…";

      fetch("/api/wishlist/ai-parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.error) {
            showToast("AI non disponibile: " + data.error);
            return;
          }
          // Fill form fields from AI response
          if (data.artist) setField("artist", data.artist);
          if (data.title) setField("title", data.title);
          if (data.max_price) setField("max_price", data.max_price);
          if (data.currency) setField("currency", data.currency);
          if (data.min_condition) setField("min_condition", data.min_condition);
          if (data.country) setField("country", data.country);
          if (data.format) setField("format", data.format);
          showToast("Filtri compilati da AI");

          const resultEl = document.getElementById("ai-parse-result");
          if (resultEl) {
            resultEl.textContent = JSON.stringify(data, null, 2);
            resultEl.parentElement.classList.remove("hidden");
          }
        })
        .catch(() => showToast("Errore AI"))
        .finally(() => {
          aiBtn.disabled = false;
          aiBtn.textContent = "Analizza con AI";
        });
    });
  }
});

function setField(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
}

function showToast(msg) {
  const t = document.getElementById("toast");
  if (!t) return;
  t.querySelector(".toast-msg").textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3000);
}

// HTMX events
document.addEventListener("htmx:afterRequest", function (e) {
  if (e.detail.elt.dataset.toastSuccess) {
    showToast(e.detail.elt.dataset.toastSuccess);
  }
});
