"""Предварительная проверка HTTP и SQLite. Запуск: python test_module.py.
Необходимы requests и beautifulsoup4; для снимков --capture нужен playwright и Chromium.
Тестовая БД изолирована от рабочей. Снимки — автономный рендер фактических HTTP-ответов.
"""
import argparse, sys, tempfile, subprocess, time, sqlite3, shutil
from pathlib import Path
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(); p.add_argument('--capture',type=Path); p.add_argument('--chromium',default='/usr/bin/chromium'); p.add_argument('--port',type=int,default=8765); args=p.parse_args()
base=f'http://127.0.0.1:{args.port}'; results=[]
if args.capture: args.capture.mkdir(parents=True,exist_ok=True)
css=(ROOT/'module.css').read_text(encoding='utf-8')
play=browser=page=None
if args.capture:
    from playwright.sync_api import sync_playwright
    play=sync_playwright().start(); browser=play.chromium.launch(executable_path=args.chromium,args=['--no-sandbox']); page=browser.new_page(viewport={'width':1280,'height':960}); page.route('**/*',lambda r:r.abort())
def check(name,condition):
    assert condition,name
    results.append(name+' — успешно'); print(results[-1],flush=True)
def soup(r): return BeautifulSoup(r.text,'html.parser')
def get(path='/expenses'): return client.get(base+path,timeout=5)
def post(path,data): return client.post(base+path,data=data,timeout=5)
def csrf(r): return soup(r).select_one('input[name=csrf]')['value']
def val(r,id): return soup(r).select_one('#'+id).get_text(strip=True)
def shot(name,r,mobile=False):
    if not page: return
    page.set_viewport_size({'width':390,'height':844} if mobile else {'width':1280,'height':960})
    html=r.text.replace('<link rel="stylesheet" href="/module.css">','<style>'+css+'</style>')
    page.set_content(html,wait_until='domcontentloaded'); page.screenshot(path=args.capture/(name+'.png'),full_page=mobile)
    if mobile: check('Автономный мобильный рендер: ширина страницы 390 px',page.evaluate('document.documentElement.scrollWidth===innerWidth'))
def add(r,trip,cat,amount,note,id=''):
    return post('/save',{'csrf':csrf(r),'trip_id':trip,'category':cat,'amount':amount,'expense_date':'2026-11-20','note':note,'id':id})
with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'test.sqlite3'; srv=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'--port',str(args.port),'--db',str(db)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); client=requests.Session()
    try:
        for _ in range(40):
            try: home=get('/'); break
            except requests.ConnectionError: time.sleep(.1)
        else: raise RuntimeError('Сервер не запустился')
        check('Главная страница содержит ссылку на модуль',home.status_code==200 and 'href="/expenses"' in home.text)
        r=get(); check('Без сессии отображается вход', 'Вход в журнал' in r.text); shot('03_login',r)
        r=post('/login',{'username':'accountant','password':'wrong'}); check('Неверный пароль отклонён (401)',r.status_code==401)
        r=post('/login',{'username':'accountant','password':'accountant-demo'}); check('Вход бухгалтера',r.status_code==200 and 'Бухгалтер' in r.text)
        r=add(r,'2','Билеты','12500,50','Билет до Сочи'); check('Добавление расхода 12 500,50',val(r,'count')=='1' and val(r,'total')=='12 500,50 ₽'); shot('04_add',r)
        r=add(r,'11','Проживание','7800','Гостиница в Перми'); check('Две записи, итог 20 300,50',val(r,'count')=='2' and val(r,'total')=='20 300,50 ₽'); shot('05_registry',r)
        r=get('/expenses?edit=2'); check('Получение существующей записи для изменения',soup(r).select_one('[name=amount]')['value']=='7800.00'); shot('06_edit',r)
        r=add(r,'11','Проживание','8000','Гостиница в Перми','2'); check('Изменение без дублирования: 20 500,50',val(r,'count')=='2' and val(r,'total')=='20 500,50 ₽'); r=get(); check('Повторное получение сохранённых записей',val(r,'total')=='20 500,50 ₽'); shot('07_updated',r)
        filtered=get('/expenses?trip=2'); check('Фильтр: только расход поездки № 2',len(soup(filtered).select('tbody tr'))==1 and 'Билет до Сочи' in soup(filtered).select_one('tbody').text); shot('08_filter',filtered)
        invalid=add(r,'2','Билеты','-50','Некорректная сумма'); check('Отрицательная сумма отклонена (400), записи неизменны',invalid.status_code==400 and val(invalid,'count')=='2'); shot('09_invalid',invalid)
        for trip,cat,amount,note in [('999','Билеты','5',''),('2','неизвестно','5',''),('2','Билеты','0',''),('2','Билеты','1000000.01',''),('2','Билеты','1.001',''),('2','Билеты','10','x'*201)]:
            bad=add(r,trip,cat,amount,note); assert bad.status_code==400 and val(bad,'count')=='2'
        check('Шесть дополнительных некорректных вводов отклонены',True)
        check('Бухгалтер не видит кнопку удаления',not soup(r).find('a',string='Удалить')); shot('10_accountant',r)
        res=post('/delete',{'csrf':csrf(r),'id':'1'}); check('Прямой POST удаления бухгалтером запрещён (403)',res.status_code==403 and val(res,'count')=='2')
        res=post('/save',{'trip_id':'2'}); check('Запрос без CSRF запрещён (403)',res.status_code==403)
        r=add(r,'2','Прочее','10','<script>alert(1)</script>'); check('HTML в комментарии экранирован в ответе', '&lt;script&gt;alert(1)&lt;/script&gt;' in r.text and not soup(r).find('script')); shot('11_xss',r)
        r=post('/logout',{'csrf':csrf(r)}); check('Выход возвращает к входу','Вход в журнал' in r.text)
        res=post('/save',{'trip_id':'2'}); check('Запрос без сессии отклонён (401)',res.status_code==401)
        r=post('/login',{'username':'admin','password':'admin-demo'}); check('Администратор видит три действия удаления',len(soup(r).find_all('a',string='Удалить'))==3); shot('12_admin',r)
        confirm=get('/expenses?confirm=3'); check('Перед удалением требуется подтверждение','Подтвердить удаление' in confirm.text); shot('13_confirm',confirm)
        r=post('/delete',{'csrf':csrf(confirm),'id':'3'}); check('Подтверждённое удаление: осталось две записи',val(r,'count')=='2' and val(r,'total')=='20 500,50 ₽'); shot('14_final',r); shot('15_mobile',r,True)
        check('Обратная ссылка в раздел командировок присутствует',soup(r).find('a',href='/#trips') is not None)
        with sqlite3.connect(db) as c:
            rows=c.execute('SELECT id,trip_id,category,amount_cents,expense_date,note FROM expenses ORDER BY id').fetchall(); check('SQLite: две строки, сумма 2050050 копеек',len(rows)==2 and sum(x[3] for x in rows)==2050050); check('SQLite: integrity_check = ok',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
        srv.terminate(); srv.wait(); srv=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'--port',str(args.port),'--db',str(db)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(.5); r=post('/login',{'username':'admin','password':'admin-demo'}); check('Данные сохранены после перезапуска сервера',val(r,'count')=='2' and val(r,'total')=='20 500,50 ₽')
        if args.capture:
            (args.capture/'test_results.txt').write_text('\n'.join(results)+'\n',encoding='utf-8'); shutil.copy2(db,args.capture/'tested.sqlite3')
    finally:
        srv.terminate(); srv.wait()
        if browser: browser.close(); play.stop()
