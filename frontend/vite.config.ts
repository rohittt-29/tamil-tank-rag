import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, forward /api/* to the FastAPI server so the browser
// sees one origin and we do not need CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
