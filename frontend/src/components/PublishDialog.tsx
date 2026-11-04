import { useMutation, useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { api, type PublishMode } from '../api'
import { Button, Choice, Field, Input, Textarea, cn } from './ui'

export interface Publishable {
  id: string
  title: string
  caption: string
  hashtags: string[]
}

export function PublishDialog({ item, onClose, onDone }: { item: Publishable; onClose: () => void; onDone: () => void }) {
  const channels = useQuery({ queryKey: ['channels'], queryFn: api.channels })
  const [selected, setSelected] = useState<string[]>([])
  const [mode, setMode] = useState<PublishMode>('queue')
  const [when, setWhen] = useState('')
  const [text, setText] = useState(`${item.caption}\n\n${item.hashtags.join(' ')}`.trim())
  const [title, setTitle] = useState(item.title)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const publish = useMutation({
    mutationFn: () =>
      api.publish(item.id, {
        channel_ids: selected,
        mode,
        scheduled_at: mode === 'schedule' && when ? new Date(when).toISOString() : null,
        text,
        title,
      }),
    onSuccess: (posts) => {
      const failed = posts.filter((p) => p.status === 'failed')
      if (failed.length) toast.error(`${failed.length} of ${posts.length} failed: ${failed[0].error}`)
      else toast.success(`Sent to Buffer for ${posts.length} channel${posts.length > 1 ? 's' : ''}`)
      onDone()
      onClose()
    },
    onError: (e) => toast.error(e.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Post with Buffer"
        className="glass rise flex max-h-[90vh] w-full max-w-lg flex-col overflow-y-auto rounded-[24px]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 pt-6">
          <h2 className="display text-[48px]">Post with Buffer</h2>
          <button aria-label="Close" onClick={onClose} className="cursor-pointer rounded-[8px] p-1.5 text-smoke hover:bg-white/[0.06] hover:text-bone">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-col gap-5 p-6">
          <Field label="Channels" group>
            {channels.isLoading && <p className="text-sm text-smoke">Loading channels…</p>}
            {channels.error && <p className="text-sm text-tally">{channels.error.message}</p>}
            <div className="grid gap-2 sm:grid-cols-2">
              {(channels.data ?? []).map((ch) => {
                const on = selected.includes(ch.id)
                return (
                  <button
                    key={ch.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setSelected(on ? selected.filter((id) => id !== ch.id) : [...selected, ch.id])}
                    className={cn(
                      'flex cursor-pointer items-center gap-3 rounded-[10px] border px-3 py-2.5 text-left text-sm transition-colors',
                      on ? 'border-rev-pink bg-rev-pink/10' : 'border-seam-up hover:border-white/30',
                    )}
                  >
                    {ch.avatar ? <img src={ch.avatar} alt="" className="h-7 w-7 rounded-full" /> : <span className="h-7 w-7 rounded-full bg-white/10" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{ch.name}</span>
                      <span className="block text-[12px] capitalize text-smoke">{ch.service}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          </Field>
          <Field label="When" group>
            <Choice<PublishMode>
              value={mode}
              onChange={setMode}
              options={[
                { value: 'queue', label: 'Queue' },
                { value: 'schedule', label: 'Schedule' },
                { value: 'now', label: 'Now' },
                { value: 'draft', label: 'Draft' },
              ]}
            />
          </Field>
          {mode === 'schedule' && (
            <Field label="Date and time">
              <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
            </Field>
          )}
          <Field label="Title" hint="Used for YouTube">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} />
          </Field>
          <Field label="Post text">
            <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-seam px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!selected.length || (mode === 'schedule' && !when)} loading={publish.isPending} onClick={() => publish.mutate()}>
            {mode === 'now' ? 'Post now' : mode === 'draft' ? 'Save draft' : mode === 'schedule' ? 'Schedule' : 'Add to queue'}
          </Button>
        </div>
      </div>
    </div>
  )
}
