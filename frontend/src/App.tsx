import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createJob, deleteJob, getHealth, getJob } from './api'
import type { Health, Job, Profile } from './types'

const LAST_JOB_KEY = 'cinevoice:last-job'
const fallbackProfiles: Profile[] = [
  { id: 'natural', name: 'Natural', description: 'Light cleanup, original tone preserved' },
  { id: 'studio', name: 'Studio', description: 'Balanced clarity and polished dynamics' },
  { id: 'deep-narration', name: 'Deep Narration', description: 'Cinematic weight with clear presence' },
]
const profileDetails: Record<string, { tone: string; target: string }> = {
  natural: { tone: 'Transparent', target: '−16 LUFS' },
  studio: { tone: 'Balanced', target: '−14 LUFS' },
  'deep-narration': { tone: 'Warm & present', target: '−14 LUFS' },
}

type IconName =
  | 'upload' | 'spark' | 'shield' | 'download' | 'wave' | 'reset'
  | 'clock' | 'check' | 'arrow' | 'file' | 'compare' | 'info'

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></>,
    spark: <><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></>,
    shield: <><path d="M12 3 5 6v5c0 4.4 2.8 7.7 7 9 4.2-1.3 7-4.6 7-9V6l-7-3Z"/><path d="m9.5 12 1.7 1.7 3.6-4"/></>,
    download: <><path d="M12 4v11"/><path d="m8 11 4 4 4-4"/><path d="M5 20h14"/></>,
    wave: <><path d="M3 12h2l2-7 3 14 3-12 3 9 2-4h3"/></>,
    reset: <><path d="M4 7v5h5"/><path d="M5.5 16A8 8 0 1 0 6 7l-2 5"/></>,
    clock: <><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.7 1.7"/></>,
    check: <><circle cx="12" cy="12" r="9"/><path d="m8 12 2.6 2.6L16.5 9"/></>,
    arrow: <><path d="M5 12h14"/><path d="m14 7 5 5-5 5"/></>,
    file: <><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5"/><path d="M10 13h5M10 17h5"/></>,
    compare: <><path d="M8 5 4 9l4 4"/><path d="M4 9h12"/><path d="m16 11 4 4-4 4"/><path d="M20 15H8"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  }
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  )
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds))
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const remainder = rounded % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}

function metric(value: number | null | undefined, suffix: string) {
  return value == null ? '—' : `${value.toFixed(1)} ${suffix}`
}

function expiryLabel(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'within the retention window'
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function inspectDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const audio = new Audio()
    let finished = false
    const finish = (value: number | null) => {
      if (finished) return
      finished = true
      window.clearTimeout(timer)
      audio.removeAttribute('src')
      URL.revokeObjectURL(url)
      resolve(value)
    }
    const timer = window.setTimeout(() => finish(null), 5000)
    audio.preload = 'metadata'
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) ? audio.duration : null)
    audio.onerror = () => finish(null)
    audio.src = url
  })
}

