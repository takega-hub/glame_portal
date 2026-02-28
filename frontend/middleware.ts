
// Basic Auth отключен — авторизация выполняется на уровне платформы
import { NextRequest, NextResponse } from 'next/server';

export function middleware(req: NextRequest) {
  // Пропускаем все запросы без проверки Basic Auth
  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api/auth-challenge|_next/static|_next/image|favicon.ico).*)'],
};
