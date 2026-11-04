import { clsx, type ClassValue } from 'clsx'
import { Loader2 } from 'lucide-react'
import { createPortal } from 'react-dom'
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

type Variant = 'light' | 'ghost' | 'line' | 'danger' | 'record'

const variants: Record<Variant, string> = {
  // Pink paper: the main action on a page.
  light: 'bg-rev-pink text-ink hover:bg-[#f9cdda] shadow-[0_0_0_1px_rgba(255,255,255,0.4)_inset,0_12px_30px_-12px_rgba(246,186,203,0.7)]',
  ghost: 'text-dust hover:text-bone hover:bg-white/[0.05]',
  line: 'border border-seam-up text-bone hover:border-rev-pink/60 hover:bg-white/[0.04]',
  danger: 'border border-seam-up text-dust hover:border-tally hover:text-tally',
  // Cherry: recording.
  record: 'bg-tally text-bone hover:bg-[#f45f74] shadow-[0_0_0_1px_rgba(255,255,255,0.25)_inset,0_14px_40px_-12px_rgba(239,75,98,0.8)]',
}

export function Button({
  variant = 'light',
  size = 'md',
  loading,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; loading?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full transition-all duration-300 disabled:pointer-events-none disabled:opacity-35',
        size === 'sm' && 'h-8 px-3.5 text-[14px]',
        size === 'md' && 'h-10 px-5 text-[15px]',
        size === 'lg' && 'h-12 px-6 text-[16px]',
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-[22px] bg-booth/80 shadow-[0_0_0_1px_rgba(255,255,255,0.07)_inset,0_1px_0_rgba(255,255,255,0.05)_inset]',
        className,
      )}
      {...props}
    />
  )
}

/** A quiet label: sentence case, never letter-spaced capitals. */
export function Meta({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn('text-[13px] text-smoke', className)}>{children}</span>
}

const states: Record<string, [string, string]> = {
  completed: ['bg-go', 'Ready'],
  running: ['tally', 'Recording'],
  queued: ['bg-smoke', 'Waiting'],
  failed: ['bg-tally', 'Failed'],
}

export function Status({ value, className }: { value: string; className?: string }) {
  const [dot, label] = states[value] ?? states.queued
  return (
    <span className={cn('inline-flex items-center gap-2 text-[13px] text-dust', className)}>
      <span className={cn('h-2 w-2 rounded-full', dot)} />
      {label}
    </span>
  )
}

export function Field({
  label,
  hint,
  children,
  className,
  group,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  className?: string
  group?: boolean
}) {
  const Tag = group ? 'div' : 'label'
  return (
    <Tag className={cn('flex flex-col gap-2.5', className)} {...(group ? { role: 'group', 'aria-label': label } : {})}>
      <span className="text-[13px] text-dust">{label}</span>
      {children}
      {hint && <span className="text-[13px] leading-relaxed text-smoke">{hint}</span>}
    </Tag>
  )
}

const control =
  'w-full rounded-[12px] bg-white/[0.04] px-3.5 text-[15px] text-bone placeholder:text-smoke outline-none ring-1 ring-seam transition focus:bg-white/[0.06] focus:ring-rev-pink/70'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, 'h-11', className)} {...props} />
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(control, 'h-11 cursor-pointer pr-8 [&>option]:bg-panel', className)} {...props} />
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, 'py-3 leading-relaxed', className)} {...props} />
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex cursor-pointer items-center gap-3 text-[15px]">
      <span className={cn('flex h-[22px] w-10 rounded-full p-[3px] transition-colors duration-300', checked ? 'bg-rev-pink' : 'bg-white/10')}>
        <span className={cn('h-4 w-4 rounded-full shadow transition-transform duration-300', checked ? 'translate-x-[18px] bg-night' : 'bg-bone')} />
      </span>
      {label}
    </button>
  )
}

export function Choice<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T
  options: { value: T; label: ReactNode }[]
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div className={cn('inline-flex rounded-full bg-white/[0.04] p-1 ring-1 ring-seam', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'flex-1 cursor-pointer whitespace-nowrap rounded-full px-3.5 py-1.5 text-[14px] transition-all duration-300',
            value === o.value ? 'bg-bone text-night' : 'text-dust hover:text-bone',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/**
 * A panel that opens from a trigger. It renders in a portal with fixed positioning,
 * so scrolling or clipped containers (like the bottom console) can never hide it.
 */
export function Popover({
  trigger,
  children,
  align = 'left',
  side = 'top',
  className,
}: {
  trigger: (open: boolean) => ReactNode
  children: ReactNode
  align?: 'left' | 'right'
  side?: 'top' | 'bottom'
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number; maxHeight: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const a = anchor.current?.getBoundingClientRect()
      if (!a) return
      const width = panel.current?.offsetWidth ?? 340
      const gap = 12
      const margin = 12
      let left = align === 'left' ? a.left : a.right - width
      left = Math.max(margin, Math.min(left, window.innerWidth - width - margin))
      if (side === 'top') setPos({ left, bottom: window.innerHeight - a.top + gap, maxHeight: a.top - gap - margin })
      else setPos({ left, top: a.bottom + gap, maxHeight: window.innerHeight - a.bottom - gap - margin })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, align, side])

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (anchor.current?.contains(t) || panel.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={anchor} className="relative">
      <div
        onClick={() => {
          setPos(null)
          setOpen(!open)
        }}
      >
        {trigger(open)}
      </div>
      {open &&
        createPortal(
          <div
            ref={panel}
            role="dialog"
            className={cn('glass pop fixed z-[90] w-[min(340px,calc(100vw-24px))] overflow-y-auto rounded-[20px] p-5', pos ? 'rise' : 'invisible', className)}
            style={pos ? { left: pos.left, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxHeight } : { left: 0, top: 0 }}
          >
            {children}
          </div>,
          document.body,
        )}
    </div>
  )
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return '–'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const rest = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`
}

/** Film timecode: 00:00:04:12 at 24 fps. */
export function timecode(seconds: number) {
  const total = Math.max(0, seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = Math.floor(total % 60)
  const f = Math.floor((total % 1) * 24)
  return [h, m, s, f].map((n) => String(n).padStart(2, '0')).join(':')
}

export function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function runLabel(run: { title: string | null; script: string }) {
  if (run.title) return run.title
  const first = run.script
    .split('\n')
    .map((l) => l.replace(/^#+\s*/, '').replace(/\[[^\]]*\]/g, '').trim())
    .find(Boolean)
  return first ? (first.length > 60 ? `${first.slice(0, 57)}…` : first) : 'Untitled'
}
