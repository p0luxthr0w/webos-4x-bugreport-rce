#!/usr/bin/env python3
"""Check an extracted webOS rootfs for the bugreport/fileCrashReport chain.

Usage: check_bugreport.py <rootfs>
Exit 0 if the vulnerable code is present, 1 otherwise.
"""

import hashlib
import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
SERVICE = "com.palm.service.bugreport"
DIR = os.path.join(ROOT, "usr/palm/services", SERVICE)


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""


print("rootfs:", ROOT)
print("service directory:", "present" if os.path.isdir(DIR) else "ABSENT")
if not os.path.isdir(DIR):
    sys.exit(1)

rdx_path = os.path.join(DIR, "rdx-manager.js")
svc_path = os.path.join(DIR, "bugreport-service.js")
rdx = read(rdx_path)
svc = read(svc_path)

def sha256(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return "missing"

print("rdx-manager.js sha256:", sha256(rdx_path))
print("bugreport-service.js sha256:", sha256(svc_path))

exec_line = next((l.strip() for l in rdx.splitlines() if 'tar zxf " + file' in l), None)
print("createLogFiles exec:", exec_line or "NOT FOUND")
print("filepath read:", "yes" if "params.filepath" in svc else "no")
print("filename read:", "yes" if "params.filename" in svc else "no")
print("call site:", "yes" if "createCrashReport(params.filename, params.filepath" in svc else "no")

# permission declarations for fileCrashReport
groups = set()
api_dir = os.path.join(ROOT, "usr/share/luna-service2/api-permissions.d")
if os.path.isdir(api_dir):
    for name in os.listdir(api_dir):
        if not name.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(api_dir, name)))
        except Exception:
            continue
        for group, entries in data.items():
            if isinstance(entries, list) and SERVICE + "/fileCrashReport" in entries:
                groups.add(group)
print("fileCrashReport groups:", ",".join(sorted(groups)) or "none")

# service launch info
exec_path = user = None
svc_dir = os.path.join(ROOT, "usr/share/luna-service2/services.d")
for name in os.listdir(svc_dir) if os.path.isdir(svc_dir) else []:
    text = read(os.path.join(svc_dir, name))
    if "Name=" + SERVICE in text:
        m = re.search(r"^Exec=(.+)$", text, re.M)
        exec_path = m.group(1).strip() if m else None
        user = "User=" in text
print("service Exec:", exec_path or "unknown", "| User= field:", user)

ok = bool(exec_line and "params.filepath" in svc)
print("\nverdict:", "VULNERABLE CODE PRESENT" if ok else "chain not found")
sys.exit(0 if ok else 1)
