-- Инициализация БД для Ukraine проекта
-- Создание таблиц для lexus_db

-- Таблица accounts
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20),
    session_name VARCHAR(255) UNIQUE NOT NULL,
    string_session TEXT,
    api_id INTEGER,
    api_hash VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    daily_posts_count INTEGER DEFAULT 0,
    last_stats_reset TIMESTAMP,
    next_allowed_action_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица targets (группы)
CREATE TABLE IF NOT EXISTS targets (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT,
    link VARCHAR(500),
    username VARCHAR(255),
    title VARCHAR(500),
    niche VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    assigned_account_id INTEGER REFERENCES accounts(id),
    joined_at TIMESTAMP,
    warmup_ends_at TIMESTAMP,
    last_post_at TIMESTAMP,
    daily_posts_in_group INTEGER DEFAULT 0,
    last_group_stats_reset TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица post_history (история постов)
CREATE TABLE IF NOT EXISTS post_history (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id),
    target_id INTEGER REFERENCES targets(id),
    message_content TEXT,
    photo_path VARCHAR(500),
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для оптимизации
CREATE INDEX IF NOT EXISTS idx_targets_status_niche ON targets(status, niche);
CREATE INDEX IF NOT EXISTS idx_targets_assigned_account ON targets(assigned_account_id);
CREATE INDEX IF NOT EXISTS idx_post_history_account_date ON post_history(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_post_history_target_date ON post_history(target_id, created_at);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_next_action ON accounts(next_allowed_action_time);
