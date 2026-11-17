import { apiRequest } from './client'

export const AVATAR_KEYS = ['knight-1', 'knight-2', 'knight-3', 'knight-4'] as const
export type AvatarKey = (typeof AVATAR_KEYS)[number]

export const AVATAR_LABELS: Record<AvatarKey, string> = {
  'knight-1': 'Червен рицар',
  'knight-2': 'Зелен рицар',
  'knight-3': 'Син рицар',
  'knight-4': 'Лилав рицар',
}

export interface Profile {
  nickname: string
  avatar_key: AvatarKey
}

export interface User {
  id: number
  username: string
  email: string
  profile: Profile | null
}

export interface RegisterPayload {
  username: string
  email: string
  nickname: string
  password: string
  password_confirm: string
}

export interface LoginPayload {
  username: string
  password: string
}

export const authApi = {
  me: () => apiRequest<User>('/api/auth/me/'),
  register: (payload: RegisterPayload) => apiRequest<User>('/api/auth/register/', 'POST', payload),
  login: (payload: LoginPayload) => apiRequest<User>('/api/auth/login/', 'POST', payload),
  logout: () => apiRequest<void>('/api/auth/logout/', 'POST'),
  updateProfile: (payload: Partial<Profile>) => apiRequest<User>('/api/auth/me/', 'PATCH', payload),
}
