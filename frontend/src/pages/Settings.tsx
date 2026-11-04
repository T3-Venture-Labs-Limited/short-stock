import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { api, type Setting, type VoiceProvider } from '../api'
import { ModelInput } from '../components/ModelInput'
import { Button, Choice, Field, Input, Panel, Select, cn } from '../components/ui'
import { VoicePicker } from '../components/VoicePicker'

const TABS = [
  { id: 'voice', label: 'Voice', checks: ['voice'] },
  { id: 'footage', label: 'Footage', checks: ['footage'] },
  { id: 'ai', label: 'AI', checks: ['ai'] },
  { id: 'publishing', label: 'Posting', checks: ['buffer', 'storage'] },
  { id: 'system', label: 'System', checks: ['ffmpeg', 'captions'] },
] as const
type Tab = (typeof TABS)[number]['id']

const ELEVEN_MODELS = [
  ['eleven_multilingual_v2', 'Multilingual v2 · best quality'],
  ['eleven_v3', 'v3 · most expressive'],
  ['eleven_flash_v2_5', 'Flash v2.5 · fastest, cheapest'],
]
const FISH_MODELS = [
  ['s2.1-pro', 'S2.1 Pro'],
  ['s2.1-pro-free', 'S2.1 Pro Free · no credit needed'],
  ['s2-pro', 'S2 Pro'],
  ['s1', 'S1'],
]

