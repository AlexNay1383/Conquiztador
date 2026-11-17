import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import type { RegisterPayload } from '../api/auth'
import { ApiError, type FieldErrors } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { FormErrors } from '../components/FormErrors'
import { FormField } from '../components/FormField'

const EMPTY_FORM: RegisterPayload = {
  username: '',
  email: '',
  nickname: '',
  password: '',
  password_confirm: '',
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  function update(field: keyof RegisterPayload, value: string) {
    setForm({ ...form, [field]: value })
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (form.password !== form.password_confirm) {
      setErrors({ password_confirm: ['Паролите не съвпадат.'] })
      return
    }
    setSubmitting(true)
    setErrors({})
    try {
      await register(form)
      navigate('/profile', { replace: true })
    } catch (error) {
      setErrors(error instanceof ApiError ? error.errors : { non_field_errors: ['Неочаквана грешка.'] })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card narrow">
      <h1>Регистрация</h1>
      <form onSubmit={handleSubmit} noValidate>
        <FormErrors errors={errors} />
        <FormField
          label="Потребителско име"
          name="username"
          autoComplete="username"
          required
          value={form.username}
          onChange={(event) => update('username', event.target.value)}
          errors={errors.username}
        />
        <FormField
          label="Имейл"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(event) => update('email', event.target.value)}
          errors={errors.email}
        />
        <FormField
          label="Прякор в играта"
          name="nickname"
          maxLength={30}
          required
          value={form.nickname}
          onChange={(event) => update('nickname', event.target.value)}
          errors={errors.nickname}
        />
        <FormField
          label="Парола"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          value={form.password}
          onChange={(event) => update('password', event.target.value)}
          errors={errors.password}
        />
        <FormField
          label="Повторете паролата"
          name="password_confirm"
          type="password"
          autoComplete="new-password"
          required
          value={form.password_confirm}
          onChange={(event) => update('password_confirm', event.target.value)}
          errors={errors.password_confirm}
        />
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? 'Създаване…' : 'Създай профил'}
        </button>
      </form>
      <p className="muted">
        Вече имате профил? <Link to="/login">Влезте</Link>
      </p>
    </section>
  )
}
