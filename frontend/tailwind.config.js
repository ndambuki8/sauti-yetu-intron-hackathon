/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        // Clinical semantics — mirrored in src/lib/palette.ts for Cytoscape.
        symptom: "#2f6f9f",
        finding: "#2a8a82",
        condition: "#c07c24",
        redflag: "#b3271e",
        topic: "#5b6b7c",
        department: "#8a94a0",
      },
    },
  },
  plugins: [],
};
