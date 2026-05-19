/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        display: ["Inter", "sans-serif"],
      },
      colors: {
        // Chat View Colors
        "chat-primary": "#13b6ec",
        "chat-bg": "#f8fbfc",
        "chat-sidebar": "#f8fbfc",
        "chat-bubble-ai": "#e7f0f3",
        "chat-text-muted": "#4c869a",
        
        // Admin View Colors
        "admin-primary": "#06bcf9",
        "admin-bg": "#f5f8f8",
        "admin-text-secondary": "#47899e",
      },
      boxShadow: {
        "soft": "0 2px 10px rgba(0, 0, 0, 0.03)",
      }
    },
  },
  plugins: [],
}
