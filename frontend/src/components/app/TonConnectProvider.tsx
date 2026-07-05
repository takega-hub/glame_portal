'use client'

import { TonConnectUIProvider } from '@tonconnect/ui-react'

export default function TonConnectProvider({ children }: { children: React.ReactNode }) {
  return (
    <TonConnectUIProvider
      manifestUrl="https://partner.glamejewelry.ru/tonconnect-manifest.json"
      analytics={{ mode: 'off' }}
    >
      {children}
    </TonConnectUIProvider>
  )
}
