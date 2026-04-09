# qmcp - QDrant MCP Server для OpenCode

[![Версия](https://img.shields.io/badge/version-0.2.1-blue.svg)](https://github.com/BigKAA/qmcp)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org/)
[![Лицензия](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-Server-blue.svg)](https://modelcontextprotocol.io/)

**Сервер семантического поиска кода и документации с использованием векторной базы данных Qdrant.**

**Язык:** [English](./README.md) | Русский

---

## Возможности

- **Семантический поиск**: Находите код и документацию с помощью запросов на естественном языке
- **Поддержка нескольких языков**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Автоматическое обновление**: Следит за изменениями файлов и автоматически переиндексирует
- **Инкрементальная индексация**: Индексирует только изменённые файлы
- **Поддержка .gitignore**: Уважает `.gitignore` — исключает `node_modules`, `__pycache__`, `.venv` и т.д.
- **Очистка**: Удаляет устаревшие векторы для удалённых/изменённых файлов
- **Диагностика**: Инструменты для понимания того, что проиндексировано
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

## Быстрый старт

### 1. Убедитесь, что Qdrant запущен

Для Kubernetes см. [Qdrant on Kubernetes](https://github.com/BigKAA/youtube/tree/master/Utils/Qdrant).

### 2. Добавьте MCP Server в OpenCode

```bash
opencode mcp add qmcp-qdrant qmcp-qdrant
```

> ⚠️ **Примечание**: Переменные окружения необходимо указать в файле `~/.config/opencode/opencode.json` (см. ниже).

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
        "QDRANT_URL": "http://192.168.218.190:6333"
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
        "QDRANT_URL": "http://192.168.218.190:6333"
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

Индексатор автоматически уважает `.gitignore` файлы, что значительно сокращает размер индекса за счёт исключения:
- Зависимостей: `node_modules/`, `vendor/`, `.venv/`, `.pip cache/`
- Артефактов сборки: `dist/`, `build/`, `*.class`, `*.o`, `*.so`
- Сгенерированных файлов: `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`
- Настроек IDE: `.idea/`, `.vscode/`, `*.swp`, `*.swo`
- Файлов окружения: `.env`, `.env.local`, `*.log`

## Конфигурация

| Переменная окружения | По умолчанию | Описание |
|---------------------|-------------|----------|
| `QDRANT_URL` | `http://localhost:6333` | URL сервера Qdrant |
| `QDRANT_API_KEY` | (нет) | API ключ Qdrant (опционально) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Модель эмбеддингов |
| `EMBEDDING_CACHE_DIR` | (системный tmp) | Кастомная директория для кэша модели |
| `WATCH_PATHS` | `/data/repo` | Пути для наблюдения |
| `BATCH_SIZE` | `50` | Размер пакета для индексации |
| `DEBOUNCE_SECONDS` | `5` | Задержка debounce |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `LOG_FORMAT` | `text` | Формат логов (`text` или `json`) |

> 💡 **Кэш модели**: Установите `EMBEDDING_CACHE_DIR` для сохранения модели между запусками. Первый запуск загружает модель (~13MB), последующие используют кэш.

## MCP Инструменты

### Поиск и индексация

| Инструмент | Описание |
|------------|---------|
| `qdrant_search` | Семантический поиск в коде/документации |
| `qdrant_index_directory` | Индексировать директорию |
| `qdrant_reindex` | Переиндексировать (полное или инкрементальное) |

> 💡 **Совет**: Используйте `qdrant_search` с фильтрами для точных результатов:
> - `chunk_type` — фильтр по типу кода (function_def, class_def и т.д.)
> - `symbol_name` — найти точный символ по имени
> - `language` — фильтр по языку программирования
>
> Подробные примеры см. в [docs/STRUCTURED_METADATA.ru.md](./docs/STRUCTURED_METADATA.ru.md).

### Управление коллекциями

| Инструмент | Описание |
|------------|---------|
| `qdrant_list_collections` | Список всех коллекций |
| `qdrant_get_collection_info` | Информация о коллекции |
| `qdrant_delete_collection` | Удалить коллекцию |

### Диагностика (НОВОЕ)

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

## OpenCode Skill

Проект включает OpenCode skill для управления Qdrant на естественном языке.

### Установка

```bash
# Скопируйте skill в директорию OpenCode skills
cp -r skills/qmcp-manager ~/.config/opencode/skills/
```

### Использование

После установки OpenCode автоматически активирует skill когда вы спросите:

| Запрос | Что происходит |
|--------|---------------|
| `what's indexed in my Qdrant?` | Диагностирует коллекцию и показывает статистику |
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

## Интеграция с OpenCode

### Добавление MCP Server

```bash
opencode mcp add qmcp-qdrant qmcp-qdrant
```

Или отредактируйте `~/.config/opencode/opencode.json` напрямую (необходимо для переменных окружения):

```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "local",
      "command": ["qmcp-qdrant"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333"
      }
    }
  }
}
```

### Управление MCP Servers

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
make mcp-dev      # Запуск с MCP inspector
```

## Решение проблем

Если вы столкнулись с проблемами, см. [Руководство по решению проблем](./docs/TROUBLESHOOTING.md):

- **[Проблемы с моделью эмбеддингов](./docs/TROUBLESHOOTING.md#embedding-model-issues)** — диагностика и исправление `indexed_vectors_count: 0`
- **[Проблемы с подключением](./docs/TROUBLESHOOTING.md#connection-problems)** — устранение проблем подключения к Qdrant
- **[Поиск не возвращает результаты](./docs/TROUBLESHOOTING.md#search-returns-no-results)** — отладка пустых результатов поиска

## Лицензия

Apache 2.0
