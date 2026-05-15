// App-wide tiny helpers. Most interactivity is handled by HTMX directly.

(function () {
  // Auto-scroll chat stream to bottom after HTMX swaps in new messages.
  document.addEventListener("htmx:afterSwap", function (e) {
    const stream = document.getElementById("chat-stream");
    if (stream && (e.detail.target === stream || stream.contains(e.detail.target))) {
      stream.scrollTop = stream.scrollHeight;
    }
  });

  // Reset chat input after a successful send.
  document.body.addEventListener("htmx:afterRequest", function (e) {
    const form = e.detail.elt;
    if (form && form.matches("form#chat-form") && e.detail.successful) {
      const input = form.querySelector("input[name=text]");
      if (input) {
        input.value = "";
        input.focus();
      }
    }
  });

  // Theme toggle. The initial dark/light class is applied synchronously by the
  // inline <head> script in base.html to avoid a flash of unstyled content;
  // here we only handle the user-driven toggle and persist the choice.
  const root = document.documentElement;
  document.addEventListener("click", function (e) {
    const t = e.target.closest("[data-theme-toggle]");
    if (!t) return;
    e.preventDefault();
    root.classList.toggle("dark");
    const isDark = root.classList.contains("dark");
    localStorage.setItem("finance.theme", isDark ? "dark" : "light");
    root.style.backgroundColor = isDark ? "#020617" : "#f8fafc";
  });
})();
