'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { getFirstAllowedHref } from '@/config/navigation';

export default function Home() {
  const { isAuthenticated, loading, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) return void router.replace('/login');
    router.replace(getFirstAllowedHref(user?.allowed_sections));
  }, [loading, isAuthenticated, user?.allowed_sections, router]);

  if (!isAuthenticated) {
    return null;
  }

  return null;
}
