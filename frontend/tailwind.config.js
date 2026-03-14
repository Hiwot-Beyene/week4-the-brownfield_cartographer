/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["ui-serif", "Georgia", "Cambria", "Times New Roman", "serif"],
      },
      colors: {
        ruby: {
          950: "#1a0a0c",
          900: "#2b0f12",
          800: "#4a141a",
          700: "#7f1d1d",
          600: "#b91c1c",
          500: "#ef4444",
          300: "#fca5a5",
        },
        gold: {
          500: "#d4af37",
          400: "#e6c86b",
          300: "#f2dc96",
        },
      },
      boxShadow: {
        luxury: "0 18px 45px rgba(0,0,0,0.45)",
        glow: "0 0 0 1px rgba(252,165,165,0.5), 0 0 30px rgba(185,28,28,0.35)",
      },
    },
  },
  plugins: [],
};
