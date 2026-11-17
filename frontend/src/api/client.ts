export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  readonly status: number
  readonly errors: FieldErrors

  constructor(status: number, errors: FieldErrors) {
    super(Object.values(errors).flat()[0] ?? `Грешка ${status}`)
    this.status = status
    this.errors = errors
  }
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function readCookie(name: string): string | null {
  const prefix = `${name}=`
  const cookie = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null
}

async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie('csrftoken')
  if (existing) return existing
  await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
  return readCookie('csrftoken') ?? ''
}

export async function apiRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (UNSAFE_METHODS.has(method)) headers['X-CSRFToken'] = await ensureCsrfToken()

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, { non_field_errors: ['Няма връзка със сървъра.'] })
  }

  if (response.status === 204) return undefined as T

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const errors: FieldErrors = data?.errors ?? { non_field_errors: [`Грешка ${response.status}`] }
    throw new ApiError(response.status, errors)
  }
  return data as T
}
