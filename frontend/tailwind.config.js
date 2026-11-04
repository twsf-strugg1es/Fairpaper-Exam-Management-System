/** @type {import('tailwindcss').Config} */

// Colors come from CSS variables (src/index.css), so light and dark themes share one set of names
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        paper: token("paper"), // page background
        surface: token("surface"), // cards, panels
        sunken: token("sunken"), // inputs, table headers, wells
        ink: token("ink"), // primary text
        muted: token("muted"), // secondary text
        line: { DEFAULT: token("line"), strong: token("line-strong") }, // borders and dividers
        faint: token("faint"), // tertiary text: labels, hints on paper
        "on-brand": token("on-brand"), // text on brand-colored buttons
        brand: {
          DEFAULT: token("brand"),
          strong: token("brand-strong"),
          soft: token("brand-soft"),
          ink: token("brand-ink"), // text on brand-soft
        },
        danger: { DEFAULT: token("danger"), soft: token("danger-soft"), ink: token("danger-ink") },
        warn: { DEFAULT: token("warn"), soft: token("warn-soft"), ink: token("warn-ink") },
        info: { DEFAULT: token("info"), soft: token("info-soft"), ink: token("info-ink") },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans Variable"', '"IBM Plex Sans"', '"Hind Siliguri"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      // Paper corners: small and consistent everywhere
      borderRadius: { sm: "2px", DEFAULT: "3px", md: "3px", lg: "4px", xl: "6px" },
      boxShadow: {
        card: "none",
        pop: "0 12px 32px -8px rgb(0 0 0 / 0.18), 0 2px 6px rgb(0 0 0 / 0.06)",
      },
      keyframes: {
        "fade-in": { from: { opacity: 0 }, to: { opacity: 1 } },
        "rise-in": { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "rise-in": "rise-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};
