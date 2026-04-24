import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#000000',
        surface: '#0a0a0a',
        card: '#0f0f0f',
        border: '#1a1a1a',
        hover: '#2a2a2a',
        text: '#ffffff',
        muted: 'rgba(255,255,255,0.7)',
      },
    },
  },
  plugins: [],
}
export default config
