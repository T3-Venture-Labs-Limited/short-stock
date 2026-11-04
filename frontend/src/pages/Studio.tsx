import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronUp, Lock, Music, Search, Sparkles, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  api,
  DEFAULT_OPTIONS,
  type AspectRatio,
  type BoardSentence,
  type CaptionStyle,
  type StockClip,
  type VideoOptions,
  type VoiceProvider,
} from '../api'
import { Button, Choice, Field, Input, Popover, Switch, Textarea, cn, timecode } from '../components/ui'
import { shotColor } from '../revision'
import { VoicePicker } from '../components/VoicePicker'
import { setPin, setQueries, setQuery } from '../scriptEdits'

const EXAMPLE = `# Why you should walk every day

[visual: person walking in park at sunrise]
A twenty minute walk does more for your brain than most supplements.

It raises your heart rate just enough to send fresh blood to the parts of your brain that handle memory.

[visual: city street at night]
And if you walk after dinner, your blood sugar drops faster too.

So tomorrow, leave your phone at home and take the long way.`

const WORDS_PER_SECOND = 2.75
const STORAGE_KEY = 'shortstock.draft'

const ASPECTS: { value: AspectRatio; label: string }[] = [
  { value: '9:16', label: '9:16' },
  { value: '4:5', label: '4:5' },
  { value: '1:1', label: '1:1' },
  { value: '16:9', label: '16:9' },
]

const CAPTION_STYLES: { value: CaptionStyle; label: string; sample: ReactNode }[] = [
  {
    value: 'bold',
    label: 'Bold',
    sample: (
      <span className="lowercase">
        take <span className="text-white/45">the</span> <span className="text-[#FFD400]">long</span>
      </span>
    ),
  },
  {
    value: 'highlight',
    label: 'Highlight',
    sample: (
      <span>
        TAKE <span className="text-[#2BE36F]">THE</span> LONG
      </span>
    ),
  },
  { value: 'minimal', label: 'Minimal', sample: <span className="font-sans text-[11px] font-semibold">Take the long</span> },
]

function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return debounced
}

