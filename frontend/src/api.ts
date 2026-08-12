import type { Health, Job } from './types'

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) message = payload.detail
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

export const getHealth = () => request<Health>('/api/health')

export async function createJob(file: File, profile: string, removeNoise: boolean): Promise<Job> {
  const body = new FormData()
  body.append('file', file)
  body.append('profile', profile)
  body.append('remove_noise', String(removeNoise))
  return request<Job>('/api/v1/jobs', { method: 'POST', body })
}

export const getJob = (id: string) => request<Job>(`/api/v1/jobs/${id}`)

export async function deleteJob(id: string): Promise<void> {
  const response = await fetch(`/api/v1/jobs/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 404) throw new Error('Could not delete the job')
}
