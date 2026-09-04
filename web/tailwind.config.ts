import type { Config } from "tailwindcss";

// Analytical, quiet, one accent. No gradients, no glow: this page asks someone to
// trust a number about the largest purchase of their life (ARCHITECTURE.md §7).
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        muted: "#6b7280",
        line: "#e5e7eb",
        accent: "#1d4ed8",
        caution: "#b45309",
        alarm: "#b91c1c",
        good: "#15803d",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