export function StudioPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const editor = useRef<HTMLTextAreaElement>(null)
  const [script, setScript] = useState(() => localStorage.getItem(STORAGE_KEY) ?? '')
  const [title, setTitle] = useState('')
  const [options, setOptions] = useState<VideoOptions>(DEFAULT_OPTIONS)
  const [hashtags, setHashtags] = useState('')
  const [musicName, setMusicName] = useState<string | null>(null)
  const [caret, setCaret] = useState<number | null>(null)

  useEffect(() => localStorage.setItem(STORAGE_KEY, script), [script])

  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const setting = (key: string) => settings.data?.find((s) => s.key === key)
  const provider: VoiceProvider = options.voice_provider ?? ((setting('tts_provider')?.value as VoiceProvider) || 'elevenlabs')
  const blockers = (health.data?.checks ?? []).filter((c) => c.required && !c.ok)
  const canSuggest = health.data?.checks.find((c) => c.name === 'ai')?.ok
  const set = <K extends keyof VideoOptions>(key: K, value: VideoOptions[K]) => setOptions((o) => ({ ...o, [key]: value }))

  const boardScript = useDebounced(script, 450)
  const board = useQuery({
    queryKey: ['storyboard', boardScript],
    queryFn: () => api.storyboard(boardScript),
    placeholderData: keepPreviousData,
    enabled: boardScript.trim().length > 0,
  })
  const inSync = board.data !== undefined && boardScript === script && !board.isPlaceholderData
  const sentences = script.trim() ? (board.data?.sentences ?? []) : []
  const words = sentences.reduce((n, s) => n + s.text.split(/\s+/).length, 0)
  const seconds = words / WORDS_PER_SECOND / options.speed
  const locked = sentences.filter((s) => s.pin != null).length
  const activeIndex = useMemo(
    () => (caret == null ? null : sentences.findIndex((s, i) => caret >= s.start && (caret <= s.end || i === sentences.length - 1))),
    [caret, sentences],
  )
  const heading = title || board.data?.title || ''

  const focusSentence = (s: BoardSentence) => {
    const el = editor.current
    if (!el || !inSync) return
    el.focus()
    el.setSelectionRange(s.start, s.end)
    setCaret(s.start)
  }

  const suggest = useMutation({
    mutationFn: () => api.suggest(script),
    onSuccess: (queries) => {
      if (!inSync) return
      setScript(setQueries(script, sentences, queries))
      toast.success(queries.length ? `Wrote ${queries.length} footage searches` : 'Every shot already has a search')
    },
    onError: (e) => toast.error(e.message),
  })

  const submit = useMutation({
    mutationFn: () =>
      api.createRun(script, title.trim() || null, {
        ...options,
        voice_provider: provider,
        hashtags: hashtags.split(/[\s,]+/).filter(Boolean).map((t) => (t.startsWith('#') ? t : `#${t}`)),
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      navigate(`/videos/${run.id}`)
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="flex flex-col gap-10 pb-36">
      {/* Marquee: the reel's title and its running numbers */}
      <section className="rise flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex min-w-0 flex-1 flex-col">
          <TitleField value={title || heading} placeholder="Untitled reel" onChange={setTitle} />
        </div>
        <dl className="grid shrink-0 grid-cols-3 gap-px overflow-hidden rounded-[18px] bg-seam ring-1 ring-seam">
          {[
            ['Shots', String(sentences.length).padStart(2, '0')],
            ['Runtime', timecode(seconds).slice(3, 8)],
            ['Locked', String(locked).padStart(2, '0')],
          ].map(([label, value]) => (
            <div key={label} className="flex min-w-[118px] flex-col gap-2 bg-booth px-5 py-4">
              <dt className="text-[13px] text-smoke">{label}</dt>
              <dd className="display text-[44px] tabular-nums text-bone">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {blockers.length > 0 && (
        <div className="rise flex flex-col gap-4 rounded-[18px] bg-rev-pink/[0.08] p-5 ring-1 ring-rev-pink/30 sm:flex-row sm:items-center">
          <p className="flex-1 text-[15px] text-bone">
            <span className="text-rev-pink">Before your first take. </span>
            {blockers.map((c) => `${c.label}: ${c.detail}`).join(' · ')}
          </p>
          <Link to="/settings">
            <Button size="sm">Open settings</Button>
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* The script: a sheet under a lamp */}
        <section className="rise flex flex-col gap-4 xl:sticky xl:top-[100px]" style={{ animationDelay: '80ms' }}>
          <div className="flex items-baseline justify-between">
            <h2 className="display text-[38px]">Script</h2>
            <span className="text-[14px] text-smoke">{words} words</span>
          </div>
          <div className="sheet relative overflow-hidden rounded-[4px]">
            <div className="sheet-margin pointer-events-none absolute inset-0" />
            <div className="sheet-holes pointer-events-none absolute inset-y-0 left-0 w-16" />
            <ScriptEditor
              editorRef={editor}
              script={script}
              sentences={inSync ? sentences : []}
              active={activeIndex}
              onChange={(value, at) => {
                setScript(value)
                setCaret(at)
              }}
              onCaret={setCaret}
            />
          </div>
          <p className="text-[14px] leading-relaxed text-smoke">
            Headings aren't read aloud. <code className="font-script text-dust">[visual: …]</code> chooses the footage for a line,{' '}
            <code className="font-script text-dust">[clip: id]</code> locks a clip. Each colour is one shot.
          </p>
        </section>

        {/* The storyboard: a strip of film */}
        <section className="rise flex flex-col gap-4" style={{ animationDelay: '160ms' }}>
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="display text-[38px]">
              Storyboard{board.isFetching && <span className="ml-4 align-middle font-sans text-[14px] text-smoke">developing…</span>}
            </h2>
            {sentences.length > 0 && (
              <button
                type="button"
                disabled={!inSync || suggest.isPending}
                onClick={() =>
                  canSuggest
                    ? suggest.mutate()
                    : toast('Suggestions need an OpenRouter key', {
                        description: 'Add one in Settings, under AI. Everything else works without it.',
                        action: { label: 'Open Settings', onClick: () => navigate('/settings#ai') },
                      })
                }
                title="Write a footage search for every shot that doesn't have one"
                className="flex cursor-pointer items-center gap-2 text-[15px] text-rev-pink transition-opacity hover:text-bone disabled:cursor-wait disabled:opacity-50"
              >
                <Sparkles className={cn('h-3.5 w-3.5', suggest.isPending && 'animate-spin')} />
                {suggest.isPending ? 'Writing searches…' : 'Suggest footage'}
              </button>
            )}
          </div>

          {sentences.length === 0 ? (
            <EmptyStrip onExample={() => setScript(EXAMPLE)} />
          ) : (
            <ol className="film flex flex-col">
              {sentences.map((s) => (
                <Frame
                  key={`${s.index}-${s.text}`}
                  sentence={s}
                  aspect={options.aspect_ratio}
                  active={activeIndex === s.index}
                  editable={inSync}
                  onFocus={() => focusSentence(s)}
                  onQuery={(q) => inSync && setScript(setQuery(script, s, q))}
                  onPin={(id) => inSync && setScript(setPin(script, s, id))}
                />
              ))}
            </ol>
          )}
        </section>
      </div>

      {/* The console */}
      <div className="pointer-events-none fixed inset-x-0 bottom-5 z-30 flex justify-center px-4">
        <div className="glass pointer-events-auto flex max-w-full items-center gap-1 rounded-[26px] p-2 pl-3">
          {/* Settings scroll sideways on narrow screens; Record video always stays in view. */}
          <div className="flex min-w-0 items-center gap-2 overflow-x-auto [mask-image:linear-gradient(90deg,#000_calc(100%-24px),transparent)] [scrollbar-width:none] sm:[mask-image:none]">
          <Popover trigger={(open) => <ConsoleButton open={open} label="Voice" value={`${provider === 'fish' ? 'Fish Audio' : 'ElevenLabs'} · ${options.speed.toFixed(2)}×`} />}>
            <div className="flex flex-col gap-5">
              <Choice<VoiceProvider>
                value={provider}
                onChange={(p) => setOptions((o) => ({ ...o, voice_provider: p, voice_id: null }))}
                options={[
                  { value: 'elevenlabs', label: 'ElevenLabs' },
                  { value: 'fish', label: 'Fish Audio' },
                ]}
              />
              <VoicePicker
                provider={provider}
                value={options.voice_id}
                fallback={setting(`${provider}_voice_id`)?.value ?? ''}
                onChange={(id) => set('voice_id', id)}
              />
              <Field label={`Pace · ${options.speed.toFixed(2)}×`}>
                <input type="range" min={0.7} max={1.2} step={0.05} value={options.speed} onChange={(e) => set('speed', Number(e.target.value))} />
              </Field>
            </div>
          </Popover>

          <Choice<AspectRatio> value={options.aspect_ratio} onChange={(v) => set('aspect_ratio', v)} options={ASPECTS} />

          <Popover
            trigger={(open) => (
              <ConsoleButton open={open} label="Captions" value={options.captions ? CAPTION_STYLES.find((c) => c.value === options.caption_style)!.label : 'Off'} />
            )}
          >
            <div className="flex flex-col gap-5">
              <Switch checked={options.captions} onChange={(v) => set('captions', v)} label="Burn in captions" />
              <div className="grid grid-cols-3 gap-2">
                {CAPTION_STYLES.map((c) => (
                  <button
                    key={c.value}
                    type="button"
                    aria-pressed={options.caption_style === c.value}
                    disabled={!options.captions}
                    onClick={() => set('caption_style', c.value)}
                    className={cn(
                      'flex cursor-pointer flex-col gap-2 rounded-[14px] p-1.5 ring-1 transition disabled:opacity-30',
                      options.caption_style === c.value ? 'bg-white/[0.06] ring-rev-pink' : 'ring-seam hover:ring-seam-up',
                    )}
                  >
                    <span className="flex h-16 items-end justify-center rounded-[10px] bg-[linear-gradient(160deg,#4a2a36,#140609)] pb-2.5 font-caption text-[11px] text-white">
                      {c.sample}
                    </span>
                    <span className="text-[13px]">{c.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </Popover>

          <Popover trigger={(open) => <ConsoleButton open={open} label="Cut" value={`≤ ${options.max_shot_seconds}s${options.music ? ' · music' : ''}`} />}>
            <EditPanel options={options} set={set} musicName={musicName} setMusicName={setMusicName} />
          </Popover>

          <Popover trigger={(open) => <ConsoleButton open={open} label="Post" value={options.caption || hashtags ? 'Written' : 'Caption'} />}>
            <div className="flex flex-col gap-5">
              <Field label="Caption" hint="Used when you post with Buffer.">
                <Textarea rows={3} value={options.caption} onChange={(e) => set('caption', e.target.value)} />
              </Field>
              <Field label="Hashtags">
                <Input value={hashtags} placeholder="#health #walking" onChange={(e) => setHashtags(e.target.value)} />
              </Field>
            </div>
          </Popover>
          </div>

          <Button
            variant="record"
            size="lg"
            aria-label="Record video"
            className="ml-1 pl-5"
            disabled={sentences.length === 0 || blockers.length > 0}
            loading={submit.isPending}
            onClick={() => submit.mutate()}
          >
            {!submit.isPending && <span className="h-2.5 w-2.5 rounded-full bg-bone" />}
            Record<span className="hidden sm:inline"> video</span>
          </Button>
        </div>
      </div>
    </div>
  )
}

/** The reel title as a marquee: wraps like a heading, edits like a field. */
function TitleField({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // Re-fit whenever the text, the width or the loaded font changes the wrapping.
    const fit = () => {
      el.style.height = '0px'
      el.style.height = `${el.scrollHeight}px`
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(el.parentElement ?? el)
    document.fonts?.ready.then(fit)
    return () => observer.disconnect()
  }, [value])
  return (
    <textarea
      ref={ref}
      aria-label="Title"
      rows={1}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value.replace(/\n/g, ' '))}
      className="display block w-full min-w-0 resize-none overflow-hidden bg-transparent py-[0.04em] text-[clamp(52px,6.6vw,112px)] text-bone outline-none placeholder:text-bone/90"
    />
  )
}

function ConsoleButton({ label, value, open }: { label: string; value: string; open: boolean }) {
  return (
    <button
      type="button"
      aria-expanded={open}
      className={cn(
        'flex h-11 cursor-pointer flex-col items-start justify-center rounded-[16px] px-3.5 text-left transition-colors',
        open ? 'bg-white/[0.09]' : 'hover:bg-white/[0.05]',
      )}
    >
      <span className="flex items-center gap-1 text-[12px] leading-none text-smoke">
        {label}
        <ChevronUp className={cn('h-3 w-3 transition-transform duration-300', !open && 'rotate-180')} />
      </span>
      <span className="mt-1 whitespace-nowrap text-[14px] leading-tight text-bone">{value}</span>
    </button>
  )
}

function EditPanel({
  options,
  set,
  musicName,
  setMusicName,
}: {
  options: VideoOptions
  set: <K extends keyof VideoOptions>(key: K, value: VideoOptions[K]) => void
  musicName: string | null
  setMusicName: (name: string | null) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: (file: File) => api.upload(file),
    onSuccess: (r) => {
      set('music', r.path)
      setMusicName(r.name)
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <div className="flex flex-col gap-6">
      <Field label={`Longest shot · ${options.max_shot_seconds.toFixed(1)}s`} hint="Long sentences are cut into several shots. Shorter feels faster.">
        <input type="range" min={1.5} max={8} step={0.5} value={options.max_shot_seconds} onChange={(e) => set('max_shot_seconds', Number(e.target.value))} />
      </Field>
      <Field label="Music" hint="Plays quietly and dips under the voice." group>
        <input
          ref={input}
          type="file"
          accept="audio/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ''
            if (file) upload.mutate(file)
          }}
        />
        {options.music ? (
          <div className="flex items-center gap-3 rounded-[12px] bg-white/[0.05] px-3.5 py-2.5 text-[13px] ring-1 ring-seam">
            <Music className="h-4 w-4 shrink-0 text-rev-pink" />
            <span className="flex-1 truncate">{musicName}</span>
            <button
              aria-label="Remove music"
              className="cursor-pointer text-smoke hover:text-bone"
              onClick={() => {
                set('music', null)
                setMusicName(null)
              }}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <Button variant="line" loading={upload.isPending} onClick={() => input.current?.click()}>
            <Music className="h-4 w-4" /> Add a music file
          </Button>
        )}
        {options.music && (
          <span className="mt-1 flex items-center gap-3 text-[13px] text-dust">
            Volume
            <input
              aria-label="Music volume"
              className="flex-1"
            type="range"
            min={0.05}
            max={0.5}
            step={0.05}
            value={options.music_volume}
            onChange={(e) => set('music_volume', Number(e.target.value))}
            />
            <span className="w-9 text-right tabular-nums">{Math.round(options.music_volume * 100)}%</span>
          </span>
        )}
      </Field>
    </div>
  )
}

function EmptyStrip({ onExample }: { onExample: () => void }) {
  return (
    <div className="film relative overflow-hidden py-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="mb-3 flex h-40 items-center justify-center rounded-[4px] bg-white/[0.025] last:mb-0">
          <span className="display text-[96px] text-white/[0.05]">{String(i + 1).padStart(2, '0')}</span>
        </div>
      ))}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 bg-[radial-gradient(closest-side,rgba(9,11,17,0.9),rgba(9,11,17,0.6))] px-10 text-center">
        <p className="display text-[52px] text-bone">The strip develops as you write</p>
        <p className="max-w-sm text-[15px] leading-relaxed text-dust">
          Every sentence becomes a frame, with real stock footage to choose from before you spend anything on the voice.
        </p>
        <Button onClick={onExample}>Load an example script</Button>
      </div>
    </div>
  )
}

/** One sentence is one frame on the strip: its line, its search and clips to lock in. */
function Frame({
  sentence,
  aspect,
  active,
  editable,
  onFocus,
  onQuery,
  onPin,
}: {
  sentence: BoardSentence
  aspect: AspectRatio
  active: boolean
  editable: boolean
  onFocus: () => void
  onQuery: (q: string) => void
  onPin: (id: number | null) => void
}) {
  const [draft, setDraft] = useState(sentence.query)
  useEffect(() => setDraft(sentence.query), [sentence.query])
  const results = useQuery({
    queryKey: ['footage', sentence.query, aspect],
    queryFn: () => api.footage(sentence.query, aspect),
    staleTime: Infinity,
    retry: false,
  })
  const pinned = useQuery({
    queryKey: ['clip', sentence.pin],
    queryFn: () => api.clip(sentence.pin!),
    enabled: sentence.pin != null && !results.data?.some((c) => c.id === sentence.pin),
    staleTime: Infinity,
  })
  const lockedClip = results.data?.find((c) => c.id === sentence.pin) ?? (sentence.pin != null ? pinned.data : undefined)
  const clips = [...(lockedClip ? [lockedClip] : []), ...(results.data ?? []).filter((c) => c.id !== sentence.pin)].slice(0, 6)
  const seconds = sentence.text.split(/\s+/).length / WORDS_PER_SECOND
  const portrait = aspect === '9:16' || aspect === '4:5'
  const number = String(sentence.index + 1).padStart(2, '0')
  const color = shotColor(sentence.index)

  return (
    <li
      className="develop relative border-b-[6px] border-[#070205] py-5 transition-colors duration-500 last:border-b-0"
      style={{ animationDelay: `${Math.min(sentence.index, 8) * 60}ms`, backgroundColor: active ? `${color}14` : 'transparent', ['--shot' as string]: color }}
    >
      <span className="edge-code -left-[12px]" style={{ color }}>SHORTSTOCK {number} 5219</span>
      <span className="edge-code -right-[12px]" style={{ color }}>{number}A {timecode(seconds).slice(6)}</span>

      <button type="button" onClick={onFocus} className="group flex w-full cursor-pointer items-start gap-5 px-2 text-left">
        <span
          className={cn('display w-[58px] shrink-0 text-[60px] leading-[0.8] tabular-nums transition-opacity duration-300', active || lockedClip ? 'opacity-100' : 'opacity-75 group-hover:opacity-100')}
          style={{ color }}
        >
          {number}
        </span>
        <span className="flex flex-1 flex-col gap-1.5 pt-0.5">
          <span className="text-[17px] leading-snug text-bone">{sentence.text}</span>
          <span className="text-[13px] text-smoke">about {seconds.toFixed(1)} seconds</span>
        </span>
      </button>

      <div className="mt-4 flex gap-2.5 overflow-x-auto px-2 pb-1 [scrollbar-width:thin]">
        {results.isLoading &&
          Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={cn('shrink-0 animate-pulse rounded-[4px] bg-white/[0.05]', portrait ? 'h-[164px] aspect-[9/16]' : 'h-[104px] aspect-video')} />
          ))}
        {clips.map((clip) => (
          <Thumb
            key={clip.id}
            clip={clip}
            portrait={portrait}
            locked={sentence.pin === clip.id}
            disabled={!editable}
            onClick={() => onPin(sentence.pin === clip.id ? null : clip.id)}
          />
        ))}
        {results.error && <p className="py-6 text-[13px] text-tally">{results.error.message}</p>}
        {results.data?.length === 0 && !lockedClip && (
          <p className="py-6 text-[13px] text-dust">Nothing on Pexels for this search. Try simpler, more visual words.</p>
        )}
      </div>

      <form
        className="mt-3 flex items-center gap-3 px-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (draft.trim() !== sentence.query) onQuery(draft)
        }}
      >
        <Search className="h-3.5 w-3.5 shrink-0 text-smoke" />
        <input
          aria-label={`Footage search for shot ${sentence.index + 1}`}
          value={draft}
          disabled={!editable}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => draft.trim() && draft.trim() !== sentence.query && onQuery(draft)}
          className="h-8 flex-1 rounded-full bg-transparent px-2 font-script text-[14px] text-dust outline-none ring-1 ring-transparent transition focus:bg-white/[0.04] focus:text-bone focus:ring-seam-up"
        />
        <span className="hidden text-[13px] text-smoke sm:inline">{sentence.hint ? 'your search' : 'automatic'}</span>
        {lockedClip && (
          <span className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] text-ink" style={{ backgroundColor: color }}>
            <Lock className="h-3 w-3" /> Locked
          </span>
        )}
      </form>
    </li>
  )
}

