import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowUpRight, Check, Copy, Download, Mic, Send, Shuffle, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { api, type RunDetail } from '../api'
import { PublishDialog } from '../components/PublishDialog'
import { Button, Meta, Panel, Status, cn, formatDuration, runLabel, timeAgo, timecode } from '../components/ui'
import { shotColor } from '../revision'

const STEPS: Record<string, [string, string]> = {
  voice: ['Voice', 'Recording the voiceover'],
  plan: ['Shots', 'Lining shots up with the words'],
  footage: ['Footage', 'Pulling stock footage'],
  render: ['Cut', 'Cutting and captioning'],
}

export function VideoPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const player = useRef<HTMLVideoElement>(null)
  const [publishing, setPublishing] = useState(false)
  const [now, setNow] = useState(0)
  const run = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.run(runId),
    refetchInterval: (query) => (['queued', 'running'].includes(query.state.data?.status ?? '') ? 1500 : false),
  })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const canPublish = ['buffer', 'storage'].every((name) => health.data?.checks.find((c) => c.name === name)?.ok)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['run', runId] })
    queryClient.invalidateQueries({ queryKey: ['runs'] })
  }
  const retry = useMutation({
    mutationFn: (from?: string) => api.retry(runId, from),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      navigate('/library')
    },
    onError: (e) => toast.error(e.message),
  })

  if (run.isLoading) return <p className="text-smoke">Loading the reel…</p>
  if (run.error || !run.data)
    return (
      <div className="flex flex-col items-start gap-5 py-20">
        <p className="display text-[72px]">No such reel</p>
        <Link to="/library">
          <Button variant="line">Back to the library</Button>
        </Link>
      </div>
    )
  const data = run.data
  const video = data.video
  const busy = data.status === 'queued' || data.status === 'running'
  const wide = data.options.aspect_ratio === '16:9'
  const seek = (t: number) => {
    if (!player.current) return
    player.current.currentTime = t + 0.01
    player.current.play()
  }
  const currentShot = data.shots.findIndex((s) => now >= s.start && now < s.end)

  return (
    <div className="flex flex-col gap-10">
      <header className="rise flex flex-col gap-5">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <h1 className="display max-w-4xl text-[clamp(52px,6.6vw,112px)]">{runLabel(data)}</h1>
          <div className="flex shrink-0 flex-wrap items-center gap-2 lg:flex-nowrap">
            {data.status === 'completed' && (
              <>
                <Button variant="line" loading={retry.isPending && retry.variables === 'footage'} onClick={() => retry.mutate('footage')} title="Keep the voice, choose different clips">
                  <Shuffle className="h-4 w-4" /> New footage
                </Button>
                <Button variant="line" loading={retry.isPending && retry.variables === 'voice'} onClick={() => retry.mutate('voice')} title="Record the voiceover again">
                  <Mic className="h-4 w-4" /> Re-record voice
                </Button>
              </>
            )}
            {data.status === 'failed' && (
              <Button loading={retry.isPending} onClick={() => retry.mutate(undefined)}>
                Try again
              </Button>
            )}
            <DeleteButton disabled={data.status === 'running'} loading={remove.isPending} onDelete={() => remove.mutate()} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Status value={data.status} />
          <Meta>{timeAgo(data.created_at)}</Meta>
          <Meta>{data.options.aspect_ratio}</Meta>
          {data.voice && (
            <Meta>
              {data.voice.provider === 'Fish' ? 'Fish Audio' : 'ElevenLabs'}, {Math.round(data.voice.wpm)} words a minute
            </Meta>
          )}
          {video && <Meta>{formatDuration(video.duration_seconds)} long</Meta>}
          <Link to="/library" className="ml-auto flex items-center gap-2 text-[14px] text-smoke transition-colors hover:text-bone">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to the library
          </Link>
        </div>
      </header>

      {(busy || data.status === 'failed') && <Gate run={data} />}

      {video && (
        <div className={cn('grid grid-cols-1 items-start gap-10', !wide && 'lg:grid-cols-[minmax(0,460px)_minmax(0,1fr)]')}>
          <div className="rise flex flex-col gap-4">
            <div className="projector -mx-10 -mt-10 px-10 pt-10">
              <div className="overflow-hidden rounded-[10px] bg-black shadow-[0_40px_120px_-30px_rgba(0,0,0,0.95),0_0_0_1px_rgba(255,255,255,0.06)]">
                <video
                  ref={player}
                  src={video.url}
                  poster={video.poster_url}
                  controls
                  preload="metadata"
                  onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
                  className={cn('w-full', wide ? 'aspect-video' : 'aspect-[9/16] max-h-[780px] object-contain')}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <a href={video.download_url} className="flex-1">
                <Button size="lg" className="w-full">
                  <Download className="h-4 w-4" /> Download MP4
                </Button>
              </a>
              {canPublish && (
                <Button size="lg" variant="line" className="flex-1" onClick={() => setPublishing(true)}>
                  <Send className="h-4 w-4" /> Post
                </Button>
              )}
            </div>
            {!canPublish && (
              <p className="text-[13px] text-smoke">
                Post straight to TikTok, Reels or Shorts by{' '}
                <Link to="/settings#publishing" className="text-dust underline decoration-rev-pink underline-offset-4 hover:text-bone">
                  connecting Buffer
                </Link>
                .
              </p>
            )}
            {data.posts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {data.posts.map((p) => (
                  <span key={p.id} title={p.error ?? undefined} className={cn('rounded-full px-2.5 py-1 text-[13px]', p.status === 'failed' ? 'bg-tally/15 text-tally' : 'bg-go/15 text-go')}>
                    {p.channel_name ?? p.service} · {p.status === 'failed' ? 'failed' : p.mode}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="rise flex flex-col gap-6" style={{ animationDelay: '120ms' }}>
            <CutList run={data} current={currentShot} onSeek={seek} />
            <div className="grid gap-6 md:grid-cols-2">
              {(video.caption || video.hashtags.length > 0) && <CopyCard label="Post caption" text={`${video.caption}\n\n${video.hashtags.join(' ')}`.trim()} />}
              {data.credits.length > 0 && <Credits run={data} />}
            </div>
          </div>
        </div>
      )}

      {publishing && video && (
        <PublishDialog item={{ id: video.id, title: video.title, caption: video.caption, hashtags: video.hashtags }} onClose={() => setPublishing(false)} onDone={refresh} />
      )}
    </div>
  )
}

/** Delete in two steps, inside the page: the bin asks once, then deletes. */
function DeleteButton({ disabled, loading, onDelete }: { disabled: boolean; loading: boolean; onDelete: () => void }) {
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    if (!asking) return
    const t = setTimeout(() => setAsking(false), 5000)
    return () => clearTimeout(t)
  }, [asking])
  if (asking)
    return (
      <span className="rise flex items-center gap-1.5">
        <Button variant="ghost" onClick={() => setAsking(false)}>
          Keep
        </Button>
        <Button variant="record" loading={loading} onClick={onDelete}>
          <Trash2 className="h-4 w-4" /> Delete video and files
        </Button>
      </span>
    )
  return (
    <Button variant="danger" aria-label="Delete video" title="Delete video" className="w-10 !px-0" disabled={disabled} onClick={() => setAsking(true)}>
      <Trash2 className="h-4 w-4" />
    </Button>
  )
}

/** While the reel is being made: film running through the gate, and the step it is on. */
function Gate({ run }: { run: RunDetail }) {
  const active = run.stages.find((s) => s.status === 'running')
  return (
    <section className="rise flex flex-col gap-8">
      <Panel className="overflow-hidden">
        <div className={cn('h-[18px] w-full', run.status === 'running' && 'gate')} />
        <ol className="grid grid-cols-2 gap-px bg-seam md:grid-cols-4">
          {run.stages.map((stage, i) => (
            <li key={stage.name} className="flex flex-col gap-3 bg-booth px-6 py-6">
              <span className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2 w-2 rounded-full',
                    stage.status === 'done' && 'bg-go',
                    stage.status === 'running' && 'tally',
                    stage.status === 'failed' && 'bg-tally',
                    stage.status === 'pending' && 'bg-white/15',
                  )}
                />
                <span className="text-[13px] text-smoke">Step {i + 1}</span>
              </span>
              <span
                className={cn(
                  'display text-[52px] transition-colors',
                  stage.status === 'pending' && 'text-white/15',
                  stage.status === 'running' && 'text-bone',
                  stage.status === 'failed' && 'text-tally',
                )}
                style={stage.status === 'done' ? { color: shotColor(i) } : undefined}
              >
                {stage.status === 'done' ? (
                  <span className="flex items-center gap-2">
                    {STEPS[stage.name][0]} <Check className="h-7 w-7" />
                  </span>
                ) : (
                  STEPS[stage.name][0]
                )}
              </span>
            </li>
          ))}
        </ol>
        {run.status === 'failed' ? (
          <Failure run={run} />
        ) : (
          <div className="border-t border-seam px-6 py-4 text-[15px]">
            {run.status === 'queued' && <span className="text-dust">Waiting for the video ahead of this one to finish.</span>}
            {active && <span className="text-bone">{STEPS[active.name][1]}…</span>}
          </div>
        )}
      </Panel>
      {run.status !== 'failed' && (
        <div className="sheet relative mx-auto w-full max-w-3xl overflow-hidden rounded-[4px] opacity-90">
          <div className="sheet-margin pointer-events-none absolute inset-0" />
          <div className="sheet-holes pointer-events-none absolute inset-y-0 left-0 w-16" />
          <p className="relative whitespace-pre-wrap py-14 pl-[92px] pr-10 font-script text-[16px] leading-[1.9] text-ink">{run.script}</p>
        </div>
      )}
    </section>
  )
}

