export type RunStatus = 'queued' | 'running' | 'completed' | 'failed'
export type StageStatus = 'pending' | 'running' | 'done' | 'failed'
export type AspectRatio = '9:16' | '4:5' | '1:1' | '16:9'
export type CaptionStyle = 'bold' | 'highlight' | 'minimal'
export type VoiceProvider = 'elevenlabs' | 'fish'
export type PublishMode = 'queue' | 'now' | 'schedule' | 'draft'

export interface VideoOptions {
  voice_provider: VoiceProvider | null
  voice_id: string | null
  speed: number
  aspect_ratio: AspectRatio
  captions: boolean
  caption_style: CaptionStyle
  max_shot_seconds: number
  music: string | null
  music_volume: number
  caption: string
  hashtags: string[]
}

export interface Run {
  id: string
  script: string
  title: string | null
  status: RunStatus
  current_stage: string | null
  error: string | null
  options: VideoOptions
  created_at: string
  updated_at: string
  video_id?: string | null
  duration_seconds?: number | null
}

export interface Stage {
  name: string
  label: string
  status: StageStatus
  error?: string | null
}

export interface Video {
  id: string
  run_id: string
  title: string
  caption: string
  hashtags: string[]
  width: number | null
  height: number | null
  duration_seconds: number | null
  filename: string
  url: string
  download_url: string
  poster_url: string
}

export interface BoardSentence {
  index: number
  text: string
  hint: string | null
  pin: number | null
  start: number
  end: number
  hint_span: [number, number] | null
  pin_span: [number, number] | null
  query: string
  query_source: 'hint' | 'keywords'
}

export interface Storyboard {
  title: string | null
  sentences: BoardSentence[]
  words: number
}

export interface StockClip {
  id: number
  duration: number
  width: number
  height: number
  image: string
  preview: string
  author: string
  page: string
}

export interface Shot {
  sentence: number
  thumb: string | null
  index: number
  start: number
  end: number
  duration: number
  query: string
  text: string
  clip_id: number | null
}

export interface Credit {
  id: number
  author: string
  url: string
}

export interface Post {
  id: string
  video_id: string
  channel_id: string
  channel_name: string | null
  service: string | null
  mode: PublishMode
  status: 'sent_to_buffer' | 'failed'
  error: string | null
}

export interface RunDetail extends Run {
  stages: Stage[]
  video: Video | null
  voice: { duration_seconds: number; timed_ratio: number; wpm: number; provider: string } | null
  shots: Shot[]
  credits: Credit[]
  posts: Post[]
}

export interface Setting {
  key: string
  value: string
  is_set: boolean
  secret: boolean
  source: 'app' | 'env' | 'default'
  env: string
  description: string
}

export interface Check {
  name: string
  label: string
  ok: boolean
  required: boolean
  detail: string
}

export interface Health {
  version: string
  checks: Check[]
  queue: { queued: number; running: number }
  worker: boolean
}

export interface Model {
  id: string
  name: string
  context_length: number | null
  prompt_price_per_million: number | null
}

export interface VoiceOption {
  id: string
  name: string
  description: string
  preview_url: string | null
}

export interface Channel {
  id: string
  name: string
  service: string
  avatar: string
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* not JSON */
    }
    throw new ApiError(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health'),
  settings: () => request<Setting[]>('/api/settings'),
  saveSettings: (values: Record<string, string | null>) =>
    request<Setting[]>('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  models: () => request<Model[]>('/api/models'),
  voices: (provider: VoiceProvider, search = '', current: string | null = null) =>
    request<VoiceOption[]>(
      `/api/voices?provider=${provider}&search=${encodeURIComponent(search)}${current ? `&current=${encodeURIComponent(current)}` : ''}`,
    ),
  storyboard: (script: string) => request<Storyboard>('/api/storyboard', { method: 'POST', body: JSON.stringify({ script }) }),
  suggest: (script: string) =>
    request<{ index: number; query: string }[]>('/api/storyboard/suggest', { method: 'POST', body: JSON.stringify({ script }) }),
  footage: (q: string, aspect: AspectRatio) => request<StockClip[]>(`/api/footage/search?q=${encodeURIComponent(q)}&aspect=${aspect}`),
  clip: (id: number) => request<StockClip>(`/api/footage/${id}`),
  runs: () => request<Run[]>('/api/runs'),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  createRun: (script: string, title: string | null, options: VideoOptions) =>
    request<Run>('/api/runs', { method: 'POST', body: JSON.stringify({ script, title, options }) }),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ path: string; name: string }>('/api/uploads', { method: 'POST', body: form })
  },
  retry: (id: string, fromStage?: string) =>
    request<RunDetail>(`/api/runs/${id}/retry`, { method: 'POST', body: JSON.stringify({ from_stage: fromStage ?? null }) }),
  deleteRun: (id: string) => request<{ deleted: string }>(`/api/runs/${id}`, { method: 'DELETE' }),
  channels: () => request<Channel[]>('/api/buffer/channels'),
  organizations: () => request<{ id: string; name: string }[]>('/api/buffer/organizations'),
  publish: (
    videoId: string,
    body: { channel_ids: string[]; mode: PublishMode; scheduled_at?: string | null; text?: string; title?: string },
  ) => request<Post[]>(`/api/videos/${videoId}/publish`, { method: 'POST', body: JSON.stringify(body) }),
}

export const DEFAULT_OPTIONS: VideoOptions = {
  voice_provider: null,
  voice_id: null,
  speed: 1,
  aspect_ratio: '9:16',
  captions: true,
  caption_style: 'bold',
  max_shot_seconds: 3.5,
  music: null,
  music_volume: 0.15,
  caption: '',
  hashtags: [],
}