function Thumb({
  clip,
  portrait,
  locked,
  disabled,
  onClick,
}: {
  clip: StockClip
  portrait: boolean
  locked: boolean
  disabled: boolean
  onClick: () => void
}) {
  const [hover, setHover] = useState(false)
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      title={locked ? 'Unlock this clip' : `Lock this clip · ${clip.author} on Pexels`}
      aria-label={`${locked ? 'Unlock' : 'Lock'} clip by ${clip.author}, ${Math.round(clip.duration)} seconds`}
      aria-pressed={locked}
      className={cn(
        'group relative shrink-0 cursor-pointer overflow-hidden rounded-[4px] bg-black transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]',
        portrait ? 'h-[164px] aspect-[9/16]' : 'h-[104px] aspect-video',
        locked
          ? 'ring-2 ring-[var(--shot)] shadow-[0_0_34px_-6px_var(--shot)]'
          : 'opacity-75 ring-1 ring-white/10 hover:-translate-y-1 hover:opacity-100 hover:ring-white/40',
      )}
    >
      <img src={clip.image} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
      {hover && <video src={clip.preview} muted autoPlay loop playsInline className="absolute inset-0 h-full w-full object-cover" />}
      <span className="absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/80 to-transparent p-1.5 pt-6">
        <span className="text-[12px] text-white/85">{Math.round(clip.duration)}s</span>
        {locked ? (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--shot)] text-ink">
            <Lock className="h-2.5 w-2.5" />
          </span>
        ) : (
          <span className="text-[12px] text-white opacity-0 transition-opacity group-hover:opacity-100">Lock</span>
        )}
      </span>
    </button>
  )
}

