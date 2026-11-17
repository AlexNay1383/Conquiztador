import { AVATAR_LABELS, type AvatarKey } from '../api/auth'

const PALETTES: Record<AvatarKey, { plume: string; shield: string; emblem: string }> = {
  'knight-1': { plume: '#c0392b', shield: '#2c3e75', emblem: '#f1c40f' },
  'knight-2': { plume: '#27ae60', shield: '#5b3a1a', emblem: '#ecf0f1' },
  'knight-3': { plume: '#2980b9', shield: '#7b1f2b', emblem: '#f5d76e' },
  'knight-4': { plume: '#8e44ad', shield: '#1f4d3a', emblem: '#e67e22' },
}

export function Avatar({ avatarKey, size = 64 }: { avatarKey: AvatarKey; size?: number }) {
  const { plume, shield, emblem } = PALETTES[avatarKey]
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={AVATAR_LABELS[avatarKey]}>
      <circle cx="32" cy="32" r="31" fill="#f4ecd8" stroke={shield} strokeWidth="2" />
      <path d="M33 6c8 2 13 6 14 12-5-3-10-4-14-3Z" fill={plume} />
      <path d="M18 30c0-9 6-15 14-15s14 6 14 15v6H18Z" fill="#9aa5b1" stroke="#5d6975" strokeWidth="1.5" />
      <rect x="22" y="27" width="20" height="4" rx="2" fill="#2d3640" />
      <path d="M31 31h2v5h-2Z" fill="#2d3640" />
      <path d="M16 38h32v6c0 8-7 14-16 16-9-2-16-8-16-16Z" fill={shield} />
      <path d="M32 42v13M26 48h12" stroke={emblem} strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