export default function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const originalPlayerRef = useRef<HTMLAudioElement>(null)
  const enhancedPlayerRef = useRef<HTMLAudioElement>(null)
  const uploadControllerRef = useRef<AbortController | null>(null)
  const healthConfiguredRef = useRef(false)
  const fileSelectionRef = useRef(0)

  const [health, setHealth] = useState<Health | null>(null)
  const [healthState, setHealthState] = useState<'checking' | 'ready' | 'offline'>('checking')
  const [file, setFile] = useState<File | null>(null)
  const [fileDuration, setFileDuration] = useState<number | null>(null)
  const [profile, setProfile] = useState('studio')
  const [removeNoise, setRemoveNoise] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [restoredJob, setRestoredJob] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

  const profiles = health?.profiles ?? fallbackProfiles
  const originalUrl = useMemo(() => file ? URL.createObjectURL(file) : null, [file])
  const active = job?.status === 'queued' || job?.status === 'processing'
  const busy = submitting || active
  const complete = job?.status === 'completed'
  const failed = job?.status === 'failed'
  const sourceUrl = originalUrl ?? (job ? `${job.links.source}?play=1` : undefined)
  const sourceName = file?.name ?? job?.original_filename
  const sourceBytes = file?.size ?? job?.source_bytes
  const sourceDuration = fileDuration ?? job?.metrics?.before.duration_seconds ?? null

  useEffect(() => () => { if (originalUrl) URL.revokeObjectURL(originalUrl) }, [originalUrl])

  const checkHealth = useCallback(async () => {
    setHealthState('checking')
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 8000)
    try {
      const value = await getHealth(controller.signal)
      setHealth(value)
      setHealthState('ready')
      if (!healthConfiguredRef.current) {
        setRemoveNoise(value.ai_denoise_available)
        healthConfiguredRef.current = true
      } else if (!value.ai_denoise_available) {
        setRemoveNoise(false)
      }
      if (value.ai_denoise_required) setRemoveNoise(true)
    } catch {
      setHealthState('offline')
    } finally {
      window.clearTimeout(timeout)
    }
  }, [])

  useEffect(() => { void checkHealth() }, [checkHealth])

  useEffect(() => {
    const savedId = window.localStorage.getItem(LAST_JOB_KEY)
    if (!savedId) return
    const controller = new AbortController()
    getJob(savedId, controller.signal)
      .then((savedJob) => {
        healthConfiguredRef.current = true
        setJob(savedJob)
        setProfile(savedJob.profile)
        setRemoveNoise(savedJob.remove_noise)
        setRestoredJob(true)
      })
      .catch(() => window.localStorage.removeItem(LAST_JOB_KEY))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!job || !['queued', 'processing'].includes(job.status)) return
    let stopped = false
    let timer = 0
    let failures = 0
    const poll = async () => {
      try {
        const next = await getJob(job.id)
        if (stopped) return
        failures = 0
        setPollError(null)
        setJob(next)
      } catch {
        if (stopped) return
        failures += 1
        setPollError('Connection interrupted. Retrying automatically…')
      }
      if (!stopped) timer = window.setTimeout(poll, Math.min(5000, 1100 + failures * 700))
    }
    timer = window.setTimeout(poll, 900)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [job?.id, job?.status])

  useEffect(() => {
    if (complete) {
      window.setTimeout(() => document.querySelector('.result-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
    }
  }, [complete])

  async function chooseFile(candidate: File | null) {
    if (!candidate) return
    const selection = ++fileSelectionRef.current
    setError(null)
    setPollError(null)
    const dot = candidate.name.lastIndexOf('.')
    const extension = dot >= 0 ? candidate.name.slice(dot).toLowerCase() : ''
    const accepted = health?.accepted_extensions ?? ['.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac']
    if (!accepted.includes(extension)) {
      setError(`That format is not available. Choose ${accepted.map((item) => item.slice(1).toUpperCase()).join(', ')}.`)
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    if (candidate.size === 0) {
      setError('That file is empty. Choose a recording that contains audio.')
      return
    }
    const maxMb = health?.limits.max_upload_mb ?? 250
    if (candidate.size > maxMb * 1024 * 1024) {
      setError(`The file is larger than the ${maxMb} MB limit.`)
      return
    }

    if (job) void deleteJob(job.id).catch(() => undefined)
    window.localStorage.removeItem(LAST_JOB_KEY)
    setJob(null)
    setRestoredJob(false)
    setFile(candidate)
    setFileDuration(null)

    const duration = await inspectDuration(candidate)
    if (selection !== fileSelectionRef.current) return
    const maxDuration = health?.limits.max_duration_seconds ?? 3600
    if (duration !== null && duration > maxDuration) {
      setFile(null)
      setError(`The recording is ${formatDuration(duration)}; the limit is ${formatDuration(maxDuration)}.`)
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    setFileDuration(duration)
  }

  async function enhance() {
    if (!file) {
      inputRef.current?.click()
      return
    }
    if (healthState !== 'ready') {
      setError('The processing engine is not connected yet. Retry the connection first.')
      return
    }

    if (job) await deleteJob(job.id).catch(() => undefined)
    setJob(null)
    window.localStorage.removeItem(LAST_JOB_KEY)
    const controller = new AbortController()
    uploadControllerRef.current = controller
    setSubmitting(true)
    setUploadProgress(0)
    setError(null)
    setPollError(null)
    try {
      const created = await createJob(
        file,
        profile,
        removeNoise,
        setUploadProgress,
        controller.signal,
      )
      setJob(created)
      setRestoredJob(false)
      window.localStorage.setItem(LAST_JOB_KEY, created.id)
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) {
        setError(reason instanceof Error ? reason.message : 'Could not start enhancement')
      }
    } finally {
      uploadControllerRef.current = null
      setSubmitting(false)
    }
  }

  function reset() {
    fileSelectionRef.current += 1
    uploadControllerRef.current?.abort()
    if (job) void deleteJob(job.id).catch(() => undefined)
    window.localStorage.removeItem(LAST_JOB_KEY)
    originalPlayerRef.current?.pause()
    enhancedPlayerRef.current?.pause()
    setFile(null)
    setFileDuration(null)
    setJob(null)
    setRestoredJob(false)
    setError(null)
    setPollError(null)
    setUploadProgress(0)
    if (inputRef.current) inputRef.current.value = ''
  }

  const noiseDelta = job?.metrics?.before.noise_floor_proxy_dbfs != null && job.metrics.after.noise_floor_proxy_dbfs != null
    ? job.metrics.before.noise_floor_proxy_dbfs - job.metrics.after.noise_floor_proxy_dbfs
    : null
  const acceptedLabel = (health?.accepted_extensions ?? ['.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac'])
    .map((item) => item.slice(1).toUpperCase()).join(' · ')
  const healthText = healthState === 'offline'
    ? 'Engine unavailable'
    : healthState === 'ready' ? 'Engine ready' : 'Checking engine'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CineVoice home">
          <span className="brand-mark"><Icon name="wave" size={21}/></span>
          <span>CineVoice</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#studio">Studio</a>
          <a href="#process">How it works</a>
        </nav>
        <button className={`top-status ${healthState}`} onClick={checkHealth} disabled={healthState !== 'offline'} type="button">
          <span className="status-dot" aria-hidden="true"/>
          {healthText}
        </button>
      </header>

      <main id="top">
        <section className="hero">
          <div className="eyebrow"><Icon name="spark" size={16}/> PRIVATE VOICE MASTERING</div>
          <h1>From raw recording to <span>remarkably clear voice.</span></h1>
          <p className="hero-copy">Clean distractions, balance tone and master loudness in one controlled signal path—while keeping your voice unmistakably yours.</p>
          <a className="hero-cta" href="#studio">Open the studio <Icon name="arrow" size={17}/></a>
          <div className="signal-line" aria-hidden="true">
            {[8, 18, 31, 14, 43, 25, 55, 22, 38, 65, 29, 48, 18, 37, 11, 25, 8].map((height, index) => <i key={index} style={{ height }}/>) }
          </div>
          <div className="trust-row">
            <span><Icon name="shield" size={17}/> Private server-side processing</span>
            <span><Icon name="clock" size={17}/> Auto-deleted after {health?.limits.retention_hours ?? 24} hours</span>
            <span><Icon name="check" size={17}/> No pitch shift or voice cloning</span>
          </div>
        </section>

        <section className="workspace" id="studio" aria-label="Voice enhancement workspace" aria-busy={busy}>
          <div className="workspace-intro">
            <div>
              <span className="section-kicker">YOUR PRIVATE STUDIO</span>
              <h2>Enhance a recording</h2>
              <p>One upload. A transparent, publish-ready WAV.</p>
            </div>
            {(file || job) && <button className="text-button" onClick={reset} type="button"><Icon name="reset" size={17}/> {busy ? 'Cancel & clear' : 'Start over'}</button>}
          </div>

          {healthState === 'offline' && (
            <div className="connection-banner" role="alert">
              <Icon name="info" size={20}/>
              <div><strong>Processing engine unavailable</strong><span>Your file stays on this device until the connection returns.</span></div>
              <button type="button" onClick={checkHealth}>Retry</button>
            </div>
          )}

          <div className="step-block">
            <div className="step-heading"><span>01</span><div><h3>Source recording</h3><p>Select one audio file from your device.</p></div></div>
            <input ref={inputRef} type="file" hidden accept={(health?.accepted_extensions ?? ['.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac']).join(',')} onChange={(event) => void chooseFile(event.target.files?.[0] ?? null)}/>

            {!sourceName ? (
              <button
                className={`dropzone ${dragging ? 'dragging' : ''}`}
                type="button"
                onClick={() => inputRef.current?.click()}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
                onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }}
                onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false) }}
                onDrop={(event) => { event.preventDefault(); setDragging(false); void chooseFile(event.dataTransfer.files[0] ?? null) }}
              >
                <span className="upload-icon"><Icon name="upload" size={27}/></span>
                <strong>{dragging ? 'Release to add recording' : 'Drop your recording here'}</strong>
                <span>or choose a file from your device</span>
                <small>{acceptedLabel} · up to {health?.limits.max_upload_mb ?? 250} MB</small>
              </button>
            ) : (
              <div className="selected-file">
                <div className="file-icon"><Icon name="file" size={24}/></div>
                <div className="file-meta">
                  <strong title={sourceName}>{sourceName}</strong>
                  <span>
                    {sourceBytes != null ? formatBytes(sourceBytes) : 'Audio recording'}
                    {sourceDuration != null ? ` · ${formatDuration(sourceDuration)}` : ''}
                    {restoredJob ? ' · restored session' : ' · ready'}
                  </span>
                </div>
                {complete
                  ? <span className="source-complete"><Icon name="check" size={15}/> Processed</span>
                  : <audio aria-label={`Preview ${sourceName}`} controls preload="metadata" src={sourceUrl}/>
                }
                {!busy && !complete && <button className="replace-button" type="button" onClick={() => inputRef.current?.click()}>Replace</button>}
              </div>
            )}
          </div>

          <div className="step-divider"/>

          <div className="step-block">
            <div className="step-heading"><span>02</span><div><h3>Enhancement character</h3><p>Choose how the finished voice should feel.</p></div></div>
            <div className="profile-grid" role="radiogroup" aria-label="Enhancement style">
              {profiles.map((item) => {
                const detail = profileDetails[item.id] ?? { tone: 'Voice profile', target: 'Mastered' }
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="radio"
                    aria-checked={profile === item.id}
                    className={`profile-card ${profile === item.id ? 'selected' : ''}`}
                    onClick={() => setProfile(item.id)}
                    disabled={busy || complete}
                  >
                    <span className="profile-top"><i className="radio"/><small>{detail.target}</small></span>
                    <strong>{item.name}</strong>
                    <span>{item.description}</span>
                    <em>{detail.tone}</em>
                  </button>
                )
              })}
            </div>

            <label className={`toggle-row ${health && !health.ai_denoise_available ? 'disabled' : ''}`}>
              <span className="ai-icon"><Icon name="spark" size={19}/></span>
              <div>
                <span className="toggle-title"><strong>AI background-noise removal</strong>{health?.ai_denoise_available && <b>AVAILABLE</b>}</span>
                <span>{healthState === 'checking' ? 'Checking model availability…' : health?.ai_denoise_available ? 'Speech-aware cleanup before tonal mastering' : 'Model is not installed; deterministic mastering remains available'}</span>
              </div>
              <input
                type="checkbox"
                aria-label="AI background-noise removal"
                checked={removeNoise}
                disabled={busy || complete || (health !== null && (!health.ai_denoise_available || health.ai_denoise_required))}
                onChange={(event) => setRemoveNoise(event.target.checked)}
              />
              <span className="switch" aria-hidden="true"/>
            </label>
          </div>

          {error && <div className="error-banner" role="alert"><Icon name="info" size={18}/><span>{error}</span></div>}
          {failed && job && (
            <div className="failed-panel" role="alert">
              <div><strong>Enhancement could not finish</strong><span>{job.error ?? 'Please check the recording and try again.'}</span></div>
              <button type="button" onClick={file ? enhance : () => inputRef.current?.click()}>{file ? 'Try again' : 'Choose file again'}</button>
            </div>
          )}

          {busy && (
            <div className="progress-panel" aria-live="polite">
              <div className="progress-copy">
                <span className="spinner"/>
                <div><strong>{submitting ? 'Uploading securely' : job?.stage ?? 'Preparing job'}</strong><small>{pollError ?? (submitting ? 'Sending your recording to the private engine' : 'Running the controlled enhancement chain')}</small></div>
                <span>{submitting ? `${uploadProgress}%` : `${job?.progress ?? 5}%`}</span>
              </div>
              <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={submitting ? uploadProgress : job?.progress ?? 5}>
                <span style={{ width: `${submitting ? uploadProgress : job?.progress ?? 5}%` }}/>
              </div>
              <div className="stage-list"><span className="done">Upload</span><span className={job && job.progress >= 30 ? 'done' : ''}>Clean</span><span className={job && job.progress >= 58 ? 'done' : ''}>Balance</span><span className={job && job.progress >= 87 ? 'done' : ''}>Master</span></div>
            </div>
          )}

          {!complete && !failed && (
            <button className="enhance-button" type="button" onClick={enhance} disabled={busy || healthState !== 'ready'}>
              <Icon name="spark" size={20}/>
              {busy ? 'Enhancing voice…' : file ? 'Enhance my voice' : 'Choose audio to begin'}
              {!busy && file && <Icon name="arrow" size={18}/>}
            </button>
          )}
          {!busy && !complete && !failed && <p className="action-note"><Icon name="shield" size={14}/> Your source is never overwritten. Processing happens privately on this server.</p>}
        </section>

        {complete && job && (
          <section className="result-card" aria-labelledby="result-title">
            <div className="result-orbit" aria-hidden="true"><Icon name="check" size={32}/></div>
            <div className="result-badge"><Icon name="spark" size={13}/> ENHANCEMENT COMPLETE</div>
            <div className="result-head">
              <div><h2 id="result-title">Your mastered voice is ready.</h2><p>Listen side by side, then keep the 24-bit WAV.</p></div>
              <a className="download-button" href={job.links.result} download><Icon name="download"/> Download WAV</a>
            </div>

            <div className="compare-note"><Icon name="compare" size={17}/><span>Starting one player automatically pauses the other for a cleaner A/B comparison.</span></div>
            <div className="players">
              <div className="player">
                <div className="player-label"><span>ORIGINAL</span><small>Source</small></div>
                <strong>{sourceName}</strong>
                <audio ref={originalPlayerRef} aria-label="Play original recording" controls preload="metadata" src={sourceUrl} onPlay={() => enhancedPlayerRef.current?.pause()}/>
              </div>
              <div className="player enhanced">
                <div className="player-label"><span>ENHANCED</span><small>24-bit WAV</small></div>
                <strong>CineVoice · {profiles.find((item) => item.id === job.profile)?.name ?? job.profile}</strong>
                <audio ref={enhancedPlayerRef} aria-label="Play enhanced recording" controls preload="metadata" src={`${job.links.result}?play=1`} onPlay={() => originalPlayerRef.current?.pause()}/>
              </div>
            </div>

            {job.metrics && (
              <div className="metrics">
                <div><span>Delivery loudness</span><strong>{metric(job.metrics.after.integrated_lufs, 'LUFS')}</strong><small>from {metric(job.metrics.before.integrated_lufs, 'LUFS')}</small></div>
                <div><span>True peak</span><strong>{metric(job.metrics.after.true_peak_dbtp, 'dBTP')}</strong><small>protected master</small></div>
                <div><span>Noise floor</span><strong>{noiseDelta != null && noiseDelta > 0.05 ? `${noiseDelta.toFixed(1)} dB` : metric(job.metrics.after.noise_floor_proxy_dbfs, 'dBFS')}</strong><small>{noiseDelta != null && noiseDelta > 0.05 ? 'quieter' : 'measured after'}</small></div>
                <div><span>Dynamic shape</span><strong>{metric(job.metrics.after.crest_factor_db, 'dB')}</strong><small>crest factor</small></div>
              </div>
            )}

            {job.warnings.length > 0 && <details className="warnings"><summary>Engineering notes ({job.warnings.length})</summary>{job.warnings.map((warning, index) => <p key={`${index}-${warning}`}>{warning}</p>)}</details>}
            <div className="result-actions">
              <div><Icon name="clock" size={16}/><span>Files expire {expiryLabel(job.expires_at)}</span></div>
              <a href={job.links.report} download>Technical report</a>
              <button className="text-button" type="button" onClick={reset}><Icon name="reset" size={17}/> Enhance another</button>
            </div>
          </section>
        )}

        <section className="process-explainer" id="process">
          <div className="section-kicker">A CONTROLLED SIGNAL PATH</div>
          <h2>Restoration where it helps.<br/><span>Restraint everywhere else.</span></h2>
          <p className="process-lead">CineVoice combines optional speech-aware cleanup with deterministic mastering you can inspect.</p>
          <div className="process-grid">
            <article><span>01</span><div className="process-icon"><Icon name="wave" size={22}/></div><h3>Clean distractions</h3><p>Optional AI noise reduction focuses on speech while high-pass filtering controls room rumble.</p></article>
            <article><span>02</span><div className="process-icon"><Icon name="spark" size={22}/></div><h3>Shape with care</h3><p>Conservative EQ, de-essing and dynamics add clarity without fabricating a new identity.</p></article>
            <article><span>03</span><div className="process-icon"><Icon name="check" size={22}/></div><h3>Master reliably</h3><p>Loudness matching and true-peak protection create a consistent, publishing-ready WAV.</p></article>
          </div>
        </section>
      </main>

      <footer>
        <div className="brand"><span className="brand-mark"><Icon name="wave" size={18}/></span><span>CineVoice</span></div>
        <p>Private voice enhancement · Restoration, not imitation</p>
        <span>Engine {health?.version ?? 'connecting…'}</span>
      </footer>
    </div>
  )
}
