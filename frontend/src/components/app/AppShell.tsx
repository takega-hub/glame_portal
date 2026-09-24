'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import Script from 'next/script';
import { AuthProvider } from '@/components/auth/AuthProvider';
import AccessGate from '@/components/auth/AccessGate';
import AdminOnlinePresence from '@/components/layout/AdminOnlinePresence';
import GlobalSidebar from '@/components/layout/GlobalSidebar';

function YandexMetrika() {
  return (
    <>
      <Script id="yandex-metrika-referral" strategy="afterInteractive">
        {`
          (function(m,e,t,r,i,k,a){
              m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
              m[i].l=1*new Date();
              for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
              k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
          })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=110503614', 'ym');

          ym(110503614, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
        `}
      </Script>
      <noscript>
        <div>
          <img src="https://mc.yandex.ru/watch/110503614" style={{ position: 'absolute', left: '-9999px' }} alt="" />
        </div>
      </noscript>
    </>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isReferralPortal = pathname === '/referral' || pathname.startsWith('/referral/');
  const isPublicGlmLanding = pathname === '/glm' || pathname.startsWith('/glm/');
  const isSellerQuestionnaire = pathname === '/seller/customer-questionnaire';

  if (isReferralPortal) {
    return (
      <>
        <YandexMetrika />
        {children}
      </>
    );
  }

  if (isPublicGlmLanding) {
    return <>{children}</>;
  }

  // Customer-facing kiosk: keep authentication and access control, but never
  // render navigation or the regular platform chrome.
  if (isSellerQuestionnaire) {
    return (
      <AuthProvider>
        <AccessGate>{children}</AccessGate>
      </AuthProvider>
    );
  }

  return (
    <AuthProvider>
      <GlobalSidebar />
      <AdminOnlinePresence />
      <main className="md:ml-16 lg:ml-72 p-4 md:p-6">
        <AccessGate>{children}</AccessGate>
      </main>
    </AuthProvider>
  );
}
