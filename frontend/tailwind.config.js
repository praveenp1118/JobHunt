/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#E1F5EE',
          100: '#C3EBD9',
          200: '#87D7B3',
          300: '#4CC48C',
          400: '#1D9E75',
          500: '#1D9E75',
          600: '#0F6E56',
          700: '#0A4F3E',
          800: '#063228',
          900: '#031810',
        },
        navy: {
          50:  '#E8EDF5',
          100: '#C5D1E6',
          200: '#8CA3CC',
          300: '#5275B2',
          400: '#2D4F8E',
          500: '#1B2B4B',
          600: '#152239',
          700: '#0F1A2B',
          800: '#0A111C',
          900: '#05090E',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
