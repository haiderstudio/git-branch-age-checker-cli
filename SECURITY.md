# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key, token, or secret. It only reads the git repo you point it at, and it never deletes a branch, never rewrites a file, and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error).

If you find a case where the tool changes anything, or reports a pass for a branch that is older than your limit, please open an issue describing the exact commands and input. Do not include any real secret in the report.