/**
 * The script, written on a revision page. A mirror behind the textarea highlights
 * each sentence in its shot colour, so the page and the strip read as one.
 */
function ScriptEditor({
  editorRef,
  script,
  sentences,
  active,
  onChange,
  onCaret,
}: {
  editorRef: RefObject<HTMLTextAreaElement | null>
  script: string
  sentences: BoardSentence[]
  active: number | null
  onChange: (value: string, caret: number) => void
  onCaret: (caret: number) => void
}) {
  const pieces: ReactNode[] = []
  let at = 0
  for (const s of sentences) {
    if (s.start < at || s.end > script.length) continue
    pieces.push(script.slice(at, s.start))
    const color = shotColor(s.index)
    pieces.push(
      <mark key={s.index} style={{ backgroundColor: `${color}${active === s.index ? 'ff' : 'a6'}` }}>
        {script.slice(s.start, s.end)}
      </mark>,
    )
    at = s.end
  }
  pieces.push(script.slice(at), '\n\u200b')
  const text = 'block w-full whitespace-pre-wrap break-words py-14 pl-[86px] pr-6 font-script text-[16px] font-medium leading-[1.9] sm:pl-[92px] sm:pr-10 sm:text-[17.5px]'
  return (
    <div className="relative min-h-[64vh]">
      <div aria-hidden className={cn('mirror pointer-events-none', text)}>
        {pieces}
      </div>
      <textarea
        ref={editorRef}
        aria-label="Script"
        value={script}
        spellCheck
        onChange={(e) => onChange(e.target.value, e.target.selectionStart)}
        onSelect={(e) => onCaret(e.currentTarget.selectionStart)}
        placeholder={'Paste or write your script.\n\nEvery sentence becomes a shot.\n\nWant a particular shot? Write\n[visual: city skyline at night]\nbefore the sentence.'}
        className={cn(
          text,
          'absolute inset-0 h-full resize-none overflow-hidden bg-transparent text-ink caret-tally outline-none placeholder:text-[#7a5c62] selection:bg-tally/30',
        )}
      />
    </div>
  )
}
