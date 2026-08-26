# VSTU Schedule Bot

Асинхронный Telegram-бот расписания ВолгГТУ с расширяемым парсером старых
`.xls` и новых `.xlsx`-таблиц. Сейчас рабочий источник ограничен одним файлом:
**«1 курс ФЭВТ.xls»** со страницы [расписаний магистратуры](https://www.vstu.ru/student/raspisaniya/zanyatiy/index.php?dep=mag).

## Возможности

- расписание выбранной группы на сегодня, завтра, произвольный день, текущую и
  следующую недели;
- поиск преподавателя по части фамилии и недельное расписание по всем группам;
- сохранение группы пользователя;
- inline-навигация без необходимости запоминать команды;
- официальное [расписание звонков ВолгГТУ](https://www.vstu.ru/student/raspisaniya/raspisanie-zvonkov/);
- фоновая проверка источника каждые 5 минут;
- `ETag` / `Last-Modified` / SHA-256: неизменившийся файл повторно не разбирается;
- атомарная замена данных в SQLite — бот не видит наполовину обновлённое расписание;
- JSON-логи, health/readiness endpoints и запуск от непривилегированного
  пользователя в контейнере.

## Быстрый запуск в Docker

Токен не читается приложением из файла и не попадает в образ. В PowerShell его
можно безопасно передать из локального файла `token`, который исключён из Git:

```powershell
$env:BOT_TOKEN = (Get-Content -Raw .\token).Trim()
docker compose up --build -d
docker compose logs -f bot
```

Проверка состояния:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/ready
```

Остановка: `docker compose down`.

SQLite хранится в именованном volume `schedule-data` и переживает пересоздание
контейнера.

## Локальная разработка

Требуется Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:BOT_TOKEN = (Get-Content -Raw .\token).Trim()
python -m vstu_schedule_bot
```

Приложение при старте получает расписание, после чего начинает Telegram long
polling и запускает лёгкую фоновую задачу обновления.

## Управление ботом

- `/start` — главное меню;
- `/today` — сегодня;
- `/week` — текущая неделя;
- `/group` или `/group ЭВМ` — выбор/поиск группы;
- `/teacher` или `/teacher Аникин` — поиск преподавателя.

Весь основной сценарий также доступен кнопками. В недельной выдаче можно листать
недели, в дневной — соседние дни.

## Конфигурация

Все параметры поступают через переменные окружения. Пример без секретов находится
в `.env.example`.

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `BOT_TOKEN` | — | обязательный токен BotFather |
| `DATABASE_PATH` | `data/schedule.db` | путь к SQLite |
| `SOURCE_PAGE_URL` | страница магистратуры | страница со ссылками на Excel |
| `SOURCE_FILE_PATTERN` | `1 курс ФЭВТ.xls` | маска текста ссылки |
| `FACULTY_NAME` | `ФЭВТ` | подпись факультета |
| `UPDATE_INTERVAL_SECONDS` | `300` | период проверки, минимум 60 секунд |
| `REQUEST_TIMEOUT_SECONDS` | `30` | сетевой таймаут |
| `TIMEZONE` | `Europe/Moscow` | локальная дата расписания |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `LOG_FORMAT` | `json` | `json` или обычный текст |
| `HEALTH_HOST` / `HEALTH_PORT` | `0.0.0.0:8080` | служебный HTTP-сервер |

## Архитектура

```text
официальная HTML-страница
        │ обнаружение нужной ссылки
        ▼
условная загрузка XLS/XLSX ── SHA-256 ── пропуск неизменившегося файла
        │
        ▼
WorkbookReaderRegistry (XlsReader / XlsxReader)
        │ единая сетка ячеек и объединённых областей
        ▼
ParserRegistry ── VstuGridParser ── нормализованные Lesson
        │
        ▼
SQLite (транзакционная замена) ── ScheduleService ── aiogram handlers
```

Excel-ридеры ничего не знают о семантике расписания. Парсеры ничего не знают о
Telegram и SQLite. Новый формат добавляется реализацией интерфейса
`ScheduleParser` и регистрацией в `parsing/factory.py`; существующий код загрузки,
хранения и бота менять не требуется. Подробности и результаты исследования
таблиц — в [docs/parser-architecture.md](docs/parser-architecture.md).

## Проверки

```powershell
ruff format --check src tests
ruff check src tests
mypy src
pytest
docker build -t vstu-schedule-bot .
```

Smoke-тест с реальным `.xls` запускается автоматически, если исследовательский
файл находится в `.research/fevt1.xls`; в чистом репозитории тест корректно
пропускается.

## Секреты и эксплуатация

- `token`, `.env`, базы и исследовательские Excel-файлы исключены из Git и
  Docker build context;
- токен не выводится в логах;
- контейнер работает без root, с read-only root filesystem, без Linux
  capabilities и с ограничением ресурсов;
- при временной ошибке сайта уже загруженное расписание остаётся доступным;
- `/health` показывает жизнеспособность процесса, `/ready` возвращает `503`, пока
  в базе нет расписания.

Проект не является официальным сервисом ВолгГТУ; источником истины остаются файлы
на сайте университета.
