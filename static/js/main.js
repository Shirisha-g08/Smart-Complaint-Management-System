/* main.js — Smart Complaint Management System */

document.addEventListener('DOMContentLoaded', function () {

  // ── Auto-dismiss flash alerts after 5 s ──────────────────────────────────
  document.querySelectorAll('#flash-container .alert').forEach(function (el) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    }, 5000);
  });

  // ── Clickable table rows (data-href) ─────────────────────────────────────
  document.querySelectorAll('tr[data-href]').forEach(function (row) {
    row.style.cursor = 'pointer';
    row.addEventListener('click', function (e) {
      // Don't navigate when clicking a button/link inside the row
      if (e.target.closest('a, button')) return;
      window.location.href = row.dataset.href;
    });
  });

  // ── Navbar: highlight active link ────────────────────────────────────────
  var currentPath = window.location.pathname;
  document.querySelectorAll('.navbar-nav .nav-link').forEach(function (link) {
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active', 'fw-semibold');
    }
  });

  // ── Tooltip initialisation (Bootstrap) ───────────────────────────────────
  var tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipEls.forEach(function (el) {
    new bootstrap.Tooltip(el);
  });

});
