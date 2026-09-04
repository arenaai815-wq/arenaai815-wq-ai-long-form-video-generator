import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        panel2: "rgb(var(--panel2) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        brand: {
          50: "#eef4ff", 100: "#dbe6ff", 200: "#bcd0ff", 300: "#8fb0ff", 400: "#5b85ff",
          500: "#3a5fff", 600: "#2a44f0", 700: "#2334cc", 800: "#212ea3", 900: "#1f2c80",
        },
        accent: "#22d3ee",
      },
      fontFamily: { sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"], mono: ["var(--font-geist-mono)", "monospace"] },
      boxShadow: { glow: "0 0 0 1px rgb(58 95 255 / 0.35), 0 10px 40px -10px rgb(58 95 255 / 0.45)" },
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        pulseSoft: { "0%, 100%": { opacity: "1" }, "50%": { opacity: ".55" } },
      },
      animation: { shimmer: "shimmer 2.2s linear infinite", pulseSoft: "pulseSoft 1.8s ease-in-out infinite" },
    },
  },
  plugins: [],
};
export default config;