const FIX: Record<string, { tab: string; label: string }> = {
  voice: { tab: 'voice', label: 'Voice settings' },
  plan: { tab: 'ai', label: 'AI settings' },
  footage: { tab: 'footage', label: 'Footage settings' },
  render: { tab: 'system', label: 'System check' },
}

/** Why the video stopped, in words, with the way to fix it. */
function Failure({ run }: { run: RunDetail }) {
  const failed = run.stages.find((s) => s.status === 'failed')
  const step = failed ? STEPS[failed.name][0] : 'A step'
  const message = (run.error ?? 'Something went wrong.').replace(/^\w+:\s*/, '')
  const fix = failed ? FIX[failed.name] : undefined
  return (
    <div className="flex flex-col gap-4 border-t border-seam bg-tally/[0.07] px-6 py-6 sm:flex-row sm:items-center">
      <div className="flex flex-1 flex-col gap-1.5">
        <p className="text-[17px] text-bone">The video stopped at the {step.toLowerCase()} step.</p>
        <p className="max-w-3xl text-[15px] leading-relaxed text-dust">{message}</p>
      </div>
      {fix && (
        <Link to={`/settings#${fix.tab}`} className="shrink-0">
          <Button variant="line">{fix.label}</Button>
        </Link>
      )}
    </div>
  )
}

