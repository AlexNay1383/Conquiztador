import { AVATAR_KEYS, AVATAR_LABELS, type AvatarKey } from '../api/auth'
import { Avatar } from './Avatar'

interface AvatarPickerProps {
  value: AvatarKey
  onChange: (value: AvatarKey) => void
  error?: string[]
}

export function AvatarPicker({ value, onChange, error }: AvatarPickerProps) {
  return (
    <fieldset className="field avatar-picker">
      <legend>Аватар</legend>
      <div className="avatar-options">
        {AVATAR_KEYS.map((key) => (
          <label key={key} className={key === value ? 'avatar-option selected' : 'avatar-option'}>
            <input
              type="radio"
              name="avatar_key"
              value={key}
              checked={key === value}
              onChange={() => onChange(key)}
            />
            <Avatar avatarKey={key} size={56} />
            <span>{AVATAR_LABELS[key]}</span>
          </label>
        ))}
      </div>
      {error?.map((message) => (
        <p key={message} className="field-error">
          {message}
        </p>
      ))}
    </fieldset>
  )
}
