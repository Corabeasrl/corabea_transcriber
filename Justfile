build:
    docker build -t corabea-transcriber:latest .

build-gpu:
    docker build -f Dockerfile.gpu -t corabea-transcriber:gpu .

deploy: (build)
    cd /opt/transcriber && docker compose up -d

deploy-gpu: (build-gpu)
    cd /opt/transcriber && docker compose -f docker-compose.yaml -f docker-compose.gpu.yaml up -d

pull-model model="":
    cd /opt/transcriber && docker compose run --rm \
        {{ if model == "" { "" } else { "-e WHISPER_MODEL=" + model } }} \
        transcriber \
        python -c "from app.config import get_settings; from app.transcriber import Transcriber; Transcriber(get_settings())"

list-rooms:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli list

transcribe roomhash:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli run {{roomhash}}
