FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -r -u 10002 -m -d /home/planner planner
WORKDIR /srv
RUN pip install --no-cache-dir \
    fastapi==0.141.1 \
    uvicorn==0.34.0 \
    pydantic==2.10.4 \
    opentelemetry-api==1.29.0 \
    opentelemetry-sdk==1.29.0 \
    opentelemetry-exporter-otlp-proto-http==1.29.0
COPY app/planning.py ./planning.py
COPY planner_runner/app.py ./app.py
RUN chown -R planner:planner /srv
USER 10002:10002
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8082"]
