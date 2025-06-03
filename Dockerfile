FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Install git so pip can install from GitHub
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/main.py"]