'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import WelcomePage from '@/components/welcome/WelcomePage';
import DesignSwitcher from '@/components/welcome/DesignSwitcher';

export default function Home() {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/login');
    }
  }, [loading, isAuthenticated, router]);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen">
      <div className="absolute top-4 right-4 z-50">
        <DesignSwitcher />
      </div>
      <WelcomePage />
    </main>
  );
}
