import { useEffect, useMemo, useRef, useState } from 'react'
import { createJob, deleteJob, getHealth, getJob } from './api'
import type { Health, Job, Profile } from './types'

const fallbackProfiles: Profile[] = [
  { id: 'natural', name: 'Natural', description: 'Light cleanup, original tone preserved' },
  { id: 'studio', name: 'Studio', description: 'Balanced clarity and polished dynamics' },
  { id: 'deep-narration', name: 'Deep Narration', description: 'Cinematic weight with clear presence' },
]

function Icon({ name, size = 20 }: { name: 'upload' | 'spark' | 'shield' | 'download' | 'wave' | 'reset'; size?: number }) {
  const paths = {
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></>,
    spark: <><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></>,
    shield: <><path d="M12 3 5 6v5c0 4.4 2.8 7.7 7 9 4.2-1.3 7-4.6 7-9V6l-7-3Z"/><path d="m9.5 12 1.7 1.7 3.6-4"/></>,
    download: <><path d="M12 4v11"/><path d="m8 11 4 4 4-4"/><path d="M5 20h14"/></>,
    wave: <><path d="M4 12h2l2-6 3 12 3-10 2 7 2-3h2"/></>,
    reset: <><path d="M4 7v5h5"/><path d="M5.5 16A8 8 0 1 0 6 7l-2 5"/></>,
  }
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function metric(value: number | null | undefined, suffix: string) {
  return value == null ? '—' : `${value.toFixed(1)} ${suffix}`
}

export default function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [profile, setProfile] = useState('studio')
  const [removeNoise, setRemoveNoise] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const profiles = health?.profiles ?? fallbackProfiles
  const originalUrl = useMemo(() => file ? URL.createObjectURL(file) : null, [file])

  useEffect(() => () => { if (originalUrl) URL.revokeObjectURL(originalUrl) }, [originalUrl])

  useEffect(() => {
    getHealth()
      .then((value) => {
        setHealth(value)
        setRemoveNoise(value.ai_denoise_available)
      })
      .catch(() => setHealthError(true))
  }, [])

  useEffect(() => {
    if (!job || !['queued', 'processing'].includes(job.status)) return
    const timer = window.setTimeout(() => {
      getJob(job.id).then(setJob).catch((reason: Error) => setError(reason.message))
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [job])

  function chooseFile(candidate: File | null) {
    if (!candidate) return
    setError(null)
    const extension = `.${candidate.name.split('.').pop()?.toLowerCase()}`
    const accepted = health?.accepted_extensions ?? ['.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac']
    if (!accepted.includes(extension)) {
      setError('Please choose a WAV, FLAC, OGG, MP3, M4A or AAC audio file.')
      return
    }
    const maxMb = health?.limits.max_upload_mb ?? 250
    if (candidate.size > maxMb * 1024 * 1024) {
      setError(`The file is larger than the ${maxMb} MB limit.`)
      return
    }
    setFile(candidate)
    setJob(null)
  }

  async function enhance() {
    if (!file) {
      inputRef.current?.click()
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      setJob(await createJob(file, profile, removeNoise))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not start enhancement')
    } finally {
      setSubmitting(false)
    }
  }

  async function reset() {
    if (job) await deleteJob(job.id).catch(() => undefined)
    setFile(null)
    setJob(null)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const busy = submitting || job?.status === 'queued' || job?.status === 'processing'
  const complete = job?.status === 'completed'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CineVoice home">
          <span className="brand-mark"><Icon name="wave" size={22}/></span>
          <span>CineVoice</span>
        </a>
        <div className="top-status">
          <span className={`status-dot ${healthError ? 'offline' : health ? 'online' : ''}`}/>
          {healthError ? 'Server unavailable' : health ? 'Local engine ready' : 'Checking engine'}
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="eyebrow"><Icon name="spark" size={16}/> PRIVATE AI AUDIO</div>
          <h1>Turn everyday recordings into <span>studio-ready voice.</span></h1>
          <p className="hero-copy">Upload a voice recording. CineVoice removes noise, controls rumble, restores clarity and delivers a polished file—without changing who you sound like.</p>
          <div className="trust-row">
            <span><Icon name="shield" size={17}/> Private processing</span>
            <span>Files deleted in {health?.limits.retention_hours ?? 24} hours</span>
            <span>No voice cloning</span>
          </div>
        </section>

        <section className="workspace" aria-label="Voice enhancement workspace">
          <div className="workspace-head">
            <div>
              <span className="step-label">01 · SOURCE</span>
              <h2>Choose your recording</h2>
            </div>
            {file && <button className="text-button" onClick={reset}><Icon name="reset" size={17}/> Start over</button>}
          </div>

          <input ref={inputRef} type="file" hidden accept="audio/*,.wav,.flac,.ogg,.mp3,.m4a,.aac" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}/>

          {!file ? (
            <button
              className={`dropzone ${dragging ? 'dragging' : ''}`}
              onClick={() => inputRef.current?.click()}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0] ?? null) }}
            >
              <span className="upload-icon"><Icon name="upload" size={28}/></span>
              <strong>Drop audio here</strong>
              <span>or click to browse your device</span>
              <small>WAV · MP3 · M4A · FLAC · OGG · up to {health?.limits.max_upload_mb ?? 250} MB</small>
            </button>
          ) : (
            <div className="selected-file">
              <div className="file-icon"><Icon name="wave" size={26}/></div>
              <div className="file-meta"><strong>{file.name}</strong><span>{formatBytes(file.size)} · ready to enhance</span></div>
              <audio controls src={originalUrl ?? undefined}/>
            </div>
          )}

          <div className="divider"/>

          <div className="workspace-head compact">
            <div>
              <span className="step-label">02 · SOUND</span>
              <h2>Select an enhancement style</h2>
            </div>
          </div>

          <div className="profile-grid">
            {profiles.map((item) => (
              <button key={item.id} className={`profile-card ${profile === item.id ? 'selected' : ''}`} onClick={() => setProfile(item.id)} disabled={busy}>
                <span className="radio"><i/></span>
                <strong>{item.name}</strong>
                <span>{item.description}</span>
              </button>
            ))}
          </div>

          <label className={`toggle-row ${health && !health.ai_denoise_available ? 'disabled' : ''}`}>
            <div>
              <strong>AI background-noise removal</strong>
              <span>{health?.ai_denoise_available ? 'DeepFilterNet speech cleanup before mastering' : 'AI model is not installed on this server'}</span>
            </div>
            <input type="checkbox" checked={removeNoise} disabled={busy || (health !== null && !health.ai_denoise_available)} onChange={(event) => setRemoveNoise(event.target.checked)}/>
            <span className="switch"/>
          </label>

          {error && <div className="error-banner" role="alert">{error}</div>}

          {busy && (
            <div className="progress-panel" aria-live="polite">
              <div className="progress-copy"><span className="spinner"/><strong>{submitting ? 'Uploading securely' : job?.stage}</strong><span>{job?.progress ?? 5}%</span></div>
              <div className="progress-track"><span style={{ width: `${job?.progress ?? 5}%` }}/></div>
              <small>Keep this page open while your recording is processed.</small>
            </div>
          )}

          {!complete && <button className="enhance-button" onClick={enhance} disabled={busy || healthError}><Icon name="spark" size={20}/>{busy ? 'Enhancing voice…' : file ? 'Enhance voice' : 'Choose audio to begin'}</button>}
        </section>

        {complete && job && (
          <section className="result-card">
            <div className="result-badge">ENHANCEMENT COMPLETE</div>
            <div className="result-head">
              <div><h2>Your studio voice is ready</h2><p>Compare both versions before downloading.</p></div>
              <a className="download-button" href={job.links.result} download><Icon name="download"/> Download WAV</a>
            </div>

            <div className="players">
              <div className="player"><span>ORIGINAL</span><strong>{file?.name}</strong><audio controls src={originalUrl ?? undefined}/></div>
              <div className="player enhanced"><span>ENHANCED</span><strong>CineVoice result</strong><audio controls src={`${job.links.result}?play=1`}/></div>
            </div>

            {job.metrics && (
              <div className="metrics">
                <div><span>Loudness</span><strong>{metric(job.metrics.after.integrated_lufs, 'LUFS')}</strong><small>was {metric(job.metrics.before.integrated_lufs, 'LUFS')}</small></div>
                <div><span>True peak</span><strong>{metric(job.metrics.after.true_peak_dbtp, 'dBTP')}</strong><small>safe delivery ceiling</small></div>
                <div><span>Dynamic control</span><strong>{metric(job.metrics.after.crest_factor_db, 'dB')}</strong><small>crest factor</small></div>
              </div>
            )}

            {job.warnings.length > 0 && <details className="warnings"><summary>Engineering notes ({job.warnings.length})</summary>{job.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
            <div className="result-actions"><a href={job.links.report} download>Download technical report</a><button className="text-button" onClick={reset}><Icon name="reset" size={17}/> Enhance another file</button></div>
          </section>
        )}

        <section className="process-explainer">
          <div className="section-kicker">A CONTROLLED SIGNAL PATH</div>
          <h2>AI restoration first. Professional audio processing after.</h2>
          <div className="process-grid">
            <article><span>01</span><h3>Clean</h3><p>Speech-aware noise reduction removes distractions while protecting vocal identity.</p></article>
            <article><span>02</span><h3>Balance</h3><p>Rumble, low-mid buildup, clarity and sibilance are handled conservatively.</p></article>
            <article><span>03</span><h3>Deliver</h3><p>Dynamics, loudness and true peak are prepared for consistent publishing.</p></article>
          </div>
        </section>
      </main>

      <footer><div className="brand"><span className="brand-mark"><Icon name="wave" size={18}/></span><span>CineVoice</span></div><p>Private voice enhancement · Original recordings are never overwritten</p></footer>
    </div>
  )
}
