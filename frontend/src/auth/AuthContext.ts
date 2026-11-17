import { createContext } from 'react'
import type { LoginPayload, Profile, RegisterPayload, User } from '../api/auth'

export interface AuthState {
  user: User | null
  loading: boolean
  login: (payload: LoginPayload) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => Promise<void>
  updateProfile: (payload: Partial<Profile>) => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)
