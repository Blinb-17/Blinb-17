# Student LMS Diary

Готовый веб-проект онлайн-дневника для студентов с двумя ролями:

- **Студент**: смотрит оценки, посещаемость, заметки преподавателей и расписание.
- **Админ**: регистрируется через защищённый ключ, управляет студентами, предметами и оценками.

## Технологии

- Python 3.11+
- Flask
- SQLite (встроенная БД, файл `lms_diary.db`)
- Jinja2 + CSS

## Запуск

1. Создать и активировать виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
```

2. Установить зависимости:

```bash
pip install -r requirements.txt
```

3. Настроить переменные окружения (рекомендуется):

```bash
export SECRET_KEY="replace-with-strong-secret"
export ADMIN_REGISTRATION_KEY="replace-admin-key"
```

4. Инициализировать БД:

```bash
python manage.py init-db
```

5. (Опционально) создать демо-данные:

```bash
python manage.py seed
```

6. Запустить приложение:

```bash
python manage.py run
```

Открыть: `http://127.0.0.1:5000`

## Демо-аккаунты после `seed`

- Админ: `admin@campus.local` / `AdminPass123!`
- Студент: `student@campus.local` / `StudentPass123!`

## Основные URL

- `/register/student` — регистрация студента
- `/register/admin` — регистрация админа (нужен admin key)
- `/login` — вход
- `/student/dashboard` — кабинет студента
- `/admin/dashboard` — админ панель

## Безопасность

- Пароли хранятся в виде хэша (`werkzeug.security`).
- Админ-регистрация защищена ключом `ADMIN_REGISTRATION_KEY`.
- Проверка доступа по ролям для всех защищённых маршрутов.
