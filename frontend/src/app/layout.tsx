import type { Metadata } from 'next'
import './globals.css'
import Navigation from '@/components/layout/Navigation'
import { AuthProvider } from '@/components/auth/AuthProvider'

export const metadata: Metadata = {
  title: 'GLAME AI Platform',
  description: 'AI-платформа для бренда GLAME',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <body>
        <AuthProvider>
          <Navigation />
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}
