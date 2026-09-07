"""Desktop launcher: runs an isolated Flask backend and opens pywebview.

Each launch uses an available loopback port.  The old fixed-port launcher could
silently connect a new window to an older Worldwalker process, which made stale
JavaScript, artwork, and campaign state appear in a freshly extracted build.
"""
import json, os, socket, ssl, sys, threading, time
from urllib.request import urlopen
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from util import DATA_DIR

# Some machines (older/integrated GPUs, remote desktop sessions, certain
# hybrid-GPU laptops) can render the embedded WebView2 browser as a solid
# white window even though the Runtime itself is installed and healthy — a
# known WebView2/Chromium GPU-compositing bug, not a Worldwalker bug. This
# app used to force --disable-gpu up front as a preemptive fix, but blanket
# software rendering makes the native CSS/canvas interface less responsive
# and is unnecessary on most machines. Since the white-window bug is
# hardware-specific, the launcher now defaults to normal GPU-accelerated
# rendering. If the white-window bug
# resurfaces for a specific machine, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
# can still be set manually as an environment variable before launching.

import webview
from app import app
from worlds import APP_VERSION
from werkzeug.serving import make_server

LAN_MODE = "--lan" in sys.argv
HOST = "0.0.0.0" if LAN_MODE else "127.0.0.1"

# Phone Mode uses HTTPS so mobile browsers can enable secure-context features
# such as service workers and clipboard access on a bare LAN address. A
# persisted self-signed certificate keeps this local-only setup independent
# of a public domain and limits the trust warning to the first connection.
SCHEME = "https" if LAN_MODE else "http"


def local_network_ip():
    """Return the address another device on the same network can open.

    socket.gethostbyname(socket.gethostname()) is unreliable on a machine
    with more than one network adapter (VPN clients like Tailscale, virtual
    switches, etc.) — it can return whichever adapter happens to sort first,
    not the one actually reachable from the local Wi-Fi/LAN. Opening a UDP
    socket "toward" a public address (no packet is actually sent for UDP
    connect()) and reading back which local address the OS picked reliably
    returns the adapter that would be used for real outbound/LAN traffic.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            address = s.getsockname()[0]
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    return "127.0.0.1"


def get_or_create_cert():
    """Return (certfile, keyfile) paths for a persisted self-signed cert."""
    cert_dir = DATA_DIR / "phone_cert"
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as _dt

    import ipaddress
    cert_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Worldwalker RPG Phone Host")])
    now = _dt.datetime.now(_dt.timezone.utc)
    san_ips = {"127.0.0.1", local_network_ip()}
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ips]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_path), str(key_path)


SSL_CONTEXT = None
if LAN_MODE:
    SSL_CONTEXT = get_or_create_cert()

SERVER = make_server(HOST, 0, app, threaded=True, ssl_context=SSL_CONTEXT)
PORT = SERVER.server_port

WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
# Microsoft's documented existence-check key/GUID for the WebView2 Runtime
# (the "Evergreen" client id) — see the WebView2 distribution docs.
_WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_WEBVIEW2_REG_PATHS = [
    (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\%s" % _WEBVIEW2_CLIENT_GUID,),
    (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\%s" % _WEBVIEW2_CLIENT_GUID,),
]


def webview2_installed():
    """Best-effort check for the Microsoft Edge WebView2 Runtime on Windows.

    pywebview silently falls back to the ancient IE/mshtml engine when this
    Runtime is missing, which can't run this app's JS at all — the result is
    a blank white window with no error, so we check up front instead.
    """
    if sys.platform != "win32":
        return True
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for (subkey,) in _WEBVIEW2_REG_PATHS:
            try:
                with winreg.OpenKey(hive, subkey):
                    return True
            except OSError:
                continue
    return False


def warn_missing_webview2():
    message = (
        "Worldwalker RPG needs the Microsoft Edge WebView2 Runtime to display "
        "its window, and it doesn't look like it's installed on this PC.\n\n"
        "This is a small, free, official Microsoft component (most Windows 10/11 "
        "PCs already have it from Windows Update, but some don't yet).\n\n"
        "Click \"Open Download Page\" to get it, then relaunch Worldwalker RPG."
    )
    try:
        import tkinter as tk
        from tkinter import messagebox
        import webbrowser
        root = tk.Tk()
        root.withdraw()
        if messagebox.askokcancel(
            "Worldwalker RPG — Missing Component",
            message,
            icon="warning",
            default="ok",
        ):
            webbrowser.open(WEBVIEW2_DOWNLOAD_URL)
        root.destroy()
    except Exception:
        # Tkinter unavailable for some reason — fall back to stderr so the
        # failure is at least visible instead of a silent blank window.
        print(message)
        print(WEBVIEW2_DOWNLOAD_URL)


def run_server():
    SERVER.serve_forever()


# The internal readiness poll and --self-test both talk to our own freshly
# generated self-signed cert — there's no CA to validate it against, and
# that's fine here since this is just the process checking its own server is
# up, not a real security boundary.
_LOCAL_SSL_CONTEXT = None
if LAN_MODE:
    _LOCAL_SSL_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    _LOCAL_SSL_CONTEXT.check_hostname = False
    _LOCAL_SSL_CONTEXT.verify_mode = ssl.CERT_NONE


if __name__ == "__main__":
    if "--self-test" not in sys.argv and not webview2_installed():
        warn_missing_webview2()
        raise SystemExit(1)
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    url = f"{SCHEME}://127.0.0.1:{PORT}/"
    for _ in range(80):
        try:
            with urlopen(f"{url}api/version", timeout=.25, context=_LOCAL_SSL_CONTEXT):
                break
        except Exception:
            time.sleep(.05)
    else:
        raise RuntimeError("Worldwalker could not start its local game server.")
    if "--self-test" in sys.argv:
        with urlopen(f"{url}api/version", timeout=3, context=_LOCAL_SSL_CONTEXT) as response:
            version = json.load(response)
        with urlopen(f"{url}api/state", timeout=3, context=_LOCAL_SSL_CONTEXT) as response:
            state = json.load(response)
        if version.get("version") != APP_VERSION or state.get("campaign_active") is not False or state.get("state", {}).get("turn") != 0:
            raise RuntimeError("Packaged fresh-launch self-test failed.")
        SERVER.shutdown()
        raise SystemExit(0)
    if LAN_MODE:
        phone_url = f"{SCHEME}://{local_network_ip()}:{PORT}/"
        window_url = f"{url}?phone_host=1&lan_url={quote(phone_url, safe='')}"
        title = f"Worldwalker Phone Host — {phone_url}"
        webview.create_window(title, window_url, width=1180, height=860, min_size=(720, 620))
    else:
        webview.create_window("Worldwalker RPG", url, width=1520, height=940, min_size=(1180, 720))
    try:
        webview.start()
    finally:
        SERVER.shutdown()
