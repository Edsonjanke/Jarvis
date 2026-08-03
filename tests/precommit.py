"""Before committing: no value from .env may appear in any file being committed.

Also reports which .env settings the code actually reads, so a key named
slightly wrong is caught rather than silently ignored.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Values that look like credentials. Model names and hostnames are config, and
# are supposed to appear in .env.example.
NOT_SECRET = re.compile(r"^(eleven_|scribe_|claude-|sonnet|opus|haiku|127\.|localhost|[01]$)"
                        r"|^[A-Za-z]:[\\/]", re.IGNORECASE)

env_lines = (ROOT / ".env").read_text(encoding="utf-8-sig", errors="replace").splitlines()
declared, secrets = [], {}
for line in env_lines:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, val = line.partition("=")
    key, val = key.strip(), val.strip().strip("\"'")
    declared.append(key)
    if len(val) >= 16 and not NOT_SECRET.search(val):
        secrets[key] = val

print(f"credential-shaped values in .env: {', '.join(secrets) or 'none'}")

# --- which settings does the code actually read? --------------------------
read = set()
for path in ROOT.rglob("*.py"):
    if ".git" in path.parts:
        continue
    read.update(re.findall(r'setting\(\s*["\']([A-Z_0-9]+)["\']', path.read_text(encoding="utf-8", errors="replace")))

print(f"\nsettings the code reads : {', '.join(sorted(read))}")
ignored = [k for k in declared if k not in read]
print(f"declared in .env but ignored: {', '.join(ignored) or 'none'}")
missing = [k for k in sorted(read) if k not in declared]
print(f"read by code, absent from .env (falls back to default): {', '.join(missing) or 'none'}")

# --- the actual gate -------------------------------------------------------
staged = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                        capture_output=True, text=True).stdout.splitlines()
files = [s[3:].strip().strip('"') for s in staged if s and not s.startswith("!!")]
print(f"\nfiles in the change set: {len(files)}")

leaks = [(rel, name)
         for rel in files
         if (ROOT / rel).is_file()
         for name, value in secrets.items()
         if value in (ROOT / rel).read_text(encoding="utf-8", errors="replace")]

if leaks:
    for rel, name in leaks:
        print(f"  LEAK  {name} appears in {rel}")
    sys.exit(1)
print("  clean: no credential from .env appears in any file being committed")

if ".env" in files:
    print("  .env is in the change set — stopping")
    sys.exit(1)
print("  .env is not in the change set (left exactly as it was)")
