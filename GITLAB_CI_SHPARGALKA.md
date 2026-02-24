# Шпаргалка по `.gitlab-ci.yml`

Ниже разбор текущего CI-файла из проекта: что делает каждый блок, зачем он нужен и что проверяется в каждой задаче.

## 1) `image: python:3.11`

```yaml
image: python:3.11
```

Что это:
- базовый Docker-образ для job-ов.

Зачем:
- гарантирует одинаковую версию Python в CI.
- убирает проблему "локально работает, в раннере нет".

Важно:
- если раннер с `executor = shell`, эта строка обычно игнорируется (job идет в окружении хоста).

## 2) `stages`

```yaml
stages:
  - build
  - lint
  - functional
```

Что это:
- порядок этапов пайплайна.

Зачем:
- сначала проверяем, что код собирается (`build`),
- затем стиль/синтаксис (`lint`),
- потом функциональные проверки (`functional`).

## 3) `workflow.rules`

```yaml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

Что это:
- правила, когда вообще запускать пайплайн.

Зачем:
- запуск только на:
- `push` (коммит в ветку),
- `merge_request_event` (обновления MR).

Итог:
- случайные типы запусков не создают лишние пайплайны.

## 4) `variables`

```yaml
variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  PYTHONUNBUFFERED: "1"
  PIP_DISABLE_PIP_VERSION_CHECK: "1"
```

Что это:
- переменные окружения для всех job.

Зачем:
- `PIP_CACHE_DIR`: кэш скачанных пакетов `pip` в папке проекта.
- `PYTHONUNBUFFERED=1`: сразу писать логи в консоль, без буферизации.
- `PIP_DISABLE_PIP_VERSION_CHECK=1`: не тратить время на проверку новой версии pip.

## 5) `cache`

```yaml
cache:
  key: "pip-cache"
  paths:
    - .cache/pip
```

Что это:
- кэш между запусками.

Зачем:
- ускоряет повторные пайплайны: зависимости не скачиваются с нуля каждый раз.

## 6) `before_script`

```yaml
before_script:
  - python --version
  - python -m pip install --upgrade pip
  - if [ -f requirements.txt ]; then pip install -r requirements.txt; else pip install "django>=5.2,<5.3"; fi
  - pip install "flake8>=7,<8" "pip-audit>=2,<3"
```

Что это:
- общие команды перед каждым job.

Зачем по шагам:
- показать версию Python в логе (удобно для отладки),
- обновить pip,
- установить зависимости проекта из `requirements.txt` (или fallback на Django),
- установить инструменты проверки:
- `flake8` (линтер),
- `pip-audit` (аудит уязвимостей в зависимостях).

## 7) Job `build_project`

```yaml
build_project:
  stage: build
  script:
    - mkdir -p artifacts/build
    - python -m compileall -q manage.py hrm core admin_portal hr_portal > artifacts/build/compileall.log 2>&1
```

Что делает:
- компилирует Python-файлы в байткод.

Зачем:
- быстрая проверка, что код без критичных синтаксических проблем.

Артефакты:

```yaml
artifacts:
  when: always
  expire_in: 1 week
  paths:
    - artifacts/build/
```

Почему так:
- лог сохраняется даже при падении job (`when: always`),
- хранится 1 неделю.

## 8) Job `lint_python`

```yaml
lint_python:
  stage: lint
  allow_failure: true
  script:
    - mkdir -p artifacts/lint
    - flake8 . --exclude=.venv,__pycache__,migrations > artifacts/lint/flake8.log || true
```

Что делает:
- запускает `flake8` по проекту.

Почему исключены каталоги:
- `.venv`: внешнее окружение, не код проекта.
- `__pycache__`: служебные файлы Python.
- `migrations`: автогенерируемые файлы, обычно не линтят строго.

Почему `allow_failure: true` и `|| true`:
- линтер не валит весь пайплайн, а дает отчет.
- удобно для учебного проекта: видно замечания, но сборка не блокируется.

## 9) Job `functional_django_checks`

```yaml
functional_django_checks:
  stage: functional
  script:
    - mkdir -p artifacts/functional
    - python manage.py check > artifacts/functional/django-check.log
    - python manage.py makemigrations --check --dry-run > artifacts/functional/migrations-check.log
```

Что делает:
- `manage.py check`: проверка конфигурации Django (настройки, приложения, модели и т.д.).
- `makemigrations --check --dry-run`: проверяет, что нет "забытых" миграций.

Зачем:
- это функциональная проверка целостности проекта перед тестами/деплоем.

## 10) Job `functional_tests`

```yaml
functional_tests:
  stage: functional
  script:
    - mkdir -p artifacts/tests
    - python manage.py test -v 2 > artifacts/tests/tests.log
```

Что делает:
- запускает тесты Django.

Зачем:
- проверка поведения приложения (не только синтаксис/стиль).

`-v 2`:
- более подробный лог тестов.

## 11) Job `security_dependencies_audit`

```yaml
security_dependencies_audit:
  stage: functional
  allow_failure: true
  script:
    - mkdir -p artifacts/security
    - |
      if [ -f requirements.txt ]; then
        pip-audit -r requirements.txt > artifacts/security/pip-audit.log || true
      else
        echo "requirements.txt not found, skipping pip-audit" > artifacts/security/pip-audit.log
      fi
```

Что делает:
- проверяет зависимости на известные уязвимости через `pip-audit`.

Почему `allow_failure: true`:
- аудит полезен как отчет, но не должен блокировать весь pipeline.

Поведение:
- если есть `requirements.txt`, идет реальная проверка,
- если нет, пишется понятный лог о пропуске.

## 12) Зачем везде `artifacts`

Во всех job используется:

```yaml
artifacts:
  when: always
  expire_in: 1 week
  paths:
    - artifacts/...
```

Смысл:
- сохранять логи и отчеты после каждой задачи,
- даже при ошибках иметь доказательства для преподавателя: что именно выполнялось и какой результат.

## 13) Коротко: логика всего пайплайна

Пайплайн проверяет проект слоями:
- `build`: "код вообще собирается?"
- `lint`: "есть ли проблемы стиля/синтаксиса?"
- `functional`: "Django настроен корректно, миграции не забыты, тесты проходят, зависимости безопасны?"

Это хорошая практичная схема для Django-курсового проекта: понятная, проверяемая и с отчетами в артефактах.
