import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi, type LoginPayload, type Profile, type RegisterPayload, type User } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    authApi
      .me()
      .then(setUser)
      .catch((error: unknown) => {
        if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) {
          console.error(error)
        }
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (payload: LoginPayload) => setUser(await authApi.login(payload)), [])
  const register = useCallback(async (payload: RegisterPayload) => setUser(await authApi.register(payload)), [])
  const updateProfile = useCallback(
    async (payload: Partial<Profile>) => setUser(await authApi.updateProfile(payload)),
    [],
  )
  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, updateProfile }),
    [user, loading, login, register, logout, updateProfile],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
