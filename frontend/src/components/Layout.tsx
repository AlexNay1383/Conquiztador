import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { Avatar } from './Avatar'

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          Conquiztador
        </Link>
        <nav>
          {user ? (
            <>
              <NavLink to="/profile" className="nav-user">
                {user.profile && <Avatar avatarKey={user.profile.avatar_key} size={32} />}
                <span>{user.profile?.nickname ?? user.username}</span>
              </NavLink>
              <button type="button" className="button secondary" onClick={handleLogout}>
                Изход
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Вход</NavLink>
              <NavLink to="/register">Регистрация</NavLink>
            </>
          )}
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
