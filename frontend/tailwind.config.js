module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        bg: "#070a09",
        panel: "#0e1410",
        panel2: "#121b16",
        accent: "#22ff8e",
        accent2: "#0fae66",
        muted: "#7c8b84",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 40px rgba(34,255,142,0.15)",
      },
    },
  },
  plugins: [],
};
