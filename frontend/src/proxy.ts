import { NextResponse, type NextRequest } from 'next/server';

export function proxy(request: NextRequest) {
  const host = request.headers.get('host')?.split(':')[0] || '';
  const isPartnerHost = host === 'partner.glamejewelry.ru';

  if (
    isPartnerHost &&
    !request.nextUrl.pathname.startsWith('/referral') &&
    !request.nextUrl.pathname.startsWith('/api') &&
    !request.nextUrl.pathname.startsWith('/docs') &&
    !request.nextUrl.pathname.startsWith('/static') &&
    !request.nextUrl.pathname.startsWith('/uploads') &&
    !request.nextUrl.pathname.startsWith('/_next') &&
    request.nextUrl.pathname !== '/tonconnect-manifest.json' &&
    request.nextUrl.pathname !== '/glame-ton-icon.svg'
  ) {
    const url = request.nextUrl.clone();
    url.pathname = '/referral';
    return NextResponse.redirect(url, 307);
  }

  if (request.method === 'POST' && request.headers.has('next-action')) {
    const url = request.nextUrl.clone();
    return NextResponse.redirect(url, 303);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
