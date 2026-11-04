import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, type Run } from '../api'
import { Button, Meta, Status, cn, formatDuration, runLabel, timeAgo } from '../components/ui'
import { shotColor } from '../revision'

export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: api.runs,
    refetchInterval: (query) => (query.state.data?.some((r) => r.status === 'queued' || r.status === 'running') ? 2000 : 15000),
  })
}

export function LibraryPage() {
  const runs = useRuns()
  const count = runs.data?.length ?? 0
  return (
    <div className="flex flex-col gap-12">
      <header className="rise flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <h1 className="display text-[clamp(64px,9vw,148px)]">Library</h1>
        <Link to="/">
          <Button size="lg">Write a new script</Button>
        </Link>
      </header>

      {runs.isLoading ? (
        <p className="text-smoke">Loading…</p>
      ) : count === 0 ? (
        <div className="rise flex flex-col items-start gap-5 rounded-[22px] p-10 ring-1 ring-seam">
          <p className="display text-[56px]">Nothing in the can yet</p>
          <p className="max-w-md text-dust">Write a script, lock the footage you like and press Record video. Finished reels land here.</p>
          <Link to="/">
            <Button>Open the script</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-x-6 gap-y-12 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
          {runs.data!.map((run, i) => (
            <Poster key={run.id} run={run} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}

/** A poster that starts playing when you hover it. */
function Poster({ run, index }: { run: Run; index: number }) {
  const [hover, setHover] = useState(false)
  const wide = run.options.aspect_ratio === '16:9'
  return (
    <Link
      to={`/videos/${run.id}`}
      className="develop group flex flex-col gap-4"
      style={{ animationDelay: `${Math.min(index, 10) * 50}ms`, ['--poster' as string]: shotColor(index) }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        className={cn(
          'relative overflow-hidden rounded-[8px] bg-booth ring-1 ring-seam transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:-translate-y-1.5 group-hover:shadow-[0_30px_60px_-20px_rgba(0,0,0,0.9),0_0_60px_-20px_var(--poster)] group-hover:ring-white/20',
          wide ? 'aspect-video' : 'aspect-[9/16]',
        )}
      >
        {run.video_id ? (
          <>
            <img src={`/api/videos/${run.video_id}/poster`} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
            {hover && <video src={`/api/videos/${run.video_id}/file`} muted autoPlay loop playsInline className="absolute inset-0 h-full w-full object-cover" />}
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <div className={cn('h-[14px] w-full', run.status !== 'failed' && 'gate')} />
            <span className={cn('text-[14px]', run.status === 'failed' ? 'text-tally' : 'text-dust')}>
              {run.status === 'failed' ? 'Failed' : run.status === 'queued' ? 'Waiting' : `${run.current_stage ?? 'Starting'}…`}
            </span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-2.5">
          <span className="rounded-full bg-black/55 px-2 py-0.5 text-[12px] text-white/85 backdrop-blur">{run.options.aspect_ratio}</span>
          {run.duration_seconds != null && (
            <span className="rounded-full bg-black/55 px-2 py-0.5 text-[12px] text-white/85 backdrop-blur">
              {formatDuration(run.duration_seconds)}
            </span>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <p className="display line-clamp-2 text-[28px] leading-[0.95] transition-colors group-hover:text-[var(--poster)]">{runLabel(run)}</p>
        <div className="flex items-center justify-between">
          <Status value={run.status} />
          <Meta>{timeAgo(run.created_at)}</Meta>
        </div>
      </div>
    </Link>
  )
}
