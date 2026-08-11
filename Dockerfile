FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN groupadd -r agent && useradd -r -g agent agent

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY supabase ./supabase

RUN chown -R agent:agent /app
USER agent

EXPOSE 8080

CMD ["python", "-m", "app.main"]
