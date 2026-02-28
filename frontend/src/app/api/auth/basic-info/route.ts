import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  let username: string | null = null;
  const auth = request.headers.get('authorization') || '';

  if (auth.startsWith('Basic ')) {
    try {
      const b64 = auth.split(' ')[1];
      const decoded = Buffer.from(b64, 'base64').toString('utf8');
      const [user] = decoded.split(':');
      username = user || null;
    } catch {
      username = null;
    }
  }

  const envUser =
    process.env.BASIC_AUTH_USER ||
    process.env.FRONTEND_BASIC_AUTH_USER ||
    null;

  return NextResponse.json({ basic_username: username || envUser });
}

