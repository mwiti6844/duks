import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#FECE2D",
          dark: "#E0B400",
          light: "#FFE89E",
        },
        accent: { DEFAULT: "#FF000D" },
        ink: "#0E0E0B",
        "soft-ink": "#21211A",
        muted: "#636363",
        surface: "#F8F8F8",
        "card-border": "#E8E8E8",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
