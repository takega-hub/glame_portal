'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { AuthProvider } from '@/components/auth/AuthProvider';
import AccessGate from '@/components/auth/AccessGate';
import GlobalSidebar from '@/components/layout/GlobalSidebar';

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isReferralPortal = pathname === '/referral' || pathname.startsWith('/referral/');
  const isPublicGlmLanding = pathname === '/glm' || pathname.startsWith('/glm/');

  if (isReferralPortal || isPublicGlmLanding) {
    return <>{children}</>;
  }

  return (
    <AuthProvider>
      <GlobalSidebar />
      <main className="md:ml-16 lg:ml-72 p-4 md:p-6">
        <AccessGate>{children}</AccessGate>
      </main>
    </AuthProvider>
  );
}
