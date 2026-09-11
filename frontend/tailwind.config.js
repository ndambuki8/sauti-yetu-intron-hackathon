/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Brand: a clinical teal→indigo trust hue used for accents & gradients.
        brand: {
          50: "#eff9ff",
          100: "#daf1ff",
          200: "#bde7ff",
          300: "#8ed7ff",
          400: "#57bffb",
          500: "#31a1f2",
          600: "#1b82e0",
          700: "#1668c4",
          800: "#18559f",
          900: "#194a7d",
          950: "#142e4d",
        },
        // Clinical semantics — mirrored in src/lib/palette.ts for Cytoscape.
        symptom: "#2f6f9f",
        finding: "#2a8a82",
        condition: "#c07c24",
        redflag: "#b3271e",
        topic: "#5b6b7c",
        department: "#8a94a0",
      },
      boxShadow: {
        glass: "0 8px 30px rgba(2, 20, 60, 0.06)",
        "glass-lg": "0 20px 60px -12px rgba(2, 20, 60, 0.18)",
        glow: "0 0 0 1px rgba(49,161,242,0.15), 0 12px 40px -8px rgba(27,130,224,0.45)",
      },
      keyframes: {
        breathe: {
          "0%, 100%": { transform: "scale(1)", opacity: "0.9" },
          "50%": { transform: "scale(1.04)", opacity: "1" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.8)", opacity: "0.6" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        breathe: "breathe 3.2s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.2, 0.6, 0.3, 1) infinite",
        float: "float 6s ease-in-out infinite",
        "fade-in-up": "fade-in-up 0.5s ease-out both",
        "fade-in": "fade-in 0.4s ease-out both",
        shimmer: "shimmer 2.2s linear infinite",
      },
    },
  },
  plugins: [],
};
