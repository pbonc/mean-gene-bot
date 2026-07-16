# Storage audit

Run the non-destructive audit from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\storage_audit.py
```

For automation or comparison between runs:

```powershell
.\.venv\Scripts\python.exe tools\storage_audit.py --json
```

The command reads file metadata and hashes only suspected duplicate static assets. It never deletes, moves, rotates, or rewrites files.

Music-cache classifications are deliberately conservative. An exact catalog filename is proven to correspond to the current catalog. Title/format mismatches, `yt_` requests, and unclassified files are review categories—not deletion authorization—because they may represent legacy cache formats or active requests.

Backup retention numbers are previews. The defaults identify files older than 30 days while retaining at least the newest 20 files. Restore requirements must be agreed before implementing deletion.
