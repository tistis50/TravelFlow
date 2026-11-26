"""Хранилище учебного журнала расходов."""
import sqlite3
from pathlib import Path
from datetime import date
import re
from contextlib import contextmanager
ROOT = Path(__file__).resolve().parent
CATEGORIES = ('Билеты','Проживание','Суточные','Прочее')
@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()
def init(path):
    with connect(path) as db:
        db.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
def validate(form, db):
    try:
        trip = int(form.get('trip_id',''))
    except ValueError:
        raise ValueError('Выберите командировку.')
    if not db.execute('SELECT 1 FROM trips WHERE id=?',(trip,)).fetchone():
        raise ValueError('Командировка не найдена.')
    category = form.get('category','')
    if category not in CATEGORIES:
        raise ValueError('Выберите категорию.')
    raw = form.get('amount','').strip().replace(',','.')
    if not re.fullmatch(r'\d{1,7}(\.\d{1,2})?',raw):
        raise ValueError('Введите положительную сумму с точностью до копеек.')
    rub, _, kop = raw.partition('.')
    cents = int(rub)*100+int(kop.ljust(2,'0') or '0')
    if not 1 <= cents <= 100000000:
        raise ValueError('Сумма должна быть от 0,01 до 1 000 000 ₽.')
    day = form.get('expense_date','')
    try:
        if date.fromisoformat(day).isoformat() != day: raise ValueError()
    except ValueError:
        raise ValueError('Укажите корректную дату.')
    note = form.get('note','').strip()
    if len(note)>200: raise ValueError('Комментарий: не более 200 символов.')
    return trip, category, cents, day, note

def create(db, values):
    return db.execute('INSERT INTO expenses(trip_id,category,amount_cents,expense_date,note) VALUES(?,?,?,?,?)',values).lastrowid

def update(db, id, values):
    return db.execute('UPDATE expenses SET trip_id=?,category=?,amount_cents=?,expense_date=?,note=? WHERE id=?',(*values,id)).rowcount

def delete(db, id):
    return db.execute('DELETE FROM expenses WHERE id=?',(id,)).rowcount

def rows(db, trip=''):
    sql = 'SELECT e.*,t.route FROM expenses e JOIN trips t ON e.trip_id=t.id'
    return db.execute(sql+(' WHERE e.trip_id=?' if trip else '')+' ORDER BY e.id DESC',(trip,) if trip else ()).fetchall()
