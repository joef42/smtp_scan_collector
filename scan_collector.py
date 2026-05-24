"""
scan_collector.py
A minimal SMTP server that accepts incoming emails and saves any attachments
to a configurable output directory. Designed for use with network scanners
(e.g. Brother ADS-1700W) that support "Scan to E-mail Server".
"""

import asyncio
import email
import logging
import os
import ssl
import warnings
from datetime import datetime

from aiosmtpd.controller import Controller
from aiosmtpd.handlers import AsyncMessage
from aiosmtpd.smtp import AuthResult, LoginPassword

# aiosmtpd's TLS detection only recognizes STARTTLS, not implicit TLS, so it
# emits a UserWarning at startup and a logger warning per connection when we
# combine auth_required with auth_require_tls=False. The session is in fact
# encrypted from byte 0 via ssl_context, so AUTH is not exposed in plaintext.
warnings.filterwarnings(
    "ignore",
    message="Requiring AUTH while not requiring TLS.*",
    category=UserWarning,
)

# ── Configuration (override via environment variables) ────────────────────────
HOST        = os.environ.get("SMTP_HOST",    "0.0.0.0")
PORT        = int(os.environ.get("SMTP_PORT", 8025))
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR",   "/scans")
LOG_LEVEL   = os.environ.get("LOG_LEVEL",    "INFO")
TLS_CERT    = os.environ.get("TLS_CERT",     "/certs/scan-collector.crt")
TLS_KEY     = os.environ.get("TLS_KEY",      "/certs/scan-collector.key")
SMTP_USER   = os.environ["SMTP_USER"]
SMTP_PASS   = os.environ["SMTP_PASS"]
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scan-collector")

def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def authenticate(server, session, envelope, mechanism, auth_data) -> AuthResult:
    if not isinstance(auth_data, LoginPassword):
        return AuthResult(success=False, handled=False)
    if auth_data.login.decode() == SMTP_USER and auth_data.password.decode() == SMTP_PASS:
        return AuthResult(success=True)
    log.warning("Auth failure for user %r", auth_data.login.decode(errors="replace"))
    return AuthResult(success=False, handled=False)


class ScanHandler(AsyncMessage):
    """Save every attachment that arrives in any email."""

    async def handle_message(self, message: email.message.Message) -> None:
        sender  = message.get("From", "unknown")
        subject = message.get("Subject", "(no subject)")
        log.info("Mail from %s — %s", sender, subject)

        saved = 0
        for part in message.walk():
            filename = part.get_filename()
            if not filename:
                continue  # skip non-attachment parts

            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            ext = os.path.splitext(filename)[1]
            date_prefix = datetime.now().strftime("%Y_%m_%d")
            counter = 0
            while True:
                safe_name = f"{date_prefix} {counter:04d}{ext}"
                dest = os.path.join(OUTPUT_DIR, safe_name)
                if not os.path.exists(dest):
                    break
                counter += 1

            await asyncio.to_thread(_write_file, dest, payload)

            log.info("  Saved attachment → %s (%d bytes)", safe_name, len(payload))
            saved += 1

        if saved == 0:
            log.warning("  No attachments found in message from %s", sender)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log.info("Scan collector starting — listening on %s:%d (implicit TLS)", HOST, PORT)
    log.info("Saving attachments to %s", OUTPUT_DIR)

    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(TLS_CERT, TLS_KEY)

    controller = Controller(
        ScanHandler(message_class=email.message.EmailMessage),
        hostname=HOST,
        port=PORT,
        ssl_context=ssl_ctx,
        authenticator=authenticate,
        auth_required=True,
        auth_require_tls=False,  # implicit TLS; whole session is already encrypted
    )
    controller.start()

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