export function SettingsPage() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const tab = (TABS.find((t) => `#${t.id}` === location.hash)?.id ?? 'voice') as Tab
  const setTab = (id: Tab) => navigate({ hash: id }, { replace: true })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const [draft, setDraft] = useState<Record<string, string>>({})

  const initial = () => Object.fromEntries((settings.data ?? []).map((s) => [s.key, s.secret ? '' : s.value]))
  useEffect(() => {
    if (settings.data) setDraft(initial())
  }, [settings.data])

  const byKey: Record<string, Setting> = Object.fromEntries((settings.data ?? []).map((s) => [s.key, s]))
  const checks = Object.fromEntries((health.data?.checks ?? []).map((c) => [c.name, c]))
  const orgs = useQuery({ queryKey: ['orgs'], queryFn: api.organizations, enabled: !!byKey.buffer_api_key?.is_set })

  const changes = () => {
    const values: Record<string, string | null> = {}
    for (const s of settings.data ?? []) {
      const next = draft[s.key] ?? ''
      if (s.secret ? next : next !== s.value) values[s.key] = next || null
    }
    return values
  }
  const dirty = Object.keys(changes()).length > 0
  const save = useMutation({
    mutationFn: () => api.saveSettings(changes()),
    onSuccess: () => {
      toast.success('Settings saved')
      queryClient.invalidateQueries()
    },
    onError: (e) => toast.error(e.message),
  })
  const clear = useMutation({
    mutationFn: (key: string) => api.saveSettings({ [key]: null }),
    onSuccess: () => queryClient.invalidateQueries(),
  })

  if (settings.isLoading) return <p className="text-smoke">Loading…</p>

  const update = (key: string) => (value: string) => setDraft((d) => ({ ...d, [key]: value }))
  const text = (key: string, placeholder?: string) => (
    <Input value={draft[key] ?? ''} placeholder={placeholder} onChange={(e) => update(key)(e.target.value)} />
  )
  const secret = (key: string, placeholder: string) => {
    const s = byKey[key]
    return (
      <div className="flex gap-2">
        <Input
          type="password"
          autoComplete="off"
          className="font-script"
          value={draft[key] ?? ''}
          placeholder={s?.is_set ? `${s.value}${s.source === 'env' ? '  (from environment)' : ''}` : placeholder}
          onChange={(e) => update(key)(e.target.value)}
        />
        {s?.is_set && s.source === 'app' && (
          <Button variant="line" onClick={() => clear.mutate(key)}>
            Remove
          </Button>
        )}
      </div>
    )
  }
  const tabState = (names: readonly string[]) =>
    names.every((n) => checks[n]?.ok) ? 'bg-go' : names.some((n) => checks[n]?.required && !checks[n]?.ok) ? 'bg-tally' : 'bg-white/15'
  const provider = (draft.tts_provider || 'elevenlabs') as VoiceProvider

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <h1 className="display text-[clamp(64px,9vw,148px)]">Settings</h1>

      {dirty && (
        <div className="fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
          <div className="glass rise flex items-center gap-4 rounded-[22px] py-2 pl-5 pr-2">
            <span className="text-[15px] text-dust">You have unsaved changes</span>
            <Button variant="ghost" onClick={() => setDraft(initial())}>
              Undo
            </Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>
              Save changes
            </Button>
          </div>
        </div>
      )}

      <div className="flex gap-1 overflow-x-auto rounded-full bg-white/[0.04] p-1 ring-1 ring-seam">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'flex flex-1 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-full px-2 py-2 text-[14px] transition-colors sm:px-3 sm:text-[15px]',
              tab === t.id ? 'bg-bone text-night' : 'text-dust hover:text-bone',
            )}
          >
            <span className={cn('hidden h-2 w-2 rounded-full sm:inline-block', tabState(t.checks))} />
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'voice' && (
        <Section intro="Your script is read by ElevenLabs or Fish Audio. Both send back the timing of every word, so cuts and captions land on the words.">
          <Field label="Default voice provider" group>
            <Choice<VoiceProvider>
              value={provider}
              onChange={(p) => update('tts_provider')(p)}
              className="w-72"
              options={[
                { value: 'elevenlabs', label: 'ElevenLabs' },
                { value: 'fish', label: 'Fish Audio' },
              ]}
            />
          </Field>
          <Panel className="flex flex-col gap-5 !bg-white/[0.025] p-6">
            <p className="display text-[38px]">ElevenLabs</p>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="API key" hint={<Ext href="https://elevenlabs.io/app/settings/api-keys">Create a key</Ext>}>
                {secret('elevenlabs_api_key', 'sk_…')}
              </Field>
              <Field label="Model">
                <Select value={draft.elevenlabs_model ?? ''} onChange={(e) => update('elevenlabs_model')(e.target.value)}>
                  {ELEVEN_MODELS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {byKey.elevenlabs_api_key?.is_set && (
              <Field label="Default voice" group>
                <VoicePicker
                  provider="elevenlabs"
                  value={draft.elevenlabs_voice_id || null}
                  fallback={byKey.elevenlabs_voice_id?.value ?? ''}
                  onChange={(id) => update('elevenlabs_voice_id')(id ?? '')}
                />
              </Field>
            )}
          </Panel>
          <Panel className="flex flex-col gap-5 !bg-white/[0.025] p-6">
            <p className="display text-[38px]">Fish Audio</p>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="API key" hint={<Ext href="https://fish.audio/app/api-keys">Create a key</Ext>}>
                {secret('fish_api_key', 'Fish key')}
              </Field>
              <Field label="Model">
                <Select value={draft.fish_model ?? ''} onChange={(e) => update('fish_model')(e.target.value)}>
                  {FISH_MODELS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {byKey.fish_api_key?.is_set && (
              <Field label="Default voice" hint="Your own voices are listed first. Search to browse the public library." group>
                <VoicePicker
                  provider="fish"
                  value={draft.fish_voice_id || null}
                  fallback={byKey.fish_voice_id?.value ?? ''}
                  onChange={(id) => update('fish_voice_id')(id ?? '')}
                />
                <label className="mt-2 flex flex-col gap-1.5 text-[13px] text-smoke">
                  Or paste a voice ID from fish.audio
                  {text('fish_voice_id', 'For example 764957cdfcc14913ad3c659b2b0cb46c')}
                </label>
              </Field>
            )}
          </Panel>
        </Section>
      )}

      {tab === 'footage' && (
        <Section intro="Stock video comes from Pexels, which is free. Clips you use are cached on this machine and reused.">
          <Field label="Pexels API key" hint={<Ext href="https://www.pexels.com/api/">Get a free key</Ext>}>
            {secret('pexels_api_key', 'Pexels key')}
          </Field>
        </Section>
      )}

      {tab === 'ai' && (
        <Section intro="Optional. Suggest footage asks an AI model to write a search for every line without one. Without a key, shortstock searches with keywords from the sentence.">
          <Field label="OpenRouter API key" hint={<Ext href="https://openrouter.ai/keys">Create a key</Ext>}>
            {secret('openrouter_api_key', 'sk-or-…')}
          </Field>
          <Field label="Model" hint="Any fast, cheap model works. A video costs a fraction of a cent.">
            <ModelInput value={draft.llm_model ?? ''} onChange={update('llm_model')} />
          </Field>
        </Section>
      )}

      {tab === 'publishing' && (
        <Section intro="Optional. Videos are always downloadable. Connect Buffer to post or schedule them to TikTok, Instagram, YouTube and more.">
          <Field label="Buffer API key" hint={<Ext href="https://publish.buffer.com/settings/api">Create a key in Buffer</Ext>}>
            {secret('buffer_api_key', 'Buffer key')}
          </Field>
          {(orgs.data?.length ?? 0) > 1 && (
            <Field label="Organization">
              <Select value={draft.buffer_organization_id ?? ''} onChange={(e) => update('buffer_organization_id')(e.target.value)}>
                <option value="">First organization</option>
                {orgs.data!.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Panel className="flex flex-col gap-5 !bg-white/[0.025] p-6">
            <div>
              <p className="display text-[38px]">Video hosting for Buffer</p>
              <p className="mt-2 text-[14px] leading-relaxed text-dust">
                Buffer fetches videos from a public link, so each video is uploaded to your own S3-compatible bucket first: Cloudflare R2,
                Backblaze B2, AWS S3 or MinIO.
              </p>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Endpoint URL" hint="Leave empty for AWS S3">
                {text('s3_endpoint_url', 'https://<account>.r2.cloudflarestorage.com')}
              </Field>
              <Field label="Region">{text('s3_region', 'auto')}</Field>
              <Field label="Bucket">{text('s3_bucket')}</Field>
              <Field label="Public base URL" hint="Optional. Without it, links are signed for 7 days">
                {text('s3_public_base_url', 'https://media.example.com')}
              </Field>
              <Field label="Access key ID">{secret('s3_access_key_id', 'Access key ID')}</Field>
              <Field label="Secret access key">{secret('s3_secret_access_key', 'Secret')}</Field>
            </div>
          </Panel>
        </Section>
      )}

      {tab === 'system' && (
        <Section intro="What shortstock checks before it records.">
          <ul className="flex flex-col divide-y divide-seam">
            {(health.data?.checks ?? []).map((c) => (
              <li key={c.name} className="flex items-start gap-3 py-3">
                <span className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', c.ok ? 'bg-go' : c.required ? 'bg-tally' : 'bg-white/15')} />
                <div>
                  <p className="text-[16px] text-bone">{c.label}</p>
                  <p className="text-[13px] text-dust">{c.detail}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className="font-script text-[12px] text-smoke">shortstock v{health.data?.version}</p>
        </Section>
      )}
    </div>
  )
}

function Section({ intro, children }: { intro: string; children: ReactNode }) {
  return (
    <Panel className="rise flex flex-col gap-7 p-8">
      <p className="max-w-2xl text-[16px] leading-relaxed text-dust">{intro}</p>
      {children}
    </Panel>
  )
}

function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-rev-pink hover:text-bone">
      {children} <ArrowUpRight className="h-3 w-3" />
    </a>
  )
}
