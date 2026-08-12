import type { Health, Job } from './types'

function errorMessage(status: number, body: string): string {
  try {
    const payload = JSON.parse(body) as { detail?: string }
    if (payload.detail) return payload.detail
  } catch {
    // Keep the status-based message when the server did not return JSON.
  }
  return `Request failed (${status})`
}

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    throw new Error(errorMessage(response.status, await response.text()))
  }
  return (await response.json()) as T
}

export const getHealth = (signal?: AbortSignal) => request<Health>('/api/health', { signal })

export function createJob(
  file: File,
  profile: string,
  removeNoise: boolean,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const body = new FormData()
    body.append('file', file)
    body.append('profile', profile)
    body.append('remove_noise', String(removeNoise))

    const upload = new XMLHttpRequest()
    upload.open('POST', '/api/v1/jobs')
    upload.responseType = 'text'
    upload.timeout = 15 * 60 * 1000

    const abort = () => upload.abort()
    signal?.addEventListener('abort', abort, { once: true })
    const finish = () => signal?.removeEventListener('abort', abort)

    upload.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.min(99, Math.round((event.loaded / event.total) * 100)))
      }
    }
    upload.onload = () => {
      finish()
      if (upload.status < 200 || upload.status >= 300) {
        reject(new Error(errorMessage(upload.status, upload.responseText)))
        return
      }
      try {
        resolve(JSON.parse(upload.responseText) as Job)
      } catch {
        reject(new Error('The server returned an invalid response'))
      }
    }
    upload.onerror = () => {
      finish()
      reject(new Error('Could not reach the CineVoice engine'))
    }
    upload.ontimeout = () => {
      finish()
      reject(new Error('The upload timed out. Check your connection and try again.'))
    }
    upload.onabort = () => {
      finish()
      reject(new DOMException('Upload cancelled', 'AbortError'))
    }
    upload.send(body)
  })
}

export const getJob = (id: string, signal?: AbortSignal) =>
  request<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`, { signal })

export async function deleteJob(id: string): Promise<void> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 404) throw new Error('Could not delete the job')
}
