# CamKinescope — Task Tracker

## Batch 1: Ядро — захват видео
- [x] Создать `config.yaml` с конфигурацией
- [x] Создать `src/logger_setup.py` — структурированное логирование
- [x] Создать `src/recorder.py` — захват RTSP через VLC + FFmpeg ремукс
- [x] Создать `requirements.txt`
- [x] Тест: запись работает, 60-мин сегменты ✅

## Batch 2: Загрузка + уведомления
- [x] Создать `src/uploader.py` — Kinescope Uploader API v2
- [x] Создать `src/notifier.py` — Telegram уведомления (plain text для ошибок)
- [x] Тест: Telegram уведомления работают ✅
- [ ] Тест: загрузка в Kinescope + play_link (ожидает первого результата)

## Batch 3: Оркестратор + автозапуск
- [x] Создать `src/main.py` — бесконечный цикл с фоновой загрузкой
- [x] Создать `install.bat` — установка зависимостей
- [x] Создать `run.bat` — запуск скрипта
- [x] Создать `autostart.bat` — Task Scheduler
- [x] Создать `src/shutdown_notify.py` — уведомление о выключении ПК
- [ ] Запустить `autostart.bat` от администратора на ПК
- [ ] Настройка BIOS: "Restore on AC Power Loss = Power On"

## Batch 4: Системный трей + баг-фиксы

### Баг-фиксы
- [ ] BUG-1: Telegram chat_id — пользователь обновляет в config.yaml на `-1003769841378`
- [x] BUG-2: main.py — последовательные загрузки (queue.Queue + upload_worker)
- [x] BUG-3: recorder.py — cleanup_old_recordings(skip_files) + PermissionError catch
- [x] BUG-4: main.py — wait_for_free_network один раз в upload_worker, не в каждом потоке
- [x] main.py — wait_for_internet() блокирует загрузку до появления сети
- [x] main.py — stop_event для корректного завершения из трея

### Системный трей
- [x] Создать `src/tray.py` — pystray + Pillow, иконка камеры, меню: Логи/Выход
- [x] Обновить `requirements.txt` — pystray, Pillow
- [x] Обновить `run.bat` — `pythonw src\tray.py` (без CMD-окна)
- [x] autostart.bat — без изменений (уже вызывает run.bat)
- [ ] Деплой + проверка пользователем
- [ ] Коммит в git

## Оптимизация
- [ ] Переключить на субпоток камеры (~100 МБ/час вместо 612 МБ)

## Баги исправлены
- [x] install.bat: `pip` → `python -m pip`
- [x] install.bat: добавлен `cd /d %~dp0`
- [x] main.py: создание директории recordings перед disk_usage
- [x] recorder.py: переход с FFmpeg на VLC (камера с нестандартным RTSP)
- [x] uploader.py: правильный Kinescope API v2 (Bearer auth, raw binary)
- [x] notifier.py: plain text для ошибок (трейсбеки ломали HTML парсер)
- [x] main.py: фоновая загрузка через threading (без пробелов между записями)
- [x] config.yaml: убран из git (содержит ключи API)
