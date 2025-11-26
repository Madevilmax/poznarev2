PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- 1. Группы задач (общие параметры: текст, дедлайн, чат)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_groups (
    group_task_id INTEGER PRIMARY KEY,
    task_text     TEXT NOT NULL,
    deadline      TEXT NOT NULL,      -- формат: "dd.MM.yyyy" или "dd.MM.yyyy HH:MM:SS"
    group_id      TEXT NOT NULL,      -- ID чата/группы в Telegram (строка)
    created_at    TEXT NOT NULL       -- "dd.MM.yyyy HH:MM:SS"
);

------------------------------------------------------------
-- 2. Индивидуальные задачи по исполнителям
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_task_id INTEGER NOT NULL,
    assigned_to   TEXT NOT NULL,      -- "@username" исполнителя
    assigned_by   TEXT NOT NULL,      -- "@username" назначившего
    status        TEXT NOT NULL,      -- "active" / "completed"
    created_at    TEXT NOT NULL,      -- "dd.MM.yyyy HH:MM:SS"
    completed_at  TEXT NOT NULL,      -- "" или "dd.MM.yyyy HH:MM:SS"
    FOREIGN KEY (group_task_id) REFERENCES task_groups (group_task_id)
        ON DELETE CASCADE
);

-- Полезные индексы для быстрого доступа
CREATE INDEX IF NOT EXISTS idx_tasks_group_task_id
    ON tasks (group_task_id);

CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to
    ON tasks (assigned_to);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks (status);


------------------------------------------------------------
-- 3. Пользователи (для веб-админки и бота)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    username  TEXT PRIMARY KEY,   -- "@username" (ключ)
    full_name TEXT                -- "Имя Фамилия"
);

------------------------------------------------------------
-- 4. Группы / чаты для уведомлений
--    Здесь храним «группы» из UI (радио-кнопки),
--    обычно это chat_id Telegram (как строка).
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS groups (
    id   TEXT PRIMARY KEY,   -- chat_id или логический ключ группы
    name TEXT NOT NULL       -- человекочитаемое название
);

------------------------------------------------------------
-- 5. Связь пользователь ↔ группа (многие-ко-многим)
--    Заполняется из поля "Группы (через запятую)" в вебе.
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_groups (
    username TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (username, group_id),
    FOREIGN KEY (username) REFERENCES users (username)
        ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_groups_username
    ON user_groups (username);

CREATE INDEX IF NOT EXISTS idx_user_groups_group_id
    ON user_groups (group_id);


------------------------------------------------------------
-- 6. Конфигурация / настройки уведомлений
--    Сохраняем ключ-значение, значения как TEXT ("true"/"false").
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Базовые значения для уведомлений (idempotent)
INSERT OR IGNORE INTO config (key, value) VALUES
    ('task_created',      'true'),
    ('task_completed',    'true'),
    ('task_deleted',      'true'),
    ('overdue_reminder',  'true');

------------------------------------------------------------
-- 7. (опционально) Админы бота
--    Если хочется увести админов из JSON в БД.
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admins (
    username TEXT PRIMARY KEY  -- "@username" админа
);
