import type { FieldErrors } from '../api/client'

const GENERAL_KEYS = ['non_field_errors', 'detail']

export function FormErrors({ errors }: { errors: FieldErrors }) {
  const messages = GENERAL_KEYS.flatMap((key) => errors[key] ?? [])
  if (messages.length === 0) return null
  return (
    <div className="form-errors" role="alert">
      {messages.map((message) => (
        <p key={message}>{message}</p>
      ))}
    </div>
  )
}
