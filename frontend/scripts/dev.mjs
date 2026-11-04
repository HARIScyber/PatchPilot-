import { createServer } from 'vite';

const server = await createServer({
  // Use the project's vite.config.ts so PostCSS/Tailwind are loaded
  configFile: 'vite.config.ts',
  server: {
    host: true,
    port: 3000,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
await server.listen();
server.printUrls();
