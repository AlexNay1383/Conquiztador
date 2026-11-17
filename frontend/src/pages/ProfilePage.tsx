import { useState, type FormEvent } from 'react'
import type { AvatarKey } from '../api/auth'
import { ApiError, type FieldErrors } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { AvatarPicker } from '../components/AvatarPicker'
import { FormErrors } from '../components/FormErrors'
import { FormField } from '../components/FormField'

export function ProfilePage() {
  const { user, updateProfile } = useAuth()
  const [nickname, setNickname] = useState(user?.profile?.nickname ?? '')
  const [avatarKey, setAvatarKey] = useState<AvatarKey>(user?.profile?.avatar_key ?? 'knight-1')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  if (!user) return null

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    setSaved(false)
    try {
      await updateProfile({ nickname, avatar_key: avatarKey })
      setSaved(true)
    } catch (error) {
      setErrors(error instanceof ApiError ? error.errors : { non_field_errors: ['Неочаквана грешка.'] })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card">
      <div className="profile-header">
        <Avatar avatarKey={user.profile?.avatar_key ?? 'knight-1'} size={96} />
        <div>
          <h1>{user.profile?.nickname ?? user.username}</h1>
          <dl className="details">
            <dt>Потребителско име</dt>
            <dd>{user.username}</dd>
            <dt>Имейл</dt>
            <dd>{user.email}</dd>
          </dl>
        </div>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <h2>Редактиране на профила</h2>
        <FormErrors errors={errors} />
        <FormField
          label="Прякор"
          name="nickname"
          maxLength={30}
          required
          value={nickname}
          onChange={(event) => {
            setNickname(event.target.value)
            setSaved(false)
          }}
          errors={errors.nickname}
        />
        <AvatarPicker
          value={avatarKey}
          onChange={(value) => {
            setAvatarKey(value)
            setSaved(false)
          }}
          error={errors.avatar_key}
        />
        <div className="actions">
          <button type="submit" className="button" disabled={submitting}>
            {submitting ? 'Запазване…' : 'Запази'}
          </button>
          {saved && (
            <span className="success" role="status">
              Промените са запазени.
            </span>
          )}
        </div>
      </form>
    </section>
  )
}
