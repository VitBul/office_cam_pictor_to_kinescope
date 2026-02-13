# CamKinescope — Task Tracker

## Batch 1: Ядро — захват видео
- [x] Создать `config.yaml` с конфигурацией
- [x] Создать `src/logger_setup.py` — структурированное логирование
- [x] Создать `src/recorder.py` — захват RTSP через FFmpeg
- [x] Создать `requirements.txt`
- [x] Тест: запись запущена, Telegram уведомление получено ✅

## Batch 2: Загрузка + уведомления
- [x] Создать `src/uploader.py` — загрузка в Kinescope API
- [x] Создать `src/notifier.py` — Telegram уведомления
- [x] Тест: Telegram уведомления работают ✅
- [ ] Тест: загрузка в Kinescope (ожидает завершения записи)

## Batch 3: Оркестратор + автозапуск
- [x] Создать `src/main.py` — бесконечный цикл
- [x] Создать `install.bat` — установка зависимостей
- [x] Создать `run.bat` — запуск скрипта
- [x] Создать `autostart.bat` — Task Scheduler (автозапуск + уведомление о выключении)
- [x] Создать `src/shutdown_notify.py` — уведомление в Telegram при выключении ПК
- [ ] Тест: полный цикл запись → загрузка → уведомление
- [ ] Тест: автозапуск и уведомление о выключении
- [ ] Настройка BIOS: "Restore on AC Power Loss = Power On"

## Баги исправлены
- [x] install.bat: `pip` → `python -m pip`
- [x] install.bat: добавлен `cd /d %~dp0`
- [x] main.py: создание директории recordings перед disk_usage
- [x] recorder.py: добавлен wall-clock timeout (duration + 5мин), RTSP таймауты, обработка частичных файлов
