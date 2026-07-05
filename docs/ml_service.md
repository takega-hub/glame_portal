# GLAME ML Service

`ml-service` — отдельный HTTP-сервис для server-side анализа внешности в сценарии `Главная -> Блок 3 -> Подбор по фото`.

## Назначение

Сервис принимает фотографию пользователя и возвращает structured analysis, который backend использует для:

- quality gate фото;
- анализа геометрии лица;
- базового color-analysis;
- формирования рекомендаций для ювелирного подбора;
- построения user-safe summary для mobile/web.

Пользователю не показываются технические параметры анализа напрямую.

## Где используется

- backend client: [ml_inference_client.py](file:///root/glame-platform/backend/app/services/ml_inference_client.py)
- orchestrator: [photo_analysis_orchestrator.py](file:///root/glame-platform/backend/app/services/photo_analysis_orchestrator.py)
- API: [look_tryon.py](file:///root/glame-platform/backend/app/api/look_tryon.py)
- mobile flow: [photo_upload_screen.dart](file:///root/glame-platform/mobile/glame_app/lib/src/features/home/photo_upload_screen.dart)

## Текущий статус

Сервис уже включён в репозиторий и поддерживает два режима:

- `mediapipe-color-v1` — основной путь `Phase 1`, если доступны `mediapipe`, `opencv`, `numpy`;
- `baseline-cpu-v1` — безопасный fallback, если face-mesh не сработал или runtime ушёл в ошибку.

## HTTP API

### `GET /health`

Health-check сервиса.

Пример ответа:

```json
{
  "status": "ok"
}
```

### `POST /analyze-face`

Принимает `multipart/form-data` с файлом `photo`.

Пример ответа:

```json
{
  "success": true,
  "can_continue": true,
  "quality_status": "ok",
  "retry_hint": null,
  "analysis": {
    "version": "1.0",
    "photoQuality": {},
    "faceGeometry": {},
    "appearanceScale": {},
    "lineAnalysis": {},
    "colorAnalysis": {},
    "textureAnalysis": {},
    "earAndLobeAnalysis": {},
    "neckAnalysis": {},
    "accentZones": {},
    "recommendations": {},
    "userFacing": {},
    "debug": {}
  }
}
```

## Структура сервиса

- entrypoint: [main.py](file:///root/glame-platform/ml-service/app/main.py)
- pipeline: [pipeline.py](file:///root/glame-platform/ml-service/app/pipeline.py)
- requirements: [requirements.txt](file:///root/glame-platform/ml-service/requirements.txt)
- image build: [Dockerfile](file:///root/glame-platform/ml-service/Dockerfile)

## Запуск локально через Docker

Из корня проекта:

```bash
docker compose -f infra/docker-compose.yml up -d --build ml_inference
```

Проверка:

```bash
curl http://127.0.0.1:8010/health
```

### Если host-порты уже заняты

`infra/docker-compose.yml` теперь поддерживает override host-портов через `infra/.env`.

Пример:

```env
POSTGRES_HOST_PORT=55433
QDRANT_HOST_PORT=56333
QDRANT_GRPC_HOST_PORT=56334
REDIS_HOST_PORT=56379
BACKEND_HOST_PORT=58000
ML_INFERENCE_HOST_PORT=58010
```

После этого:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
```

## Запуск вручную

Из каталога `ml-service`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

## Интеграция с backend

Backend использует переменную окружения:

```bash
ML_INFERENCE_URL=http://127.0.0.1:8010
```

Если переменная не задана или внешний ML endpoint недоступен, backend уходит в legacy fallback внутри `look_tryon_service`.

## Интеграция с systemd

Сервис `glame-stack` уже умеет поднимать `ml_inference` автоматически через `scripts/start_glame_stack.sh`.

Ключевые переменные для `systemctl restart glame-stack`:

- `START_ML_INFERENCE=true`
- `ML_INFERENCE_URL=http://127.0.0.1:8010`
- `ML_INFERENCE_COMPOSE_FILE=infra/docker-compose.yml`

Systemd unit:

- [glame-stack.service](file:///root/glame-platform/infra/systemd/glame-stack.service)

Пример override-файла:

- [glame-stack.env.example](file:///root/glame-platform/infra/systemd/glame-stack.env.example)

### Рекомендуемая настройка на сервере

```bash
sudo mkdir -p /etc/glame-platform
sudo cp /root/glame-platform/infra/systemd/glame-stack.env.example /etc/glame-platform/glame-stack.env
sudo systemctl daemon-reload
sudo systemctl restart glame-stack
sudo systemctl status glame-stack
```

После рестарта `glame-stack`:

1. запускает storefront/admin/backend;
2. до старта backend вызывает `docker compose ... up -d ml_inference`;
3. прокидывает `ML_INFERENCE_URL` в backend runtime.

## Ограничения текущей версии

- hair segmentation ещё не реализован;
- ear/lobe analysis пока эвристический;
- neck analysis пока эвристический;
- часть shape/color выводов остаётся baseline-level и требует дообучения/уточнения.

## Следующие шаги

- вынести pipeline на модули `quality_gate`, `face_landmarks`, `color_analysis`;
- добавить более точный single-person gate;
- улучшить ROI для кожи, глаз и волос;
- подключить сегментацию волос и confidence scores по блокам.
