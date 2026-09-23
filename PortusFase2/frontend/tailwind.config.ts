import type { Config } from 'tailwindcss'

// Paleta propia: cian industrial como acento, grises oscuros para estructura,
// colores de estado exclusivos para comunicar estado real del sistema.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        base: '#0A0E14',
        surface: '#111823',
        surface2: '#18212F',
        surface3: '#1F2A3A',
        line: '#263344',
        line2: '#31415A',
        ink: '#E7EEF6',
        inkdim: '#94A3B8',
        inkfaint: '#5E7189',
        accent: {
          DEFAULT: '#0EA5E9',
          hover: '#38BDF8',
          dim: '#0C87BC',
          soft: 'rgba(14, 165, 233, 0.12)',
        },
        ok: { DEFAULT: '#22C55E', soft: 'rgba(34, 197, 94, 0.12)' },
        warn: { DEFAULT: '#F59E0B', soft: 'rgba(245, 158, 11, 0.12)' },
        danger: { DEFAULT: '#EF4444', soft: 'rgba(239, 68, 68, 0.12)' },
        neutral: { DEFAULT: '#6B7280', soft: 'rgba(107, 114, 128, 0.14)' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        panel: '0 1px 0 rgba(0,0,0,0.35)',
        modal: '0 16px 48px rgba(0,0,0,0.55)',
      },
    },
  },
  plugins: [],
} satisfies Config