/** The edit as cut: a strip of frames to scrub, then every shot with its line. */
function CutList({ run, current, onSeek }: { run: RunDetail; current: number; onSeek: (t: number) => void }) {
  const total = run.voice?.duration_seconds ?? run.shots.at(-1)?.end ?? 1
  return (
    <Panel className="overflow-hidden">
      <div className="flex items-baseline justify-between px-6 pb-4 pt-6">
        <h2 className="display text-[38px]">Cut list</h2>
        <span className="text-[14px] text-smoke">
          {run.shots.length} shots, <span className="font-script">{timecode(total)}</span>
        </span>
      </div>
      <div className="film !rounded-none !px-[30px] py-3">
        <div className="flex h-[92px] gap-[3px]">
          {run.shots.map((s, i) => (
            <button
              key={s.index}
              onClick={() => onSeek(s.start)}
              title={`${timecode(s.start)} · ${s.text}`}
              className={cn(
                'relative h-full cursor-pointer overflow-hidden rounded-[3px] bg-black transition-all duration-300',
                i === current ? 'ring-2 ring-[var(--shot)]' : 'opacity-70 hover:opacity-100',
              )}
              style={{ width: `${(s.duration / total) * 100}%`, ['--shot' as string]: shotColor(s.sentence) }}
            >
              {s.thumb ? (
                <img src={s.thumb} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="display flex h-full w-full items-center justify-center text-[22px] text-ink" style={{ backgroundColor: shotColor(s.sentence) }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
              )}
              <span className="absolute inset-x-0 bottom-0 h-[3px] bg-[var(--shot)]" />
            </button>
          ))}
        </div>
      </div>
      <ol className="max-h-[420px] overflow-y-auto">
        {run.shots.map((shot, i) => (
          <li key={shot.index}>
            <button
              onClick={() => onSeek(shot.start)}
              className="flex w-full cursor-pointer items-start gap-5 border-t border-seam px-6 py-4 text-left transition-colors hover:bg-white/[0.03]"
              style={i === current ? { backgroundColor: `${shotColor(shot.sentence)}14` } : undefined}
            >
              <span
                className={cn('display w-11 shrink-0 text-[38px] leading-[0.85] tabular-nums transition-opacity', i === current ? 'opacity-100' : 'opacity-50')}
                style={{ color: shotColor(shot.sentence) }}
              >
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                <span className="text-[15px] leading-snug text-bone">{shot.text}</span>
                <span className="flex flex-wrap gap-x-4 font-script text-[13px] text-smoke">
                  <span className="text-dust">{timecode(shot.start)}</span>
                  <span>{shot.query}</span>
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

/** Footage credits, rolling like the end of a film. */
function Credits({ run }: { run: RunDetail }) {
  const names = run.credits
  const loop = [...names, ...names]
  return (
    <Panel className="flex flex-col p-6">
      <h2 className="display text-[32px]">Footage by</h2>
      <div className="credits relative mt-4 h-[180px] overflow-hidden">
        <ul className={cn('flex flex-col items-center gap-3 text-center', names.length > 4 && 'credits-roll')}>
          {(names.length > 4 ? loop : names).map((c, i) => (
            <li key={`${c.id}-${i}`}>
              <a href={c.url} target="_blank" rel="noreferrer" className="group inline-flex items-center gap-1 text-[16px] text-dust hover:text-bone">
                {c.author}
                <ArrowUpRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
              </a>
            </li>
          ))}
        </ul>
      </div>
      <span className="mt-4 text-center text-[13px] text-smoke">on Pexels</span>
    </Panel>
  )
}

function CopyCard({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Panel className="relative flex flex-col p-6 pr-14">
      <h2 className="display text-[32px]">{label}</h2>
      <p className="mt-4 whitespace-pre-line text-[15px] leading-relaxed text-bone">{text}</p>
      <button
        aria-label={`Copy ${label.toLowerCase()}`}
        className="absolute right-4 top-4 cursor-pointer rounded-full p-2 text-smoke transition-colors hover:bg-white/[0.06] hover:text-bone"
        onClick={() => {
          navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
      >
        {copied ? <Check className="h-4 w-4 text-go" /> : <Copy className="h-4 w-4" />}
      </button>
    </Panel>
  )
}
