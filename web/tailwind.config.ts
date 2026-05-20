import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // 2015-2016 flat-design palette
        navy:    "#1e3a5f",   // primary
        navyDk:  "#15293f",
        sky:     "#3498db",   // accent
        skyDk:   "#2980b9",
        slate:   "#2c3e50",   // body text
        muted:   "#7f8c8d",   // secondary text
        line:    "#e1e8ed",   // borders / dividers
        bg:      "#f5f7fa",   // page background
        card:    "#ffffff",
        good:    "#27ae60",
        bad:     "#e74c3c",
        warn:    "#f39c12",
        info:    "#3498db",
        // for subtle stripe rows
        zebra:   "#f8fafb",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: ['"SFMono-Regular"', "Consolas", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(0,0,0,0.04), 0 1px 3px 0 rgba(0,0,0,0.06)",
        cardHover: "0 2px 4px 0 rgba(0,0,0,0.06), 0 4px 8px 0 rgba(0,0,0,0.08)",
      },
      borderRadius: {
        DEFAULT: "4px",
      },
    },
  },
  plugins: [],
};
export default config;
