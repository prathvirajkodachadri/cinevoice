# Production plan

## Current deployment

Version 0.1 intentionally uses one application container and a filesystem job store. This keeps local
validation simple and ensures the entire workflow can be audited before scaling it.

## Public architecture

```text
Browser
  → CDN / WAF / TLS / rate limit
  → API service
  → direct encrypted object-storage upload
  → Redis or managed queue
  → isolated CPU/GPU audio worker
  → lifecycle-managed result storage
  → short-lived download URL
```

## Mandatory gates before public launch

1. Pin application, model and operating-system dependencies.
2. Record model-weight hashes and license decisions.
3. Sandbox FFmpeg and model workers with no public network access.
4. Enforce size, duration, codec, concurrency and daily-user quotas before queueing.
5. Strip unsafe metadata and never use user filenames as storage paths.
6. Delete source and result objects automatically and support immediate deletion.
7. Redact audio, filenames and signed URLs from logs and error monitoring.
8. Add bot protection, abuse reporting and denial-of-wallet controls.
9. Validate metering against trusted references and conduct level-matched multilingual listening tests.
10. Publish privacy, retention and model disclosures reviewed for target regions.

## Scale-out interface

The `Processor.run(job_id, upload_path)` boundary should move to a queue worker without changing the
public API. Job metadata should migrate from atomic JSON to PostgreSQL; audio should migrate from the
shared volume to S3-compatible object storage. API nodes must never execute untrusted media directly in
the public deployment.

## Reliability targets for 1.0

- No source overwrite under any failure mode.
- Deterministic DSP output for identical versions and model hashes.
- True peak at or below the selected ceiling within 0.1 dB.
- Automatic retry only for idempotent infrastructure failures.
- Cancellation and expiry remove all source, prepared, result and report objects.
- Health checks cover API, queue, storage and worker model readiness.
