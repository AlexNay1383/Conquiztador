import { useState, useEffect } from 'react'
import './index.css'

function getCookie(name: string) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function App() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'login' | 'register'>('login');
  
  // Form states
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [avatarKey, setAvatarKey] = useState('knight-1');
  const [errors, setErrors] = useState<any>({});

  useEffect(() => {
    fetchCsrf();
    checkSession();
  }, []);

  const fetchCsrf = async () => {
    try {
      await fetch('/api/auth/csrf/');
    } catch (e) {}
  };

  const checkSession = async () => {
    try {
      const res = await fetch('/api/auth/me/', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getHeaders = () => {
    return {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken') || ''
    };
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    
    try {
      const res = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        setUser(data);
        setPassword('');
      } else {
        setErrors(data.errors || data);
      }
    } catch (e) {
      setErrors({ non_field_errors: ['Connection error'] });
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    
    try {
      const res = await fetch('/api/auth/register/', {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ username, email, nickname, password, password_confirm: passwordConfirm })
      });
      const data = await res.json();
      if (res.ok) {
        // Auto login or switch to login
        setView('login');
        setPassword('');
        setPasswordConfirm('');
        alert('Registration successful! Please login.');
      } else {
        setErrors(data.errors || data);
      }
    } catch (e) {
      setErrors({ non_field_errors: ['Connection error'] });
    }
  };

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    
    try {
      const res = await fetch('/api/auth/me/', {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ nickname, avatar_key: avatarKey })
      });
      const data = await res.json();
      if (res.ok) {
        setUser(data);
        alert('Profile updated!');
      } else {
        setErrors(data.errors || data);
      }
    } catch (e) {
      setErrors({ non_field_errors: ['Connection error'] });
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout/', {
        method: 'POST',
        headers: getHeaders()
      });
      setUser(null);
    } catch (e) {
      console.error(e);
    }
  };

  if (loading) return <div>Loading...</div>;

  if (user) {
    return (
      <div className="container">
        <h1>Conquiztador</h1>
        
        <div className="profile-info">
          <div className="avatar">
            {user.profile?.avatar_key?.split('-')[1] || '1'}
          </div>
          <div className="profile-details">
            <h3>{user.profile?.nickname}</h3>
            <p>@{user.username}</p>
            <p>{user.email}</p>
          </div>
        </div>

        <h2>Edit Profile</h2>
        <form onSubmit={handleUpdateProfile}>
          <div className="form-group">
            <label>Nickname</label>
            <input 
              type="text" 
              defaultValue={user.profile?.nickname} 
              onChange={e => setNickname(e.target.value)} 
            />
            {errors?.nickname && <span className="error-text">{errors.nickname[0]}</span>}
          </div>
          
          <div className="form-group">
            <label>Avatar</label>
            <select defaultValue={user.profile?.avatar_key} onChange={e => setAvatarKey(e.target.value)}>
              <option value="knight-1">Knight 1</option>
              <option value="knight-2">Knight 2</option>
              <option value="knight-3">Knight 3</option>
              <option value="knight-4">Knight 4</option>
            </select>
            {errors?.avatar_key && <span className="error-text">{errors.avatar_key[0]}</span>}
          </div>
          
          <button type="submit">Save Changes</button>
        </form>
        
        <button className="secondary" onClick={handleLogout}>Logout</button>
      </div>
    );
  }

  return (
    <div className="container">
      <h1>Conquiztador</h1>
      
      {view === 'login' ? (
        <form onSubmit={handleLogin}>
          <h2>Welcome Back</h2>
          {errors?.non_field_errors && <div className="error-text" style={{marginBottom: '1rem', textAlign: 'center'}}>{errors.non_field_errors[0]}</div>}
          
          <div className="form-group">
            <label>Username</label>
            <input type="text" required value={username} onChange={e => setUsername(e.target.value)} />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" required value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <button type="submit">Login</button>
          
          <div className="auth-switch">
            Don't have an account? <span onClick={() => setView('register')}>Register</span>
          </div>
        </form>
      ) : (
        <form onSubmit={handleRegister}>
          <h2>Create Account</h2>
          {errors?.non_field_errors && <div className="error-text" style={{marginBottom: '1rem', textAlign: 'center'}}>{errors.non_field_errors[0]}</div>}
          
          <div className="form-group">
            <label>Username</label>
            <input type="text" required value={username} onChange={e => setUsername(e.target.value)} />
            {errors?.username && <span className="error-text">{errors.username[0]}</span>}
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} />
            {errors?.email && <span className="error-text">{errors.email[0]}</span>}
          </div>
          <div className="form-group">
            <label>Nickname</label>
            <input type="text" required value={nickname} onChange={e => setNickname(e.target.value)} />
            {errors?.nickname && <span className="error-text">{errors.nickname[0]}</span>}
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" required value={password} onChange={e => setPassword(e.target.value)} />
            {errors?.password && <span className="error-text">{errors.password[0]}</span>}
          </div>
          <div className="form-group">
            <label>Confirm Password</label>
            <input type="password" required value={passwordConfirm} onChange={e => setPasswordConfirm(e.target.value)} />
            {errors?.password_confirm && <span className="error-text">{errors.password_confirm[0]}</span>}
          </div>
          <button type="submit">Register</button>
          
          <div className="auth-switch">
            Already have an account? <span onClick={() => setView('login')}>Login</span>
          </div>
        </form>
      )}
    </div>
  )
}

export default App
