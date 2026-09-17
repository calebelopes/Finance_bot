/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./web/templates/**/*.html",
    "./web/static/js/app.js",
    // Route handlers occasionally return small inline HTML fragments
    // (e.g. the category-correction span), so scan them for class names.
    "./web/routes/**/*.py",
    // Preline ships its interactive class names in its dist bundle.
    "./node_modules/preline/dist/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms"), require("preline/plugin")],
};
