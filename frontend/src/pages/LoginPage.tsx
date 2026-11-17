import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { ApiError, type FieldErrors } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { FormErrors } from '../components/FormErrors'
import { FormField } from '../components/FormField'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ username: '', password: '' })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await login(form)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from ?? '/profile', { replace: true })
    } catch (error) {
      setErrors(error instanceof ApiError ? error.errors : { non_field_errors: ['Неочаквана грешка.'] })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card narrow">
      <h1>Вход</h1>
      <form onSubmit={handleSubmit} noValidate>
        <FormErrors errors={errors} />
        <FormField
          label="Потребителско име"
          name="username"
          autoComplete="username"
          required
          value={form.username}
          onChange={(event) => setForm({ ...form, username: event.target.value })}
          errors={errors.username}
        />
        <FormField
          label="Парола"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={form.password}
          onChange={(event) => setForm({ ...form, password: event.target.value })}
          errors={errors.password}
        />
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? 'Влизане…' : 'Вход'}
        </button>
      </form>
      <p className="muted">
        Нямате профил? <Link to="/register">Регистрирайте се</Link>
      </p>
    </section>
  )
}
