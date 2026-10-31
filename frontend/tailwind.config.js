/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F5F1",
        surface: "#FFFFFF",
        ink: { DEFAULT: "#16181D", soft: "#3A3F4A", muted: "#646A76", faint: "#8C919B" },
        line: { DEFAULT: "#E4E2DB", strong: "#CFCCC2" },
        accent: { DEFAULT: "#0F5C4D", hover: "#0B4A3E", tint: "#E6F0ED" },
        danger: { DEFAULT: "#B42318", tint: "#FDEDEB" },
        warn: { DEFAULT: "#9A4A07", tint: "#FDF3E4" },
        ok: { DEFAULT: "#067647", tint: "#E7F5EE" },
        info: { DEFAULT: "#1A56B0", tint: "#EAF1FB" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "Segoe UI", "sans-serif"],
        serif: ['"Newsreader"', "Georgia", "serif"],
        mono: ['"IBM Plex Mono"', "Consolas", "monospace"],
      },
      boxShadow: { card: "0 1px 0 rgba(22,24,29,0.04), 0 1px 2px rgba(22,24,29,0.06)" },
    },
  },
  plugins: [],
};
