/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'media', // Используем медиа-запрос prefers-color-scheme
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // GLAME Color Palette - inspired by store design
        // Concrete grays (бетонные серые тона)
        concrete: {
          50: '#F8F8F8',   // Светлый бетон
          100: '#F0F0F0',  // Очень светлый
          200: '#E5E5E5',  // Светлый
          300: '#D4D4D4',  // Средне-светлый
          400: '#A3A3A3',  // Средний
          500: '#737373',  // Базовый бетон
          600: '#525252',  // Темный
          700: '#404040',  // Очень темный
          800: '#2D2D2D',  // Почти черный бетон
          900: '#1A1A1A',  // Глубокий темный
        },
        // Metallic (металлические поверхности - brushed metal)
        metallic: {
          50: '#F5F5F5',
          100: '#E8E8E8',
          200: '#D4D4D4',
          300: '#C0C0C0',  // Brushed steel light
          400: '#A8A8A8',  // Brushed steel medium
          500: '#8C8C8C',  // Brushed steel base
          600: '#707070',
          700: '#545454',
          800: '#383838',
          900: '#1C1C1C',
        },
        // Gold accents (золотые акценты вместо розовых)
        gold: {
          50: '#FFFDF5',
          100: '#FFF9E6',
          200: '#FFF3CC',
          300: '#FFE8A3',
          400: '#FFD966',
          500: '#D4AF37',  // Classic gold
          600: '#B8860B',  // Dark goldenrod
          700: '#9A7209',
          800: '#7C5D07',
          900: '#5E4805',
        },
        // Wood tones (натуральное дерево)
        wood: {
          50: '#FDF8F3',
          100: '#F5E6D3',
          200: '#E8D5B7',
          300: '#D4B896',
          400: '#C09B75',
          500: '#A67C52',
          600: '#8B6A42',
          700: '#6F5433',
          800: '#533E25',
          900: '#372816',
        },
        // GLAME brand colors
        glame: {
          primary: '#D4AF37',    // Gold
          secondary: '#737373',  // Concrete gray
          accent: '#C0C0C0',     // Metallic
          dark: '#1A1A1A',       // Deep dark
          light: '#F8F8F8',     // Light concrete
        },
      },
      backgroundImage: {
        'concrete-texture': 'linear-gradient(135deg, #F8F8F8 0%, #E5E5E5 100%)',
        'metallic-shine': 'linear-gradient(135deg, #E8E8E8 0%, #C0C0C0 50%, #E8E8E8 100%)',
        'gold-gradient': 'linear-gradient(135deg, #FFD966 0%, #D4AF37 50%, #B8860B 100%)',
      },
      boxShadow: {
        'concrete': '0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04)',
        'metallic': '0 4px 12px rgba(192, 192, 192, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.2)',
        'gold': '0 4px 12px rgba(212, 175, 55, 0.25)',
      },
    },
  },
  plugins: [],
}
