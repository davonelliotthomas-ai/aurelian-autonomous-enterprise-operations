FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -r -u 10001 -m -d /home/runner runner
WORKDIR /srv
RUN pip install --no-cache-dir \
    fastapi==0.141.1 \
    uvicorn==0.34.0 \
    pydantic==2.10.4 \
    opentelemetry-api==1.29.0 \
    opentelemetry-sdk==1.29.0 \
    opentelemetry-exporter-otlp-proto-http==1.29.0
COPY tool_runner ./tool_runner
RUN chown -R runner:runner /srv
USER 10001:10001
CMD ["uvicorn","tool_runner.app:app","--host","0.0.0.0","--port","8081"]
