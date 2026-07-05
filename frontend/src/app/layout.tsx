import type { Metadata } from 'next'
import './globals.css'
import StaleDeploymentReloader from '@/components/app/StaleDeploymentReloader'
import AppShell from '@/components/app/AppShell'
import TonConnectProvider from '@/components/app/TonConnectProvider'

export const metadata: Metadata = {
  title: 'Платформа GLAME ИИ',
  description: 'ИИ-платформа для бренда GLAME',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <body className="bg-gray-50">
        <StaleDeploymentReloader />
        <TonConnectProvider>
          <AppShell>{children}</AppShell>
        </TonConnectProvider>
      </body>
    </html>
  )
}
