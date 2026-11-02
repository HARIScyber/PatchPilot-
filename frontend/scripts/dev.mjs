import react from '@vitejs/plugin-react';
import { createServer } from 'vite';

const server = await createServer({
  configFile: false,
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
await server.listen();
server.printUrls();
