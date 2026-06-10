build:
    docker build -t corabea-transcriber:latest .

build-gpu:
    docker build -f Dockerfile.gpu -t corabea-transcriber:gpu .

deploy: (build)
    cd /opt/transcriber && docker compose up -d

deploy-gpu: (build-gpu)
    cd /opt/transcriber && docker compose -f docker-compose.yaml -f docker-compose.gpu.yaml up -d

pull-llm model="qwen2.5:14b-instruct-q4_K_M":
    cd /opt/transcriber && docker compose up -d ollama && docker exec ollama ollama pull {{model}}

list-rooms:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli list

transcribe roomhash:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli run {{roomhash}}
