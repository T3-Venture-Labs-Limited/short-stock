import { useQuery } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { api } from '../api'
import { Input } from './ui'

/** Free-text model id with suggestions loaded from the provider the first time it is focused. */
export function ModelInput({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  const id = useId()
  const [wanted, setWanted] = useState(false)
  const models = useQuery({ queryKey: ['models'], queryFn: api.models, enabled: wanted, staleTime: 60 * 60 * 1000 })
  return (
    <>
      <Input value={value} placeholder={placeholder} list={id} onFocus={() => setWanted(true)} onChange={(e) => onChange(e.target.value)} />
      <datalist id={id}>
        {(models.data ?? []).map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
            {m.prompt_price_per_million != null ? ` · $${m.prompt_price_per_million}/M in` : ''}
          </option>
        ))}
      </datalist>
    </>
  )
}
