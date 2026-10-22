# Known vulnerable fingerprints

SHA-256 of the two files that carry the bug, from the latest 4.0 and 4.5 firmware:

| File | webOS 4.0 (B8 m16pp / C8 o18, 05.50.70) | webOS 4.5 (B9 m16p3 / C9 o18, 05.50.00) |
| :--- | :--- | :--- |
| `rdx-manager.js` | `a5fe4857c7ff5c4da9e5e8e009f4706e59553c58f4b4526a35ef6dbbb691d4e4` | same |
| `bugreport-service.js` | `b9a2233d0fbe2f9f4f75038562b469f3b53e05eeebdbc09cdf7665ffe58a7654` | `c649cecd27c9c75180c5db83d1b28a0e63927aad147369fb3bc8134625ee4ea6` |

The hashes are identical across SoCs within a branch: B8 (`m16pp`) and C8 (`o18`) share the
4.0 files; B9 (`m16p3`) and C9 (`o18`) share the 4.5 files. The service is model-independent.

`rdx-manager.js` is byte-identical on 4.0 and 4.5: the `exec` sink is shared. The service
entry file differs, but both still read `params.filepath` and call
`createCrashReport(params.filename, params.filepath, null)`.

## Checking a new build

```sh
python3 tools/check_bugreport.py /path/to/extracted/rootfs
```

- If `rdx-manager.js` has the same hash, the sink is unchanged.
- If it differs, check the `createLogFiles` line and the `exec` call manually.
- If `bugreport-service.js` differs, check that `params.filepath` is still read and passed to
  `createCrashReport`.
- If the service directory is absent, the TV is not affected.

Future 4.0/4.5 builds can be detected by monitoring the LG support pages for the model and
re-running this check on the new EPK.
