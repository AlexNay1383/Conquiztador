import type { InputHTMLAttributes } from 'react'

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  name: string
  errors?: string[]
}

export function FormField({ label, name, errors, ...inputProps }: FormFieldProps) {
  const errorId = `${name}-errors`
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <input
        id={name}
        name={name}
        aria-invalid={errors ? true : undefined}
        aria-describedby={errors ? errorId : undefined}
        {...inputProps}
      />
      {errors && (
        <div id={errorId}>
          {errors.map((message) => (
            <p key={message} className="field-error">
              {message}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
