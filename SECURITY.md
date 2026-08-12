# Security policy

Use GitHub private vulnerability reporting for path traversal, arbitrary-code execution, unsafe model
loading, upload bypass, cross-user data access or deletion failures.

The local pilot validates file extensions, generates UUID job paths, sanitizes display filenames,
streams uploads with a hard byte limit, writes metadata atomically, never overwrites uploads and expires
jobs. A public deployment must isolate decoding and inference workers, verify file signatures, scan
uploads, use object storage, enforce rate limits and use expiring download authorization.

Never upload recordings without the speaker's consent. Never log audio content or original filenames in
hosted telemetry.
