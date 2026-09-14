/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b12",
        navy: "#0b1220",
        panel: "#121b2b",
        raised: "#182433",
        line: "#2a3a52",
        cyan: "#3ee0f0",
        electric: "#4f8cff",
        violet: "#8b7cff",
        ok: "#3ddc97",
        warn: "#f5c542",
        bad: "#ff6b6b",
        mute: "#8ea0b8",
      },
      fontFamily: {
        sans: ["IBM Plex Sans Variable", "Avenir Next", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "inset 0 1px 0 rgba(255,255,255,0.04)",
      },
    },
  },
  plugins: [],
};
