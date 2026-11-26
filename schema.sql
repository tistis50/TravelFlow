PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS trips (
  id INTEGER PRIMARY KEY,
  route TEXT NOT NULL,
  purpose TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER NOT NULL REFERENCES trips(id),
  category TEXT NOT NULL CHECK(category IN ('Билеты','Проживание','Суточные','Прочее')),
  amount_cents INTEGER NOT NULL CHECK(amount_cents BETWEEN 1 AND 100000000),
  expense_date TEXT NOT NULL,
  note TEXT NOT NULL CHECK(length(note)<=200)
);
CREATE INDEX IF NOT EXISTS ix_expenses_trip ON expenses(trip_id);
INSERT OR IGNORE INTO trips VALUES
 (2,'Уфа — Сочи','Монтаж оборудования на объекте'),
 (11,'Уфа — Пермь','Сервисное обслуживание оборудования'),
 (12,'Уфа — Москва','Конференция дизайнеров');
