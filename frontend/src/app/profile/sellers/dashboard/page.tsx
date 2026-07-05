'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import SellerKpiMainDashboard from '@/components/profile/SellerKpiMainDashboard';
import { useAuth } from '@/components/auth/AuthProvider';

export default function Page() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user?.role === 'seller') {
      router.replace('/profile/sellers/personal');
    }
  }, [router, user?.role]);

  if (loading || user?.role === 'seller') {
    return <main className="min-h-screen bg-gray-50 p-8 text-sm text-gray-600">Открываю личный KPI продавца…</main>;
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <SellerKpiMainDashboard />
    </main>
  );
}
