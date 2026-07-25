import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0F0A08",
        panel: "rgba(255, 244, 235, 0.045)",
        raised: "rgba(255, 244, 235, 0.08)",
        line: "rgba(255, 214, 186, 0.13)",
        ember: { DEFAULT: "#FF6A5A", 2: "#FFB454" },
        ink: { DEFAULT: "#F5EFEA", dim: "#B3A69D", faint: "#7C7069" },
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        ember: "0 0 34px -8px rgba(255, 106, 90, 0.5)",
        "glass-inset": "inset 0 1px 0 rgba(255,255,255,0.07)",
      },
      keyframes: {
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        "msg-in": {
          "0%": { opacity: "0", transform: "translateY(10px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "dot-pulse": {
          "0%, 60%, 100%": { transform: "translateY(0)", opacity: "0.4" },
          "30%": { transform: "translateY(-4px)", opacity: "1" },
        },
        "ember-drift": {
          "0%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(50px,-40px,0) scale(1.15)" },
          "100%": { transform: "translate3d(-30px,30px,0) scale(0.95)" },
        },
        "gradient-x": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 18px -4px rgba(255,106,90,0.55)" },
          "50%": { boxShadow: "0 0 30px -2px rgba(255,180,84,0.65)" },
        },
      },
      animation: {
        blink: "blink 1s step-start infinite",
        "msg-in": "msg-in 0.4s cubic-bezier(0.22,1,0.36,1) both",
        "dot-pulse": "dot-pulse 1.2s ease-in-out infinite",
        "ember-drift": "ember-drift 26s ease-in-out infinite alternate",
        "gradient-x": "gradient-x 5s ease infinite",
        "glow-pulse": "glow-pulse 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
