import { useQuery } from '@tanstack/react-query'
import { Pause, Play, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type VoiceProvider } from '../api'
import { Button, Input, Select } from './ui'

/** Voice list from the provider, Fish Audio library search, and previews. */
export function VoicePicker({
  provider,
  value,
  fallback,
  onChange,
}: {
  provider: VoiceProvider
  value: string | null
  fallback: string
  onChange: (id: string | null) => void
}) {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null)
  const current = value ?? fallback
  const voices = useQuery({
    queryKey: ['voices', provider, query, provider === 'fish' ? current : null],
    queryFn: () => api.voices(provider, query, provider === 'fish' ? current : null),
    // Keep the old list while a search loads, but never show one provider's voices under another.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[1] === provider ? previous : undefined),
    staleTime: 10 * 60_000,
    retry: false,
  })
  const selected = voices.data?.find((v) => v.id === current)

  useEffect(() => () => audio?.pause(), [audio])

  const preview = () => {
    if (audio) {
      audio.pause()
      return setAudio(null)
    }
    if (!selected?.preview_url) return
    const next = new Audio(selected.preview_url)
    next.onended = () => setAudio(null)
    next.play()
    setAudio(next)
  }

  return (
    <div className="flex flex-col gap-2">
      {provider === 'fish' && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setQuery(search.trim())
          }}
        >
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search the Fish Audio library" aria-label="Search Fish voices" />
          <Button type="submit" variant="line" className="h-11 w-11 !px-0" aria-label="Search">
            <Search className="h-4 w-4" />
          </Button>
        </form>
      )}
      {voices.error ? (
        <p className="break-words text-[13px] text-tally">{voices.error.message}</p>
      ) : (
        <div className="flex gap-2">
          <Select value={current} onChange={(e) => onChange(e.target.value || null)} aria-label="Voice">
            {!selected && <option value={current}>{voices.isLoading ? 'Loading voices…' : current ? 'Saved voice' : 'Choose a voice'}</option>}
            {(voices.data ?? []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </Select>
          {selected?.preview_url && (
            <Button variant="line" className="h-11 w-11 !px-0" aria-label={audio ? 'Stop preview' : 'Play a sample of this voice'} title={audio ? 'Stop' : 'Play a sample'} onClick={preview}>
              {audio ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
          )}
        </div>
      )}
      {provider === 'fish' && <p className="text-[13px] text-smoke">Check a voice's licence before using it commercially.</p>}
    </div>
  )
}
