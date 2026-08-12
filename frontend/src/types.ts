export type Profile = {
  id: string
  name: string
  description: string
}

export type Health = {
  status: 'ok'
  version: string
  ai_denoise_available: boolean
  ai_denoise_required: boolean
  ffmpeg_available: boolean
  accepted_extensions: string[]
  profiles: Profile[]
  limits: {
    max_upload_mb: number
    max_duration_seconds: number
    retention_hours: number
  }
  privacy: {
    server_side_processing: boolean
    automatic_deletion: boolean
    retention_hours: number
  }
}

export type Metrics = {
  sample_rate_hz: number
  channels: number
  duration_seconds: number
  integrated_lufs: number | null
  short_term_max_lufs: number | null
  loudness_range_lu: number | null
  sample_peak_dbfs: number
  true_peak_dbtp: number
  rms_dbfs: number
  crest_factor_db: number
  noise_floor_proxy_dbfs: number | null
  dc_offset: number[]
}

export type Job = {
  id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  progress: number
  stage: string
  profile: string
  remove_noise: boolean
  original_filename: string
  created_at: string
  updated_at: string
  expires_at: string
  source_bytes: number | null
  error: string | null
  warnings: string[]
  metrics: { before: Metrics; after: Metrics } | null
  links: {
    self: string
    source: string
    result: string
    report: string
  }
}
