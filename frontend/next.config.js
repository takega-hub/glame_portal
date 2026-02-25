/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['clsx', 'tailwind-merge'],
  async rewrites() {
    // In local dev: proxy /api/* to backend to match production (nginx) setup.
    // If NEXT_PUBLIC_API_URL is set to an absolute URL (http/https), proxy to that target.
    // If it's set to a relative path like "/api", ignore it (that would create /api/api/* loops).
    const envTarget = process.env.NEXT_PUBLIC_API_URL || '';
    const target = envTarget.startsWith('http://') || envTarget.startsWith('https://') ? envTarget : 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${target}/api/:path*`,
      },
      // Проксируем статические файлы (изображения) с backend
      {
        source: '/static/:path*',
        destination: `${target}/static/:path*`,
      },
      // Проксируем загруженные файлы с backend
      {
        source: '/uploads/:path*',
        destination: `${target}/uploads/:path*`,
      },
    ];
  },
  // Увеличиваем таймаут для длительных запросов (генерация контент-плана через LLM)
  serverRuntimeConfig: {
    // Next.js не поддерживает прямой таймаут для rewrites, но axios на клиенте уже настроен
  },
}

module.exports = nextConfig
