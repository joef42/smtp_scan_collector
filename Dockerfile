FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir aiosmtpd

COPY scan_collector.py .

RUN useradd -r -u 1000 collector
USER collector

CMD ["python", "scan_collector.py"]
