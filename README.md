# scan-collector

A tiny SMTP server that receives e-mails from a network scanner's "Scan to
E-mail Server" feature and saves the attachments to disk. Built for the
Brother ADS-1700W but should work with any scanner that can send scans over
SMTP.

The scanner sends each scan job as an e-mail with the document attached;
this server accepts the e-mail, throws the body away, and writes the
attachment(s) to a directory you mount as a volume. No real mail server,
no IMAP, no Postfix — just files on disk.

## Features

- Implicit TLS (SMTPS) with a self-signed certificate
- SMTP-AUTH (username + password from environment)
- Per-recipient routing: mail to `alice@…` lands in `scans/alice/`,
  mail to `default@…` lands in `scans/`
- Files named `YYYY_MM_DD NNNN.<ext>` with an auto-incrementing counter
- Runs rootless under Podman with a non-root user inside the container

## Quick start

```bash
git clone https://github.com/joef42/smtp_scan_collector
cd smtp_scan_collector

# 1. Generate a self-signed cert + key
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout certs/scan-collector.key \
    -out    certs/scan-collector.crt \
    -days 3650 -subj "/CN=scan-collector.local"
chmod 600 certs/scan-collector.key

# 2. Set SMTP credentials
cat > .env <<EOF
SMTP_USER=scanner
SMTP_PASS=$(openssl rand -base64 18)
EOF
chmod 600 .env

# 3. Start
podman-compose up -d
```

The server listens on TCP port `8025` by default (changeable via
`SMTP_PORT` in `compose.yml`). Scans are written to `./scans/`.

## Brother scanner configuration

On the scanner's web admin (`http://<scanner-ip>/`):

**Network → Protocol → SMTP** (or "Scan to E-mail Server"):

| Setting | Value |
|---|---|
| Server Address | IP of the host running scan-collector |
| Server Port | `8025` |
| SSL/TLS | **SSL** (implicit TLS — not STARTTLS) |
| Verify Server Certificate | Off, **or** upload `certs/scan-collector.crt` under Security → CA Certificate and turn this on |
| Server Authentication Method | **SMTP-AUTH** |
| Account Name | matches `SMTP_USER` from `.env` |
| Password | matches `SMTP_PASS` from `.env` |

**Address book entries** — the local-part (before `@`) determines the
subfolder:

| Recipient address | Saved to |
|---|---|
| `default@anything.tld` | `scans/` |
| `alice@anything.tld`   | `scans/alice/` |
| `receipts@x.y`         | `scans/receipts/` |

The domain part is ignored; pick anything that the scanner's address
validation accepts (e.g. `scan@local.lan`).

> **Note:** Brother firmware validates the recipient string as a
> syntactically valid e-mail. Don't use a bare username like `alice` —
> the scanner will report "Timeout" on the LCD even though the scan
> was actually delivered. Always include a domain.

## Configuration reference

All settings are environment variables; defaults in parentheses.

| Variable | Default | Purpose |
|---|---|---|
| `SMTP_HOST` | `0.0.0.0` | Bind address inside the container |
| `SMTP_PORT` | `8025` | Listen port |
| `OUTPUT_DIR` | `/scans` | Where attachments are written |
| `TLS_CERT` | `/certs/scan-collector.crt` | Path to TLS certificate |
| `TLS_KEY` | `/certs/scan-collector.key` | Path to TLS private key |
| `SMTP_USER` | *(required)* | SMTP-AUTH username |
| `SMTP_PASS` | *(required)* | SMTP-AUTH password |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Files

- [`scan_collector.py`](scan_collector.py) — the SMTP server (~120 lines)
- [`Dockerfile`](Dockerfile) — `python:3.12-slim` + `aiosmtpd`, non-root user
- [`compose.yml`](compose.yml) — Podman/Docker Compose definition

## Security notes

- The container runs rootless (Podman `userns_mode: keep-id`) with a
  non-root user inside, and `no-new-privileges` is set. A container
  escape gives the attacker an unprivileged shell on the host, not root.
- SMTP-AUTH is enforced; the server rejects `MAIL FROM` without prior
  authentication.
- The whole SMTP session is wrapped in TLS from the first byte, so
  credentials and message contents are never transmitted in plaintext.
- The self-signed certificate is intended for use on a trusted LAN.
  For anything more exposed, use a CA-signed cert.

## Troubleshooting

**Scanner shows "Timeout" but the PDF actually arrived.** The recipient
address is probably not in `local@domain` form. Edit the scanner's
address book entry to include a domain.

**Scanner shows "Timeout" and no file arrives.** Check the container
logs (`podman logs scan-collector`). The most common causes are wrong
port, wrong SSL/TLS mode (must be SSL, not TLS/STARTTLS), or wrong
SMTP-AUTH credentials.

**`ssl.SSLError: UNSUPPORTED_PROTOCOL`.** The scanner is negotiating a
TLS version below Python's default minimum (1.2). The Brother
ADS-1700W handshakes fine with default settings in *SSL* mode; this
error shows up if you've configured it for *TLS* (STARTTLS) instead,
where the same firmware drops to TLS 1.0/1.1. Switch the scanner back
to SSL.

**Debug-level SMTP wire log.** Set `LOG_LEVEL=DEBUG` and add
`logging.getLogger("mail.log").setLevel(logging.DEBUG)` near the top
of `scan_collector.py` to see every command and response.

## License

MIT
