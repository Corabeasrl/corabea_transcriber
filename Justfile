build:
    docker build -t corabea-transcriber:latest .

deploy: (build)
    cd /opt/transcriber && docker compose up -d

pull-model model="":
    cd /opt/transcriber && docker compose run --rm \
        {{ if model == "" { "" } else { "-e WHISPER_MODEL=" + model } }} \
        transcriber \
        python -c "from app.config import get_settings; from app.transcriber import Transcriber; Transcriber(get_settings())"

list-rooms:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli list

transcribe roomhash:
    cd /opt/transcriber && docker compose run --rm transcriber python -m app.cli run {{roomhash}}
