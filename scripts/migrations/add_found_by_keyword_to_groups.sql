-- Добавление колонки found_by_keyword в groups (ключевое слово поиска: Thailand expat, Dubai и т.д.)
-- Выполнено: 2026-02
ALTER TABLE groups ADD COLUMN IF NOT EXISTS found_by_keyword VARCHAR(255);
CREATE INDEX IF NOT EXISTS ix_groups_found_by_keyword ON groups (found_by_keyword);
