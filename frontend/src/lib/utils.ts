import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Экспортируем для использования в других компонентах
export { clsx, twMerge }

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const value = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=')
  return value ? decodeURIComponent(value) : null
}

function withCsrfHeader(init?: RequestInit): RequestInit | undefined {
  if (typeof window === 'undefined') return init
  const method = String(init?.method || 'GET').toUpperCase()
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) return init

  const headers = new Headers(init?.headers)
  if (!headers.has('authorization') && !headers.has('x-csrf-token')) {
    const csrfToken = readCookie('__Host-glame_csrf')
    if (csrfToken) headers.set('x-csrf-token', csrfToken)
  }
  return { ...init, headers }
}

/**
 * Безопасный fetch с разбором JSON. Не падает с SyntaxError, если сервер вернул HTML/текст (например "Internal Server Error").
 */
export async function fetchJson<T = unknown>(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<{ response: Response; data: T }> {
  const response = await fetch(input, withCsrfHeader(init))
  const text = await response.text()
  let data: T
  try {
    data = (text ? JSON.parse(text) : {}) as T
  } catch {
    if (!response.ok) {
      throw new Error(text || response.statusText || String(response.status))
    }
    throw new Error('Ответ сервера не в формате JSON')
  }
  if (!response.ok) {
    const msg = (data as { detail?: string; message?: string })?.detail
      ?? (data as { detail?: string; message?: string })?.message
      ?? text
      ?? response.statusText
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return { response, data }
}
