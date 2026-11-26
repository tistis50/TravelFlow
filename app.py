"""Локальный сервер TravelFlow. Python 3.10+, стандартная библиотека."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, urlencode
from http.cookies import SimpleCookie
from pathlib import Path
from html import escape
from datetime import date
import argparse, secrets, hmac, time, os
import storage as s
ROOT=Path(__file__).resolve().parent
DB=ROOT/'travelflow.sqlite3'
USERS={'accountant':('accountant-demo','Бухгалтер'),'admin':('admin-demo','Администратор')}
SESSIONS={}
def h(v): return escape(str(v),quote=True)
def money(c): return f'{c/100:,.2f}'.replace(',',' ').replace('.',',')+' ₽'
def page(body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>TravelFlow — журнал расходов</title><link rel="stylesheet" href="/module.css"><body>'+body+'</body></html>'
def notice(msg,err=False): return f'<div role="alert" class="msg {"error" if err else ""}">{h(msg)}</div>' if msg else ''
def token(session): return f'<input type="hidden" name="csrf" value="{h(session[1])}">'
def login(msg=''):
    return page(f'<div class="login"><a class="logo" href="/">✈ TravelFlow</a><div class="card"><h1>Вход в журнал</h1><p class="sub">Учёт фактических расходов</p>{notice(msg,True)}<form method="post" action="/login"><label>Логин<input name="username" autocomplete="username" required></label><label>Пароль<input name="password" type="password" autocomplete="current-password" required></label><button>Войти</button></form><p class="hint">Учебный режим. Бухгалтер или администратор.</p><a href="/">Вернуться на главную</a></div></div>')
def journal(session, form=None, edit=None, q='', msg='', err=False):
    with s.connect(DB) as db:
        trips=db.execute('SELECT * FROM trips ORDER BY id').fetchall()
        records=s.rows(db,q)
        all_count,total=db.execute('SELECT count(*),coalesce(sum(amount_cents),0) FROM expenses').fetchone()
    admin=session[0]=='admin'; role=USERS[session[0]][1]; form=form or {}
    def opts(selected):
        return ''.join(f'<option value="{r["id"]}" {"selected" if str(r["id"])==str(selected) else ""}>№ {r["id"]} · {h(r["route"])}</option>' for r in trips)
    cats=''.join(f'<option {"selected" if c==form.get("category") else ""}>{c}</option>' for c in s.CATEGORIES)
    csrf=token(session)
    data=''
    for r in records:
        rid=r['id']; delete=f'<a class="btn danger" href="/expenses?confirm={rid}">Удалить</a>' if admin else ''
        data+=f'<tr><td>{rid}</td><td>№ {r["trip_id"]} · {h(r["route"])}</td><td>{h(r["category"])}</td><td>{money(r["amount_cents"])}</td><td>{h(r["expense_date"])}</td><td>{h(r["note"])}</td><td><div class="actions"><a class="btn ghost" href="/expenses?edit={rid}">Изменить</a>{delete}</div></td></tr>'
    # Контролируемый дефект: для пустой выборки используется общий текст.
    if not data: data='<tr><td colspan="7" class="empty">Записей пока нет</td></tr>'
    nav='<a href="/#home">Главная</a><a href="/#trips">Командировки</a><a href="/#employees">Сотрудники</a><a class="active" href="/expenses">Журнал расходов</a><a href="/#reports">Отчёты</a><a href="/#config">Настройки</a>'
    return page(f'''<div class="app"><aside class="sidebar"><a href="/" class="logo">✈ TravelFlow</a><nav>{nav}</nav></aside><main class="main"><div class="head"><h1>Журнал расходов</h1><div class="logout"><span class="badge">{role}</span><form method="post" action="/logout">{csrf}<button class="ghost">Выйти</button></form></div></div><p class="sub">Фактические расходы по командировкам · SQLite</p>{notice(msg,err)}<div class="stats"><div class="stat">Всего записей<strong id="count">{all_count}</strong></div><div class="stat">Общая сумма<strong id="total">{money(total)}</strong></div></div><br><section class="card"><h2>{'Редактирование записи № '+h(edit) if edit else 'Новый расход'}</h2><form method="post" action="/save" novalidate>{csrf}<input type="hidden" name="id" value="{h(edit or '')}"><div class="formgrid"><label>Командировка<select name="trip_id"><option value="">Выберите поездку</option>{opts(form.get('trip_id',''))}</select></label><label>Категория<select name="category"><option value="">Выберите категорию</option>{cats}</select></label><label>Сумма, ₽<input name="amount" inputmode="decimal" placeholder="0,00" value="{h(form.get('amount',''))}"></label><label>Дата расхода<input name="expense_date" type="date" value="{h(form.get('expense_date',date.today().isoformat()))}"></label><label class="wide">Комментарий (до 200 символов)<input name="note" maxlength="200" value="{h(form.get('note',''))}" placeholder="Например, билет или чек"></label></div><div class="actions"><button>{'Сохранить изменения' if edit else 'Добавить расход'}</button>{'<a class="btn ghost" href="/expenses">Отмена</a>' if edit else ''}</div></form></section><section class="card"><h2>Реестр расходов</h2><form class="filter" method="get" action="/expenses"><label>Фильтр по командировке<select name="trip"><option value="">Все командировки</option>{opts(q)}</select></label><button>Показать</button><a class="btn ghost" href="/expenses">Сбросить</a></form><div class="tablewrap"><table><thead><tr><th>№</th><th>Командировка</th><th>Категория</th><th>Сумма</th><th>Дата</th><th>Комментарий</th><th>Действия</th></tr></thead><tbody>{data}</tbody></table></div><p class="hint">Показано: {len(records)} из {all_count}. Справочник содержит три демонстрационные поездки исходного проекта.</p></section></main></div>''')
class Handler(BaseHTTPRequestHandler):
    def send(self, body, status=200, typ='text/html; charset=utf-8', cookie=None):
        b=body.encode('utf-8') if isinstance(body,str) else body
        self.send_response(status); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(b)
    def redirect(self,path,cookie=None):
        self.send_response(303); self.send_header('Location',path); self.send_header('Content-Length','0')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
    def session(self):
        c=SimpleCookie(); c.load(self.headers.get('Cookie','')); sid=c['tf_sid'].value if 'tf_sid' in c else ''
        session=SESSIONS.get(sid)
        if session and session[2]>time.time(): return sid,session
        SESSIONS.pop(sid,None); return '',None
    def do_GET(self):
        url=urlsplit(self.path); q={k:v[0] for k,v in parse_qs(url.query).items()}; path=url.path
        if path=='/': return self.send((ROOT/'index.html').read_bytes())
        if path=='/module.css': return self.send((ROOT/'module.css').read_bytes(),typ='text/css; charset=utf-8')
        if path!='/expenses': return self.send(page('Страница не найдена'),404)
        _,sess=self.session()
        if not sess: return self.send(login())
        if 'confirm' in q:
            if sess[0]!='admin': return self.send(journal(sess,msg='Удаление доступно только администратору.',err=True),403)
            with s.connect(DB) as db: row=db.execute('SELECT id FROM expenses WHERE id=?',(q['confirm'],)).fetchone()
            if not row: return self.send(journal(sess,msg='Запись не найдена.',err=True),404)
            return self.send(page(f'<div class="login"><div class="card"><h2>Удалить расход № {row[0]}?</h2><p>Действие нельзя отменить.</p><form method="post" action="/delete">{token(sess)}<input type="hidden" name="id" value="{row[0]}"><div class="actions"><button class="danger">Подтвердить удаление</button><a class="btn ghost" href="/expenses">Отмена</a></div></form></div></div>'))
        if 'edit' in q:
            with s.connect(DB) as db: r=db.execute('SELECT * FROM expenses WHERE id=?',(q['edit'],)).fetchone()
            if not r: return self.send(journal(sess,msg='Запись не найдена.',err=True),404)
            f=dict(r); f['amount']=f'{r["amount_cents"]/100:.2f}'; return self.send(journal(sess,f,r['id']))
        messages={'added':'Расход добавлен.','deleted':'Расход удалён.'}
        return self.send(journal(sess,q=q.get('trip',''),msg=messages.get(q.get('msg'),'')))
    def do_POST(self):
        try: n=int(self.headers.get('Content-Length','0'))
        except ValueError: return self.send('Bad request',400)
        if n<0 or n>8192: return self.send('Request too large',413)
        try: f={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode('utf-8'),keep_blank_values=True,max_num_fields=20).items()}
        except (UnicodeError,ValueError): return self.send('Bad request',400)
        path=urlsplit(self.path).path; sid,sess=self.session()
        if path=='/login':
            user=f.get('username',''); pw=f.get('password','')
            if user not in USERS or not hmac.compare_digest(pw.encode(),USERS[user][0].encode()): return self.send(login('Неверный логин или пароль.'),401)
            SESSIONS.pop(sid,None); sid=secrets.token_urlsafe(32); SESSIONS[sid]=(user,secrets.token_urlsafe(32),time.time()+3600)
            return self.redirect('/expenses',f'tf_sid={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=3600')
        if not sess: return self.send(login('Войдите в систему.'),401)
        if not hmac.compare_digest(f.get('csrf','').encode(),sess[1].encode()): return self.send(journal(sess,msg='Недопустимый запрос.',err=True),403)
        if path=='/logout': SESSIONS.pop(sid,None); return self.redirect('/expenses','tf_sid=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
        if path=='/delete':
            if sess[0]!='admin': return self.send(journal(sess,msg='Удаление доступно только администратору.',err=True),403)
            with s.connect(DB) as db: count=s.delete(db,f.get('id',''))
            if not count: return self.send(journal(sess,msg='Запись не найдена.',err=True),404)
            return self.redirect('/expenses?msg=deleted')
        if path=='/save':
            edit=f.get('id','')
            try:
                with s.connect(DB) as db:
                    values=s.validate(f,db)
                    if edit:
                        if not s.update(db,edit,values): raise ValueError('Запись не найдена.')
                    else: s.create(db,values)
            except ValueError as e: return self.send(journal(sess,f,edit,msg=str(e),err=True),400)
            # Контролируемый дефект: после изменения надпись как при добавлении.
            return self.redirect('/expenses?msg=added')
        return self.send('Not found',404)
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8000); p.add_argument('--db',type=Path,default=DB); a=p.parse_args(); DB=a.db; s.init(DB)
    print(f'TravelFlow: http://127.0.0.1:{a.port}',flush=True); ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
