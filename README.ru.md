# qmcp - QDrant MCP Server для OpenCode

[![Версия](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/BigKAA/qmcp)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org/)
[![Лицензия](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-Server-blue.svg)](https://modelcontextprotocol.io/)

**Сервер семантического поиска кода и документации с использованием векторной базы данных Qdrant.**

**Язык:** [English](./README.md) | Русский

## Возможности

- **Семантический поиск**: Находите код и документацию с помощью запросов на естественном языке
- **Поддержка нескольких языков**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Выбор модели**: Выбирайте модель эмбеддингов для каждой коллекции (поиск по коду, документация, мультиязычная база знаний)
- **Корпоративная база знаний**: Архитектура с несколькими коллекциями для общей корпоративной информации
- **Поддержка E5 модели**: Автоматическое добавление префиксов `query:` и `passage:` для модели `intfloat/multilingual-e5-large`
- **Автоматическое обновление**: Следит за изменениями файлов и автоматически переиндексирует
- **Инкрементальная индексация**: Индексирует только изменённые файлы
- **Поддержка .gitignore**: Уважает `.gitignore` — исключает `node_modules`, `__pycache__`, `.venv` и т.д.
- **Очистка**: Удаляет устаревшие векторы для удалённых/изменённых файлов
- **Диагностика**: Инструменты для понимания того, что проиндексировано
- **Поиск по нескольким коллекциям**: Одновременный поиск по нескольким коллекциям
- **OpenCode Skill**: Интерфейс на естественном языке для управления Qdrant

## Установка

### Через PyPI (Рекомендуется)

```bash
pip install qmcp-qdrant
```

### Через uv

```bash
uv tool install qmcp-qdrant
```

### Из исходников

```bash
git clone https://github.com/BigKAA/qmcp.git
cd qmcp
make install
```

## Обновление

### Через uv (Рекомендуется)

```bash
uv tool upgrade qmcp-qdrant
```

### Через pip

```bash
pip install --upgrade qmcp-qdrant
```

## Быстрый старт

### 1. Убедитесь, что Qdrant запущен

Для Kubernetes см. [Qdrant on Kubernetes](https://github.com/BigKAA/youtube/tree/master/Utils/Qdrant).

### 2. Добавьте MCP Server в OpenCode

```bash
opencode mcp add qmcp-qdrant qmcp-qdrant
```

> ⚠️ **Примечание**: Переменные окружения необходимо указать в файле `~/.config/opencode/opencode.json`.

## Конфигурация

| Переменная окружения | По умолчанию | Описание |
|---------------------|-------------|----------|
| `QDRANT_URL` | `http://localhost:6333` | URL сервера Qdrant |
| `QDRANT_API_KEY` | (нет) | API ключ Qdrant (опционально) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Модель эмбеддингов по умолчанию (используется когда не указана для коллекции) |
| `EMBEDDING_CACHE_DIR` | (системный tmp) | Кастомная директория для кэша модели |
| `WATCH_PATHS` | `/data/repo` | Базовые пути, которые автоматически отслеживаются при старте сервера |
| `BATCH_SIZE` | `50` | Размер пакета для индексации |
| `DEBOUNCE_SECONDS` | `5` | Задержка debounce |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `LOG_FORMAT` | `text` | Формат логов (`text` или `json`) |

> 💡 **Кэш модели**: Установите `EMBEDDING_CACHE_DIR` для сохранения модели между запусками. Первый запуск загружает модель (~7-2240MB в зависимости от модели), последующие используют кэш.

> 💡 **Выбор модели**: Переменная `EMBEDDING_MODEL` устанавливает модель **по умолчанию**. Однако вы можете переопределить её для каждой коллекции с помощью параметра `model=` в `qdrant_index_directory()` или `qdrant_reindex()`. Каждая коллекция автоматически сохраняет свою модель в метаданных.

> 💡 **Примеры WATCH_PATHS**:
> - Один путь: `WATCH_PATHS=/home/user/project`
> - Несколько путей: `WATCH_PATHS=/home/user/project,/home/user/docs`
> - JSON-массив: `WATCH_PATHS=["/home/user/project", "/home/user/docs"]`

## Выбор модели эмбеддингов

qmcp поддерживает несколько моделей эмбеддингов. Используйте `qdrant_list_supported_models()` для просмотра всех доступных моделей:

| Сценарий использования | Рекомендуемая модель | Dim | Размер | Примечания |
|-----------------------|---------------------|-----|--------|-----------|
| **Поиск по коду** | `jinaai/jina-embeddings-v2-base-code` | 768 | 0.64 GB | Лучшая для кода, 30+ языков |
| **Документация EN (лёгкая)** | `BAAI/bge-small-en-v1.5` | 384 | 0.07 GB | Быстрая, маленькая, хорошее качество |
| **Документация EN (качество)** | `BAAI/bge-large-en-v1.5` | 1024 | 1.2 GB | Лучшее качество для английского |
| **Мультиязычная БЗ (RU+EN)** | `intfloat/multilingual-e5-large` | 1024 | 2.24 GB | Лучшая для корпоративной БЗ, 100+ языков |
| **Мультиязычная (лёгкая)** | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | 0.22 GB | Компромиссный вариант |

### Автоматическая обработка префиксов E5 модели

> ⚠️ **Важно**: Модель `intfloat/multilingual-e5-large` требует специальные префиксы (`query: ` и `passage: `) для оптимальных результатов. **Это обрабатывается автоматически qmcp** — никаких действий не требуется!

При индексации или поиске с E5 моделью qmcp автоматически:
- Добавляет префикс `passage: ` к содержимому при индексации
- Добавляет префикс `query: ` к запросам при поиске

### Модель для каждой коллекции

Каждая коллекция хранит свою модель эмбеддингов в метаданных. Проверить модель можно через:

```
qdrant_get_collection_info(collection="my-collection")
# Возвращает: { ..., "embedding_model": "jinaai/jina-embeddings-v2-base-code" }
```

Чтобы изменить модель коллекции, переиндексируйте с новой моделью:
```
qdrant_reindex(path="/path/to/code", collection="my-collection", model="jinaai/jina-embeddings-v2-base-code", mode="full")
```

### 3. Готово!

OpenCode автоматически найдёт и использует инструменты семантического поиска.

### Ручная настройка (Альтернатива)

Если команда `opencode mcp add` не работает, отредактируйте `~/.config/opencode/opencode.json` напрямую:

```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "local",
      "command": ["qmcp-qdrant"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333",
        "WATCH_PATHS": "/home/user/shared-docs,/home/user/shared-snippets"
      }
    }
  }
}
```

Для Python модуля:
```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "local",
      "command": ["python", "-m", "qmcp.server"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333",
        "WATCH_PATHS": "/home/user/shared-docs,/home/user/shared-snippets"
      }
    }
  }
}
```

## Примечания об индексации

> ⚠️ **Важно**: Полная индексация и переиндексация больших проектов может занять значительное время (минуты или часы в зависимости от размера проекта).

Для больших кодовых баз предпочитайте:
- **Инкрементальную переиндексацию** (`mode="incremental"`) — обновляет только изменённые файлы на основе хэшей содержимого
- **Наблюдатель за файлами** — включает автоматическое обновление при изменении файлов

### Стратегия автоматической индексации

`qmcp` поддерживает автоматическую индексацию на двух уровнях:

1. **Уровень запуска сервера** — при старте MCP сервер автоматически пытается включить watcher для путей из `WATCH_PATHS`.
2. **Уровень workspace-сессии** — поскольку один глобальный MCP сервер может использоваться в нескольких репозиториях, агент должен проверять состояние watcher для текущего workspace и вызывать `qdrant_watch_ensure(paths=[workspace_root])`, если путь workspace отсутствует в наблюдаемых путях.

Рекомендуемый сценарий для каждого нового workspace в OpenCode:

```python
status = qdrant_get_status()

# Если watcher не активен или текущий репозиторий не покрыт,
# безопасно расширяем список путей без потери других проектов.
qdrant_watch_ensure(paths=["/absolute/path/to/current/workspace"])
```

`qdrant_watch_ensure` объединяет текущий workspace с уже отслеживаемыми путями и `WATCH_PATHS`, поэтому безопасен для одного глобального MCP, который используется в нескольких проектах.

## MCP Инструменты

### Поиск и индексация

| Инструмент | Описание |
|------------|---------|
| `qdrant_search` | Семантический поиск в коде/документации |
| `qdrant_search_many` | Поиск по нескольким коллекциям одновременно |
| `qdrant_index_directory` | Индексировать директорию с выбором модели |
| `qdrant_reindex` | Переиндексировать (полное или инкрементальное) с возможностью сменить модель |
| `qdrant_list_supported_models` | Список доступных моделей эмбеддингов с метаданными |

> 💡 **Совет**: Используйте `qdrant_search` с фильтрами для точных результатов:
> - `chunk_type` — фильтр по типу кода (function_def, class_def и т.д.)
> - `symbol_name` — найти точный символ по имени
> - `language` — фильтр по языку программирования
>
> Подробные примеры см. в [docs/STRUCTURED_METADATA.ru.md](./docs/STRUCTURED_METADATA.ru.md).

> 💡 **Выбор модели**: Передайте `model="jinaai/jina-embeddings-v2-base-code"` в `qdrant_index_directory` или `qdrant_reindex` для использования конкретной модели эмбеддингов.

### Управление коллекциями

| Инструмент | Описание |
|------------|---------|
| `qdrant_list_collections` | Список всех коллекций |
| `qdrant_get_collection_info` | Информация о коллекции (включает поле `embedding_model`) |
| `qdrant_delete_collection` | Удалить коллекцию |

### Диагностика и интроспекция

| Инструмент | Описание |
|------------|---------|
| `qdrant_diagnose_collection` | Полная диагностика коллекции — векторы, файлы, типы, проблемы |
| `qdrant_list_indexed_files` | Постраничный список проиндексированных файлов с метаданными |
| `qdrant_diff_collection` | Сравнение состояния Qdrant с файловой системой (orphans, missing, modified) |

### Обслуживание

| Инструмент | Описание |
|------------|---------|
| `qdrant_cleanup` | Очистка устаревших векторов (поддержка dry-run) |
| `qdrant_watch_start` | Запустить наблюдатель за файлами |
| `qdrant_watch_ensure` | Гарантировать наблюдение за workspace без потери других проектов |
| `qdrant_watch_stop` | Остановить наблюдатель за файлами |
| `qdrant_get_status` | Статус сервера |

### Примеры использования диагностических инструментов

```bash
# Диагностика коллекции — посмотреть что проиндексировано, типы файлов, проблемы
qdrant_diagnose_collection(collection="myproject")

# Список проиндексированных файлов с пагинацией
qdrant_list_indexed_files(collection="myproject", limit=50, offset=0)

# Фильтрация по типу файла
qdrant_list_indexed_files(collection="myproject", file_type=".py")

# Сравнение состояния Qdrant с файловой системой
qdrant_diff_collection(collection="myproject", repo_path="/path/to/repo")
```

## Корпоративная база знаний

qmcp поддерживает архитектуру с несколькими коллекциями для корпоративных баз знаний, доступных всем командам и проектам.

### Соглашение о наименовании коллекций

| Паттерн коллекции | Назначение | Рекомендуемая модель |
|-----------------|-----------|---------------------|
| `company-kb-docs` | Корпоративная база знаний (политики, wiki) | `intfloat/multilingual-e5-large` |
| `company-kb-snippets` | Переиспользуемые шаблоны, сниппеты кода | `jinaai/jina-embeddings-v2-base-code` |
| `team-<name>-docs` | Документация команды | `BAAI/bge-small-en-v1.5` |
| `team-<name>-code` | Общий код команды | `jinaai/jina-embeddings-v2-base-code` |
| `project-<name>-code` | Код проекта | `jinaai/jina-embeddings-v2-base-code` |
| `project-<name>-docs` | Документация проекта | `BAAI/bge-small-en-v1.5` |

### Пример: Настройка корпоративной базы знаний

```bash
# 1. Индексация корпоративной документации с мультиязычной моделью
qdrant_index_directory(
    path="/shared/corporate-docs",
    collection="company-kb-docs",
    model="intfloat/multilingual-e5-large",
    metadata={"team": "docs-team", "visibility": "internal"}
)

# 2. Индексация общих сниппетов кода
qdrant_index_directory(
    path="/shared/snippets",
    collection="company-kb-snippets",
    model="jinaai/jina-embeddings-v2-base-code",
    metadata={"team": "all", "visibility": "public"}
)

# 3. Поиск по всем коллекциям
qdrant_search_many(
    collections=["company-kb-docs", "company-kb-snippets"],
    query="How do I set up authentication?",
    limit=10
)
```

### Обогащение метаданными

Добавляйте кастомные метаданные к проиндексированным чанкам для фильтрации и организации:

```bash
qdrant_index_directory(
    path="/project/docs",
    collection="project-docs",
    metadata={
        "team": "backend",
        "project": "api-gateway",
        "visibility": "internal",
        "source_system": "confluence"
    }
)
```

Результаты поиска будут включать ваши поля метаданных для постобработки.

Подробные инструкции по настройке см. в [docs/COLLECTION_SETUP.md](./docs/COLLECTION_SETUP.md).

## OpenCode Skill

Проект включает OpenCode skill для управления Qdrant на естественном языке.

### Установка

```bash
# скопируйте skill в директорию OpenCode skills
cp -r skills/qmcp-manager ~/.config/opencode/skills/
```

### Использование

После установки OpenCode автоматически активирует skill когда вы спросите:

| Запрос | Что происходит |
|--------|---------------|
| `what's indexed in my Qdrant?` | Диагностирует коллекцию и показывает ст��тистику |
| `show collection stats` | Список всех коллекций с количеством векторов |
| `clean up orphans in my index` | Находит и показывает удаление осиротевших векторов |
| `diagnose my index` | Полная диагностика с проблемами и списком файлов |
| `compare index with /path/to/repo` | Показывает orphans, missing и modified файлы |
| `find missing files` | Список файлов на диске, но не в индексе |
| `is my index up to date?` | Сравнивает хэши для обнаружения изменений |

### Workflows предоставляемые Skill

1. **Quick Status** — Проверка состояния коллекции с `qdrant_list_collections`
2. **Full Diagnostics** — Детальный анализ с `qdrant_diagnose_collection`
3. **Diff** — Сравнение Qdrant с файловой системой через `qdrant_diff_collection`
4. **Safe Cleanup** — Предпросмотр с dry-run, затем подтверждение удаления
5. **Smart Reindex** — Инкрементальные обновления на основе хэшей файлов

### Расположение Skill

```
skills/qmcp-manager/SKILL.md
```

## Управление MCP Servers

```bash
opencode mcp list          # Список всех MCP серверов
opencode mcp debug qmcp-qdrant     # Отладка проблем подключения
opencode mcp logout qmcp-qdrant    # Удалить MCP сервер
```

## Разработка

```bash
make install      # Установить зависимости
make test         # Запустить тесты
make lint         # Линтинг кода
make format       # Форматирование кода
mcp-dev      # Запуск с MCP inspector
```

## Решение проблем

Если вы столкнулись с проблемами, см. [Руководство по решению пробл��м](./docs/TROUBLESHOOTING.md):

- **[Проблемы с моделью эмбеддингов](./docs/TROUBLESHOOTING.md#embedding-model-issues)** — диагностика и исправление `indexed_vectors_count: 0`
- **[Проблемы с подключением](./docs/TROUBLESHOOTING.md#connection-problems)** — устранение проблем подключения к Qdrant
- **[Поиск не возвращает результаты](./docs/TROUBLESHOOTING.md#search-returns-no-results)** — отладка пустых результатов поиска

## Лицензия

Apache 2.0