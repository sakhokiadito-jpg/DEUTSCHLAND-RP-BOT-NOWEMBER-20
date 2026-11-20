"""CPM RP Expansion 2.0 — безопасная песочница новых RP-систем.

Все команды этого модуля работают ТОЛЬКО с таблицами rp_demo_* и не меняют
боевой баланс, автомобили, бизнесы или недвижимость существующих игроков.
"""
from __future__ import annotations
import os, sqlite3, time, random, html
from contextlib import contextmanager
from typing import Optional
from aiogram import Router, F, types

router = Router(name="cpmrp_expansion")
DB_PATH = os.environ.get("CPMRP_DB_PATH", os.path.join(os.path.dirname(__file__), "bot.db"))
START_CASH = 50_000
START_BANK = 25_000

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS rp_demo_users(
 uid INTEGER PRIMARY KEY, name TEXT NOT NULL, cash INTEGER NOT NULL DEFAULT 50000,
 bank INTEGER NOT NULL DEFAULT 25000, debt INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_elections(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
 winner_uid INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_candidates(
 election_id INTEGER NOT NULL, uid INTEGER NOT NULL, slogan TEXT NOT NULL,
 PRIMARY KEY(election_id,uid));
CREATE TABLE IF NOT EXISTS rp_demo_votes(
 election_id INTEGER NOT NULL, voter_uid INTEGER NOT NULL, candidate_uid INTEGER NOT NULL,
 PRIMARY KEY(election_id,voter_uid));
CREATE TABLE IF NOT EXISTS rp_demo_economy(
 sector TEXT PRIMARY KEY, label TEXT NOT NULL, index_value REAL NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_calls(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, kind TEXT NOT NULL,
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', assigned_uid INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_medical(
 uid INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'healthy', condition_text TEXT NOT NULL DEFAULT 'Здоров', updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_families(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, owner_uid INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_family_members(
 family_id INTEGER NOT NULL, uid INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'member', PRIMARY KEY(family_id,uid));
CREATE TABLE IF NOT EXISTS rp_demo_marriages(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid1 INTEGER NOT NULL, uid2 INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL, UNIQUE(uid1,uid2));
CREATE TABLE IF NOT EXISTS rp_demo_wills(
 uid INTEGER PRIMARY KEY, heir_uid INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_deaths(
 uid INTEGER PRIMARY KEY, deceased_at INTEGER NOT NULL, claimed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rp_demo_seasons(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'active', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER NOT NULL, title TEXT NOT NULL,
 description TEXT NOT NULL, reward INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS rp_demo_event_members(
 event_id INTEGER NOT NULL, uid INTEGER NOT NULL, PRIMARY KEY(event_id,uid));
CREATE TABLE IF NOT EXISTS rp_demo_cars(
 id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, base_price INTEGER NOT NULL,
 owner_uid INTEGER, price_index REAL NOT NULL DEFAULT 1.0);
CREATE TABLE IF NOT EXISTS rp_demo_court_cases(
 id INTEGER PRIMARY KEY AUTOINCREMENT, plaintiff_uid INTEGER NOT NULL, defendant_uid INTEGER NOT NULL,
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', verdict TEXT, judge_uid INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_clubs(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, owner_uid INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_club_members(
 club_id INTEGER NOT NULL, uid INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'member', PRIMARY KEY(club_id,uid));
CREATE TABLE IF NOT EXISTS rp_demo_news(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL, author_uid INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rp_demo_tenders(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
 budget INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', winner_uid INTEGER, winning_bid INTEGER);
CREATE TABLE IF NOT EXISTS rp_demo_bids(
 tender_id INTEGER NOT NULL, uid INTEGER NOT NULL, amount INTEGER NOT NULL, created_at INTEGER NOT NULL,
 PRIMARY KEY(tender_id,uid));
CREATE TABLE IF NOT EXISTS rp_demo_properties(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, price INTEGER NOT NULL,
 owner_uid INTEGER, daily_rent INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rp_demo_rentals(
 id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER NOT NULL, tenant_uid INTEGER NOT NULL,
 paid_amount INTEGER NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS rp_demo_stocks(
 symbol TEXT PRIMARY KEY, title TEXT NOT NULL, price REAL NOT NULL, volatility REAL NOT NULL DEFAULT 0.05);
CREATE TABLE IF NOT EXISTS rp_demo_holdings(
 uid INTEGER NOT NULL, symbol TEXT NOT NULL, shares INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(uid,symbol));
CREATE TABLE IF NOT EXISTS rp_demo_achievements(
 uid INTEGER NOT NULL, code TEXT NOT NULL, title TEXT NOT NULL, reward INTEGER NOT NULL DEFAULT 0,
 unlocked_at INTEGER NOT NULL, PRIMARY KEY(uid,code));
CREATE TABLE IF NOT EXISTS rp_demo_audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, action TEXT NOT NULL,
 amount INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=20000")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    with _conn() as c:
        c.executescript(SCHEMA)
        now = int(time.time())
        c.execute("INSERT OR IGNORE INTO rp_demo_economy VALUES('auto','Автомобили',1.0,?)", (now,))
        c.execute("INSERT OR IGNORE INTO rp_demo_economy VALUES('realty','Недвижимость',1.0,?)", (now,))
        c.execute("INSERT OR IGNORE INTO rp_demo_economy VALUES('business','Бизнес',1.0,?)", (now,))
        for symbol, title, price, vol in [('AUTO','Автопром',1200,0.06),('BANK','Банк',850,0.03),('MEDIA','Медиа',500,0.08)]:
            c.execute("INSERT OR IGNORE INTO rp_demo_stocks VALUES(?,?,?,?)", (symbol,title,price,vol))
        if c.execute("SELECT COUNT(*) FROM rp_demo_cars").fetchone()[0] == 0:
            c.executemany("INSERT INTO rp_demo_cars(model,base_price,price_index) VALUES(?,?,1.0)", [
                ('Lada Priora', 18000), ('BMW E36', 32000), ('Mercedes W140', 48000),
                ('Nissan Skyline R34', 95000), ('Toyota Supra', 110000), ('BMW M5 E60', 125000)])
        if c.execute("SELECT COUNT(*) FROM rp_demo_properties").fetchone()[0] == 0:
            c.executemany("INSERT INTO rp_demo_properties(title,price,daily_rent) VALUES(?,?,?)", [
                ('Комната в общежитии',18000,250),('Квартира в центре',95000,1200),('Дом у трассы',180000,2200)])
        if c.execute("SELECT COUNT(*) FROM rp_demo_tenders").fetchone()[0] == 0:
            c.execute("INSERT INTO rp_demo_tenders(title,description,budget) VALUES(?,?,?)",
                      ('Ремонт городской дороги','Поставка материалов и ремонт участка',12000))
        if c.execute("SELECT COUNT(*) FROM rp_demo_seasons").fetchone()[0] == 0:
            c.execute("INSERT INTO rp_demo_seasons(name,description,status,created_at) VALUES(?,?,?,?)",
                      ('Новая эра города','Первый сезон: выборы, развитие бизнеса и городские события.','active',now))
            sid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute("INSERT INTO rp_demo_events(season_id,title,description,reward) VALUES(?,?,?,?)",
                      (sid,'День города','Прими участие в городском событии и получи награду.',1500))
        if c.execute("SELECT COUNT(*) FROM rp_demo_elections WHERE status='open'").fetchone()[0] == 0:
            c.execute("INSERT INTO rp_demo_elections(title,status,created_at) VALUES(?,?,?)",
                      ('Выборы президента CPM RP','open',now))


def _demo(uid):
    with _conn() as c:
        return c.execute("SELECT * FROM rp_demo_users WHERE uid=? AND active=1", (uid,)).fetchone()


def _ensure(uid, name):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO rp_demo_users(uid,name,cash,bank,debt,active,created_at) VALUES(?,?,?,?,0,1,?)",
                  (uid, name[:40], START_CASH, START_BANK, int(time.time())))
        c.execute("UPDATE rp_demo_users SET name=? WHERE uid=?", (name[:40],uid))
        c.execute("INSERT OR IGNORE INTO rp_demo_medical(uid,status,condition_text,updated_at) VALUES(?,?,?,?)",
                  (uid,'healthy','Здоров',int(time.time())))
        return c.execute("SELECT * FROM rp_demo_users WHERE uid=?", (uid,)).fetchone()


def _cash(uid, delta, action, details=''):
    if delta == 0: return True
    with _conn() as c:
        row = c.execute("SELECT cash FROM rp_demo_users WHERE uid=? AND active=1", (uid,)).fetchone()
        if not row or row['cash'] + delta < 0: return False
        c.execute("UPDATE rp_demo_users SET cash=cash+? WHERE uid=?", (int(delta),uid))
        c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",
                  (uid,action,int(delta),details[:300],int(time.time())))
        return True


def _fmt(n): return f"{int(n):,}".replace(',', ' ')
def _name(m): return m.from_user.username or m.from_user.full_name or str(m.from_user.id)
def _is_admin(uid):
    try:
        import config
        return uid in getattr(config,'ADMIN_IDS',[]) or uid in getattr(config,'ADMINS',[])
    except Exception: return False
async def _need_demo(m):
    if not _demo(m.from_user.id):
        await m.answer("Сначала включи безопасный режим: <code>/rp_demo</code>. Он не меняет твой настоящий игровой баланс.",parse_mode='HTML')
        return False
    return True

HELP = """<b>CPM RP — полный список команд</b>

<b>Основное</b>
команды — показать этот список
рп — меню систем
демо — включить тестовый режим
обычный режим — выключить тестовый режим

<b>Государство</b>
выборы — посмотреть выборы
кандидат ТЕКСТ — стать кандидатом
голос UID — проголосовать
парламент — посмотреть парламент
завершить выборы — завершить выборы (админ)
тендеры — список тендеров
заявка ID СУММА — подать заявку на тендер
выдать тендер ID UID — назначить победителя (админ)

<b>Экономика и транспорт</b>
экономика — состояние экономики
автоцены — цены всех машин
автоцена ID — цена одной машины
купить авто ID — купить машину
обновить рынок — обновить цены и акции (админ)
биржа — фондовый рынок
купить акции КОД КОЛИЧЕСТВО
продать акции КОД КОЛИЧЕСТВО

<b>Городские службы</b>
вызов СЛУЖБА ОПИСАНИЕ — вызвать полицию, скорую или пожарных
вызовы — список вызовов
принять вызов ID
закрыть вызов ID
медкарта — состояние здоровья
больница — госпитализация
выписка — выйти из больницы

<b>Семья и общество</b>
семья создать НАЗВАНИЕ
семья вступить ID
семья информация ID
брак UID — предложить брак
принять брак ID
завещание UID — назначить наследника
смерть — тестовая симуляция смерти
наследство — посмотреть наследство
получить наследство — забрать наследство
клуб создать НАЗВАНИЕ
клуб вступить ID
клуб информация ID

<b>Суды и финансы</b>
иск UID ОПИСАНИЕ — подать иск
суды — список дел
решение ID ТЕКСТ — решение суда (админ)
кредит СУММА — взять тестовый кредит
погасить СУММА — погасить долг
банкротство — подать на банкротство

<b>Новости и события</b>
сезон — текущий сезон
события — список событий
участвовать ID — принять участие
новости — новостная лента
опубликовать новость ЗАГОЛОВОК | ТЕКСТ — публикация (админ)
телевидение — эфир телеканала
достижения — список достижений

<b>Недвижимость</b>
недвижимость — каталог объектов
купить недвижимость ID
сдать недвижимость ID СУММА — цена аренды в день
арендовать ID ДНИ

<b>Важно</b>
Все новые функции пока работают в тестовом режиме и не меняют настоящий баланс CPM RP.
Для нескольких функций нужен второй игрок, а административные действия доступны только администраторам."""

@router.message(F.text)
async def expansion_commands(message: types.Message):
    text = (message.text or '').strip()
    if not text:
        return
    # Русские короткие команды без /, подчёркиваний и других спецсимволов.
    aliases = {
        'команды':'/rp_help', 'помощь':'/rp_help', 'рп':'/rp', 'демо':'/rp_demo',
        'обычный режим':'/rp_live', 'выборы':'/election', 'кандидат':'/candidate',
        'голос':'/vote', 'парламент':'/parliament', 'завершить выборы':'/election_close',
        'экономика':'/economy', 'автоцены':'/carprices', 'автоцена':'/carprice',
        'купить авто':'/carbuy', 'обновить рынок':'/market_refresh', 'биржа':'/stocks',
        'купить акции':'/stockbuy', 'продать акции':'/stocksell', 'вызов':'/call911',
        'вызовы':'/dispatch', 'принять вызов':'/takecall', 'закрыть вызов':'/closecall',
        'медкарта':'/medical', 'больница':'/hospitalize', 'выписка':'/discharge',
        'семья создать':'/family create', 'семья вступить':'/family join',
        'семья информация':'/family info', 'брак':'/marry', 'принять брак':'/marryaccept',
        'завещание':'/will', 'смерть':'/rp_death', 'наследство':'/inheritance',
        'получить наследство':'/inheritance_claim', 'иск':'/court file', 'суды':'/court cases',
        'решение':'/court decide', 'клуб создать':'/club create', 'клуб вступить':'/club join',
        'клуб информация':'/club info', 'кредит':'/borrow', 'погасить':'/repay',
        'банкротство':'/bankruptcy', 'новости':'/news', 'опубликовать новость':'/news publish',
        'телевидение':'/tv', 'сезон':'/season', 'события':'/events', 'участвовать':'/eventjoin',
        'тендеры':'/tenders', 'заявка':'/bid', 'выдать тендер':'/tender_award',
        'недвижимость':'/property', 'купить недвижимость':'/propertybuy',
        'сдать недвижимость':'/propertyrent', 'арендовать':'/rent', 'достижения':'/achievements'
    }
    lowered = text.lower()
    mapped = None
    for alias in sorted(aliases, key=len, reverse=True):
        if lowered == alias or lowered.startswith(alias + ' '):
            mapped = aliases[alias] + text[len(alias):]
            break
    if mapped is not None:
        text = mapped
    elif not text.startswith('/'):
        return
    parts = text.split(maxsplit=2)
    cmd = parts[0].split('@')[0].lower()
    a1 = parts[1] if len(parts)>1 else ''
    rest = parts[2] if len(parts)>2 else ''
    # Подкоманды семьи, клуба и суда преобразуются в привычные внутренние аргументы.
    if cmd in ('/family','/club','/court') and a1:
        rest = (rest + ' ' + parts[2] if len(parts)>2 else '').strip()
        # aliases уже добавили подкоманду после внутренней команды
        if a1 in ('create','join','info','file','cases','decide'):
            pass
    uid = message.from_user.id
    uname = _name(message)

    if cmd in ('/rp_help','/rp'):
        await message.answer(HELP if cmd=='/rp_help' else "🏙 <b>CPM RP 2.0</b>\n\n"+HELP,parse_mode='HTML'); return
    if cmd == '/rp_demo':
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO rp_demo_users(uid,name,cash,bank,debt,active,created_at) VALUES(?,?,?,?,0,1,?)",
                      (uid, (rest or uname)[:40], START_CASH, START_BANK, int(time.time())))
            c.execute("INSERT OR REPLACE INTO rp_demo_medical(uid,status,condition_text,updated_at) VALUES(?,?,?,?)",
                      (uid,'healthy','Здоров',int(time.time())))
            c.execute("INSERT OR IGNORE INTO rp_demo_achievements(uid,code,title,reward,unlocked_at) VALUES(?,?,?,?,?)",
                      (uid,'first_login','Первый вход',500,int(time.time())))
            c.execute("UPDATE rp_demo_users SET cash=cash+500 WHERE uid=?",(uid,))
        await message.answer("✅ <b>Тестовый профиль создан!</b>\n💵 Наличные: 50 500\n🏦 Банк: 25 000\n\nПопробуй <code>/rp</code> или <code>/rp_help</code>. Все операции изолированы от реального баланса.",parse_mode='HTML'); return
    if cmd == '/rp_live':
        with _conn() as c: c.execute("UPDATE rp_demo_users SET active=0 WHERE uid=?",(uid,))
        await message.answer("Тестовый режим выключен. Данные реального аккаунта не менялись."); return
    if cmd == '/market_refresh':
        if not _is_admin(uid): await message.answer('Нет доступа.'); return
        with _conn() as c:
            for r in c.execute("SELECT sector FROM rp_demo_economy").fetchall():
                factor=random.uniform(0.94,1.06)
                c.execute("UPDATE rp_demo_economy SET index_value=MAX(0.5,MIN(1.8,index_value*?)),updated_at=? WHERE sector=?",(factor,int(time.time()),r['sector']))
            c.execute("UPDATE rp_demo_cars SET price_index=MAX(0.65,MIN(1.6,price_index*(1+?)))",(random.uniform(-0.06,0.06),))
            for stock in c.execute("SELECT symbol,price,volatility FROM rp_demo_stocks").fetchall():
                c.execute("UPDATE rp_demo_stocks SET price=MAX(10,price*(1+?)) WHERE symbol=?",(random.uniform(-stock['volatility'],stock['volatility']),stock['symbol']))
        await message.answer('📊 Рыночные индексы, цены автомобилей и акции обновлены.'); return
    if cmd == '/tender_award':
        if not _is_admin(uid): await message.answer('Нет доступа.'); return
        try: tid=int(a1); winner=int(rest.split()[0])
        except: await message.answer('Формат: /tender_award ID UID'); return
        with _conn() as c:
            b=c.execute("SELECT amount FROM rp_demo_bids WHERE tender_id=? AND uid=?",(tid,winner)).fetchone()
            if not b: await message.answer('Заявка игрока не найдена.'); return
            c.execute("UPDATE rp_demo_tenders SET status='awarded',winner_uid=?,winning_bid=? WHERE id=?",(winner,b['amount'],tid))
            c.execute("UPDATE rp_demo_users SET cash=cash+? WHERE uid=?",(b['amount'],winner))
        await message.answer('🏛 Тендер присуждён. Сумма перечислена в тестовом режиме.'); return
    if not await _need_demo(message): return
    me = _demo(uid)

    if cmd == '/election':
        with _conn() as c:
            e=c.execute("SELECT * FROM rp_demo_elections WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
            if not e: await message.answer('Сейчас нет активных выборов.'); return
            cs=c.execute("SELECT uid,slogan FROM rp_demo_candidates WHERE election_id=? ORDER BY uid",(e['id'],)).fetchall()
            lines=[f"🗳 <b>{html.escape(e['title'])}</b> · выборы #{e['id']}"]
            lines += [f"Кандидат <code>{x['uid']}</code>: {html.escape(x['slogan'])}" for x in cs]
        await message.answer('\n'.join(lines)+"\n\nВыдвинуться: <code>/candidate программа</code>\nГолосовать: <code>/vote UID</code>",parse_mode='HTML'); return
    if cmd == '/candidate':
        slogan=' '.join(parts[1:])[:200]
        if not slogan: await message.answer('Формат: /candidate Моя программа'); return
        with _conn() as c:
            e=c.execute("SELECT id FROM rp_demo_elections WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
            if not e: await message.answer('Активных выборов нет.'); return
            c.execute("INSERT OR REPLACE INTO rp_demo_candidates VALUES(?,?,?)",(e['id'],uid,slogan))
        await message.answer('✅ Ты зарегистрирован кандидатом.'); return
    if cmd == '/vote':
        try: candidate=int(a1)
        except: await message.answer('Формат: /vote UID_кандидата'); return
        with _conn() as c:
            e=c.execute("SELECT id FROM rp_demo_elections WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
            if not e or not c.execute("SELECT 1 FROM rp_demo_candidates WHERE election_id=? AND uid=?",(e['id'],candidate)).fetchone(): await message.answer('Кандидат не найден.'); return
            c.execute("INSERT OR REPLACE INTO rp_demo_votes VALUES(?,?,?)",(e['id'],uid,candidate))
        await message.answer('🗳 Голос принят. Повторное голосование заменит предыдущий голос.'); return
    if cmd == '/parliament':
        with _conn() as c:
            e=c.execute("SELECT * FROM rp_demo_elections ORDER BY id DESC LIMIT 1").fetchone()
            if not e: await message.answer('Парламент ещё не сформирован.'); return
            rows=c.execute("SELECT c.uid,c.slogan,COUNT(v.voter_uid) AS votes FROM rp_demo_candidates c LEFT JOIN rp_demo_votes v ON v.election_id=c.election_id AND v.candidate_uid=c.uid WHERE c.election_id=? GROUP BY c.uid,c.slogan ORDER BY votes DESC",(e['id'],)).fetchall()
        await message.answer('🏛 <b>Парламент CPM RP</b>\n'+('\n'.join(f"{i+1}. UID {r['uid']} — {r['votes']} голосов\n{html.escape(r['slogan'])}" for i,r in enumerate(rows)) or 'Кандидаты пока не зарегистрированы.'),parse_mode='HTML'); return
    if cmd == '/election_close':
        if not _is_admin(uid): await message.answer('Нет доступа.'); return
        with _conn() as c:
            e=c.execute("SELECT id FROM rp_demo_elections WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
            if not e: await message.answer('Нет открытых выборов.'); return
            winner=c.execute("SELECT candidate_uid,COUNT(*) AS n FROM rp_demo_votes WHERE election_id=? GROUP BY candidate_uid ORDER BY n DESC,candidate_uid LIMIT 1",(e['id'],)).fetchone()
            c.execute("UPDATE rp_demo_elections SET status='closed',winner_uid=? WHERE id=?",(winner['candidate_uid'] if winner else None,e['id']))
        await message.answer(f"🏛 Выборы завершены. Президент: UID {winner['candidate_uid']} ({winner['n']} голосов)." if winner else 'Выборы завершены без голосов.'); return

    if cmd == '/economy':
        with _conn() as c: rows=c.execute("SELECT label,index_value FROM rp_demo_economy ORDER BY sector").fetchall()
        await message.answer("📊 <b>Экономика города</b>\n"+'\n'.join(f"{r['label']}: {r['index_value']*100:.1f}%" for r in rows)+f"\n\nТвой кошелёк: {_fmt(me['cash'])} | Банк: {_fmt(me['bank'])}",parse_mode='HTML'); return
    if cmd in ('/carprices','/carprice'):
        with _conn() as c:
            if cmd=='/carprice':
                try: cid=int(a1)
                except: await message.answer('Формат: /carprice ID'); return
                r=c.execute("SELECT * FROM rp_demo_cars WHERE id=?",(cid,)).fetchone()
                if not r: await message.answer('Автомобиль не найден.'); return
                await message.answer(f"🚘 {html.escape(r['model'])}\nБазовая цена: {_fmt(r['base_price'])}\nРыночный индекс: {r['price_index']*100:.1f}%\nЦена сейчас: <b>{_fmt(r['base_price']*r['price_index'])}</b>",parse_mode='HTML'); return
            rows=c.execute("SELECT * FROM rp_demo_cars ORDER BY id").fetchall()
        await message.answer('🚘 <b>Рыночные цены авто</b>\n'+'\n'.join(f"#{r['id']} {html.escape(r['model'])} — {_fmt(r['base_price']*r['price_index'])}" for r in rows),parse_mode='HTML'); return
    if cmd == '/carbuy':
        try: cid=int(a1)
        except: await message.answer('Формат: /carbuy ID'); return
        with _conn() as c:
            car=c.execute("SELECT * FROM rp_demo_cars WHERE id=?",(cid,)).fetchone()
            if not car: await message.answer('Автомобиль не найден.'); return
            if car['owner_uid'] is not None: await message.answer('Этот автомобиль уже принадлежит игроку.'); return
            price=int(car['base_price']*car['price_index'])
            bal=c.execute("SELECT cash FROM rp_demo_users WHERE uid=?",(uid,)).fetchone()[0]
            if bal<price: await message.answer(f'Не хватает тестовых денег. Цена: {_fmt(price)}.'); return
            c.execute("UPDATE rp_demo_users SET cash=cash-? WHERE uid=?",(price,uid))
            c.execute("UPDATE rp_demo_cars SET owner_uid=? WHERE id=? AND owner_uid IS NULL",(uid,cid))
            c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'car_buy',-price,car['model'],int(time.time())))
        await message.answer(f"🚗 Куплен {html.escape(car['model'])} за {_fmt(price)}.",parse_mode='HTML'); return
    if cmd == '/stocks':
        with _conn() as c:
            stocks=c.execute("SELECT * FROM rp_demo_stocks").fetchall(); holdings=c.execute("SELECT symbol,shares FROM rp_demo_holdings WHERE uid=? AND shares>0",(uid,)).fetchall()
        await message.answer('📈 <b>Фондовый рынок</b>\n'+'\n'.join(f"{r['symbol']} — {r['title']}: {_fmt(r['price'])}/акция" for r in stocks)+'\n\nТвои акции: '+(', '.join(f"{r['symbol']} ×{r['shares']}" for r in holdings) or 'нет')+'\nПокупка: /stockbuy AUTO 2',parse_mode='HTML'); return
    if cmd in ('/stockbuy','/stocksell'):
        try: sym=a1.upper(); qty=int(rest.split()[0]);
        except: await message.answer('Формат: /stockbuy AUTO 2 или /stocksell AUTO 2'); return
        if qty<1 or qty>10000: await message.answer('Количество должно быть от 1 до 10 000.'); return
        with _conn() as c:
            st=c.execute("SELECT price FROM rp_demo_stocks WHERE symbol=?",(sym,)).fetchone()
            if not st: await message.answer('Тикер не найден.'); return
            price=int(st['price']*qty)
            h=c.execute("SELECT shares FROM rp_demo_holdings WHERE uid=? AND symbol=?",(uid,sym)).fetchone()
            if cmd=='/stockbuy':
                bal=c.execute("SELECT cash FROM rp_demo_users WHERE uid=?",(uid,)).fetchone()[0]
                if bal<price: await message.answer('Недостаточно тестовых наличных.'); return
                c.execute("UPDATE rp_demo_users SET cash=cash-? WHERE uid=?",(price,uid))
                c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'stock_buy',-price,f'{sym}:{qty}',int(time.time())))
                c.execute("INSERT INTO rp_demo_holdings(uid,symbol,shares) VALUES(?,?,?) ON CONFLICT(uid,symbol) DO UPDATE SET shares=shares+excluded.shares",(uid,sym,qty))
            else:
                if not h or h['shares']<qty: await message.answer('Недостаточно акций.'); return
                c.execute("UPDATE rp_demo_holdings SET shares=shares-? WHERE uid=? AND symbol=?",(qty,uid,sym))
                c.execute("UPDATE rp_demo_users SET cash=cash+? WHERE uid=?",(price,uid))
                c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'stock_sell',price,f'{sym}:{qty}',int(time.time())))
        await message.answer(f"✅ {'Куплено' if cmd=='/stockbuy' else 'Продано'} {qty} акц. {sym} за {_fmt(price)}."); return

    if cmd == '/call911':
        data=' '.join(parts[1:])
        if not data or ' ' not in data: await message.answer('Формат: /call911 СКОРАЯ|ПОЛИЦИЯ|ПОЖАРНЫЕ описание'); return
        kind,desc=data.split(' ',1); kind=kind.upper()
        if kind not in ('СКОРАЯ','ПОЛИЦИЯ','ПОЖАРНЫЕ'): await message.answer('Тип: СКОРАЯ, ПОЛИЦИЯ или ПОЖАРНЫЕ.'); return
        with _conn() as c: c.execute("INSERT INTO rp_demo_calls(uid,kind,description,created_at) VALUES(?,?,?,?)",(uid,kind,desc[:300],int(time.time())))
        await message.answer('🚨 Вызов зарегистрирован. Диспетчер увидит его в /dispatch.'); return
    if cmd == '/dispatch':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_calls WHERE status!='closed' ORDER BY id DESC LIMIT 15").fetchall()
        await message.answer('📟 <b>Диспетчерская 911</b>\n'+('\n'.join(f"#{r['id']} {r['kind']} · от {r['uid']} · {html.escape(r['description'])} · {r['status']}" for r in rows) or 'Активных вызовов нет.'),parse_mode='HTML'); return
    if cmd in ('/takecall','/closecall'):
        try: cid=int(a1)
        except: await message.answer(f'Формат: {cmd} ID'); return
        with _conn() as c:
            r=c.execute("SELECT * FROM rp_demo_calls WHERE id=?",(cid,)).fetchone()
            if not r: await message.answer('Вызов не найден.'); return
            if cmd=='/takecall': c.execute("UPDATE rp_demo_calls SET status='assigned',assigned_uid=? WHERE id=? AND status='open'",(uid,cid))
            else:
                if r['assigned_uid'] not in (None,uid) and not _is_admin(uid): await message.answer('Закрыть вызов может назначенный сотрудник или администратор.'); return
                c.execute("UPDATE rp_demo_calls SET status='closed' WHERE id=?",(cid,))
        await message.answer('✅ Статус вызова обновлён.'); return

    if cmd == '/medical':
        with _conn() as c: r=c.execute("SELECT * FROM rp_demo_medical WHERE uid=?",(uid,)).fetchone()
        await message.answer(f"🏥 <b>Медкарта</b>\nСтатус: {r['status']}\nСостояние: {r['condition_text']}\nГоспитализация: /hospitalize (500)\nВыписка: /discharge",parse_mode='HTML'); return
    if cmd == '/hospitalize':
        if not _cash(uid,-500,'hospital','Госпитализация'): await message.answer('Не хватает 500 тестовых денег.'); return
        with _conn() as c: c.execute("UPDATE rp_demo_medical SET status='hospitalized',condition_text='На лечении',updated_at=? WHERE uid=?",(int(time.time()),uid))
        await message.answer('🏥 Ты госпитализирован. После лечения используй /discharge.'); return
    if cmd == '/discharge':
        with _conn() as c:
            r=c.execute("SELECT status FROM rp_demo_medical WHERE uid=?",(uid,)).fetchone()
            if not r or r['status']!='hospitalized': await message.answer('Ты не находишься в больнице.'); return
            c.execute("UPDATE rp_demo_medical SET status='healthy',condition_text='Выписан, состояние стабильное',updated_at=? WHERE uid=?",(int(time.time()),uid))
        await message.answer('✅ Ты выписан.'); return

    if cmd == '/family':
        sub=a1.lower(); arg=rest or ''
        if sub=='create' and arg:
            try:
                with _conn() as c:
                    c.execute("INSERT INTO rp_demo_families(name,owner_uid,created_at) VALUES(?,?,?)",(arg[:40],uid,int(time.time())))
                    fid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                    c.execute("INSERT INTO rp_demo_family_members VALUES(?,?,?)",(fid,uid,'owner'))
                await message.answer(f'👨‍👩‍👧‍👦 Семья создана. ID: {fid}');
            except sqlite3.IntegrityError: await message.answer('Такое название семьи уже занято.')
            return
        if sub=='join':
            try: fid=int(arg)
            except: await message.answer('Формат: /family join ID'); return
            with _conn() as c:
                if not c.execute("SELECT 1 FROM rp_demo_families WHERE id=?",(fid,)).fetchone(): await message.answer('Семья не найдена.'); return
                c.execute("INSERT OR IGNORE INTO rp_demo_family_members VALUES(?,?,?)",(fid,uid,'member'))
            await message.answer('✅ Ты вступил в семью.'); return
        if sub=='info':
            try: fid=int(arg)
            except: await message.answer('Формат: /family info ID'); return
            with _conn() as c:
                f=c.execute("SELECT * FROM rp_demo_families WHERE id=?",(fid,)).fetchone(); n=c.execute("SELECT COUNT(*) FROM rp_demo_family_members WHERE family_id=?",(fid,)).fetchone()[0]
            if not f: await message.answer('Семья не найдена.'); return
            await message.answer(f"👨‍👩‍👧‍👦 {html.escape(f['name'])} · ID {fid}\nГлава: {f['owner_uid']}\nУчастников: {n}",parse_mode='HTML'); return
        await message.answer('Команды: /family create Название · /family join ID · /family info ID'); return
    if cmd == '/marry':
        try: target=int(a1)
        except: await message.answer('Формат: /marry TELEGRAM_UID (второй игрок должен создать /rp_demo)'); return
        if target==uid or not _demo(target): await message.answer('Игрок не найден в тестовом городе или это ты сам.'); return
        with _conn() as c:
            c.execute("INSERT OR IGNORE INTO rp_demo_marriages(uid1,uid2,status,created_at) VALUES(?,?,?,?)",(uid,target,'pending',int(time.time())))
            mid=c.execute("SELECT id FROM rp_demo_marriages WHERE uid1=? AND uid2=?",(uid,target)).fetchone()[0]
        await message.answer(f'💍 Предложение создано. ID {mid}. Второй игрок принимает: /marryaccept {mid}');
        try: await message.bot.send_message(target,f'💍 Игрок {html.escape(uname)} сделал предложение. Принять: /marryaccept {mid}',parse_mode='HTML')
        except Exception: pass
        return
    if cmd == '/marryaccept':
        try: mid=int(a1)
        except: await message.answer('Формат: /marryaccept ID'); return
        with _conn() as c:
            r=c.execute("SELECT * FROM rp_demo_marriages WHERE id=? AND uid2=? AND status='pending'",(mid,uid)).fetchone()
            if not r: await message.answer('Предложение не найдено.'); return
            c.execute("UPDATE rp_demo_marriages SET status='married' WHERE id=?",(mid,))
        await message.answer('💍 Поздравляем! Брак зарегистрирован в тестовом RP.'); return
    if cmd == '/will':
        try: heir=int(a1)
        except: await message.answer('Формат: /will UID_наследника'); return
        if heir==uid or not _demo(heir): await message.answer('Наследник должен иметь тестовый профиль.'); return
        with _conn() as c: c.execute("INSERT INTO rp_demo_wills(uid,heir_uid,created_at) VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET heir_uid=excluded.heir_uid,created_at=excluded.created_at",(uid,heir,int(time.time())))
        await message.answer(f'📜 Завещание сохранено. Наследник: UID {heir}.'); return
    if cmd == '/rp_death':
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO rp_demo_deaths(uid,deceased_at,claimed) VALUES(?,?,0)",(uid,int(time.time())))
        await message.answer('🕯 Тестовая смерть зарегистрирована. Наследник может использовать /inheritance_claim.'); return
    if cmd == '/inheritance':
        with _conn() as c:
            w=c.execute("SELECT * FROM rp_demo_wills WHERE uid=?",(uid,)).fetchone()
            d=c.execute("SELECT * FROM rp_demo_deaths WHERE uid=?",(uid,)).fetchone()
        await message.answer((f"📜 Наследник: UID {w['heir_uid']}\nСтатус: {'наследство уже получено' if d and d['claimed'] else 'ожидает события смерти' if not d else 'можно получить'}" if w else 'Завещание не оформлено.') ); return
    if cmd == '/inheritance_claim':
        with _conn() as c:
            will=c.execute("SELECT uid FROM rp_demo_wills WHERE heir_uid=? ORDER BY created_at DESC LIMIT 1",(uid,)).fetchone()
            if not will: await message.answer('Доступного наследства нет.'); return
            deceased=will['uid']
            death=c.execute("SELECT claimed FROM rp_demo_deaths WHERE uid=?",(deceased,)).fetchone()
            if not death or death['claimed']: await message.answer('Наследодатель ещё не умер в тестовом сценарии или наследство уже получено.'); return
            source=c.execute("SELECT cash,bank FROM rp_demo_users WHERE uid=?",(deceased,)).fetchone()
            if not source: await message.answer('Профиль наследодателя не найден.'); return
            c.execute("UPDATE rp_demo_users SET cash=cash+?,bank=bank+? WHERE uid=?",(source['cash'],source['bank'],uid))
            c.execute("UPDATE rp_demo_users SET cash=0,bank=0 WHERE uid=?",(deceased,))
            c.execute("UPDATE rp_demo_cars SET owner_uid=? WHERE owner_uid=?",(uid,deceased))
            c.execute("UPDATE rp_demo_properties SET owner_uid=? WHERE owner_uid=?",(uid,deceased))
            c.execute("UPDATE rp_demo_deaths SET claimed=1 WHERE uid=?",(deceased,))
        await message.answer('🏛 Наследство получено: переведены тестовые деньги, автомобили и недвижимость.'); return

    if cmd == '/court':
        sub=a1.lower()
        if sub=='file':
            try: defendant=int(rest.split(maxsplit=1)[0]); desc=rest.split(maxsplit=1)[1]
            except: await message.answer('Формат: /court file UID описание'); return
            if not _demo(defendant): await message.answer('Ответчик должен быть в тестовом городе (/rp_demo).'); return
            with _conn() as c:
                c.execute("INSERT INTO rp_demo_court_cases(plaintiff_uid,defendant_uid,description,created_at) VALUES(?,?,?,?)",(uid,defendant,desc[:500],int(time.time())))
                cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            await message.answer(f'⚖️ Иск зарегистрирован. Номер дела: {cid}'); return
        if sub=='cases':
            with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_court_cases WHERE plaintiff_uid=? OR defendant_uid=? ORDER BY id DESC",(uid,uid)).fetchall()
            await message.answer('⚖️ <b>Судебные дела</b>\n'+('\n'.join(f"#{r['id']} истец {r['plaintiff_uid']} → ответчик {r['defendant_uid']}: {html.escape(r['description'])} [{r['status']}]" for r in rows) or 'Дел нет.'),parse_mode='HTML'); return
        if sub=='decide' and _is_admin(uid):
            try: cid=int(rest.split(maxsplit=1)[0]); verdict=rest.split(maxsplit=1)[1]
            except: await message.answer('Формат: /court decide ID решение'); return
            with _conn() as c: c.execute("UPDATE rp_demo_court_cases SET status='closed',verdict=?,judge_uid=? WHERE id=?",(verdict[:300],uid,cid))
            await message.answer('⚖️ Решение суда сохранено.'); return
        await message.answer('Команды: /court file UID описание · /court cases · /court decide ID решение (админ)'); return

    if cmd == '/club':
        sub=a1.lower(); arg=rest or ''
        if sub=='create' and arg:
            try:
                with _conn() as c:
                    c.execute("INSERT INTO rp_demo_clubs(name,owner_uid,created_at) VALUES(?,?,?)",(arg[:40],uid,int(time.time())))
                    cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                    c.execute("INSERT INTO rp_demo_club_members VALUES(?,?,?)",(cid,uid,'owner'))
                await message.answer(f'🏎 Клуб создан. ID {cid}')
            except sqlite3.IntegrityError: await message.answer('Такой клуб уже существует.')
            return
        if sub=='join':
            try: cid=int(arg)
            except: await message.answer('Формат: /club join ID'); return
            with _conn() as c:
                if not c.execute("SELECT 1 FROM rp_demo_clubs WHERE id=?",(cid,)).fetchone(): await message.answer('Клуб не найден.'); return
                c.execute("INSERT OR IGNORE INTO rp_demo_club_members VALUES(?,?,?)",(cid,uid,'member'))
            await message.answer('🏁 Ты вступил в клуб.'); return
        if sub=='info':
            try: cid=int(arg)
            except: await message.answer('Формат: /club info ID'); return
            with _conn() as c:
                r=c.execute("SELECT * FROM rp_demo_clubs WHERE id=?",(cid,)).fetchone(); n=c.execute("SELECT COUNT(*) FROM rp_demo_club_members WHERE club_id=?",(cid,)).fetchone()[0]
            if not r: await message.answer('Клуб не найден.'); return
            await message.answer(f"🏎 {html.escape(r['name'])}\nГлава: {r['owner_uid']}\nУчастников: {n}",parse_mode='HTML'); return
        await message.answer('Команды: /club create Название · /club join ID · /club info ID'); return

    if cmd == '/borrow':
        try: amount=int(a1)
        except: await message.answer('Формат: /borrow СУММА'); return
        if amount<100 or amount>100000: await message.answer('Тестовый кредит: от 100 до 100 000.'); return
        with _conn() as c: c.execute("UPDATE rp_demo_users SET debt=debt+? WHERE uid=?",(int(amount*1.1),uid))
        _cash(uid,amount,'loan','Тестовый кредит с 10% комиссией')
        await message.answer(f'🏦 Выдано {_fmt(amount)}. К погашению: {_fmt(amount*1.1)}.'); return
    if cmd == '/repay':
        try: amount=int(a1)
        except: await message.answer('Формат: /repay СУММА'); return
        if amount<=0 or amount>me['debt']: await message.answer(f"Сумма должна быть от 1 до {_fmt(me['debt'])}."); return
        if not _cash(uid,-amount,'loan_repay','Погашение тестового кредита'): await message.answer('Недостаточно наличных.'); return
        with _conn() as c: c.execute("UPDATE rp_demo_users SET debt=debt-? WHERE uid=?",(amount,uid))
        await message.answer(f'✅ Погашено {_fmt(amount)}. Остаток долга: {_fmt(me["debt"]-amount)}.'); return
    if cmd == '/bankruptcy':
        if me['debt']<=0: await message.answer('У тебя нет задолженности.'); return
        new_debt=int(me['debt']*0.6)
        with _conn() as c: c.execute("UPDATE rp_demo_users SET debt=?,cash=0,bank=0 WHERE uid=?",(new_debt,uid))
        await message.answer(f'⚖️ Тестовое банкротство одобрено. Долг реструктурирован до {_fmt(new_debt)}. Наличные и банк заморожены до погашения.'); return

    if cmd == '/news':
        if a1.lower()=='publish' and _is_admin(uid):
            raw=' '.join(parts[1:])
            try: title,body=raw[len('publish '):].split('|',1)
            except: await message.answer('Формат: /news publish Заголовок | Текст'); return
            with _conn() as c: c.execute("INSERT INTO rp_demo_news(title,body,author_uid,created_at) VALUES(?,?,?,?)",(title.strip()[:120],body.strip()[:1000],uid,int(time.time())))
            await message.answer('📰 Новость опубликована в тестовой ленте.'); return
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_news ORDER BY id DESC LIMIT 10").fetchall()
        await message.answer('📰 <b>CPM NEWS</b>\n'+('\n\n'.join(f"<b>{html.escape(r['title'])}</b>\n{html.escape(r['body'])}" for r in rows) or 'Пока нет новостей.'),parse_mode='HTML'); return
    if cmd == '/tv':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_news ORDER BY id DESC LIMIT 5").fetchall()
        await message.answer('📺 <b>CPM TV — эфир</b>\n'+('\n\n'.join(f"▶️ <b>{html.escape(r['title'])}</b>\n{html.escape(r['body'])}" for r in rows) or 'Сегодня в эфире: городские новости и RP-события. Новостей пока нет.'),parse_mode='HTML'); return
    if cmd == '/season':
        with _conn() as c: r=c.execute("SELECT * FROM rp_demo_seasons WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
        await message.answer(f"🎬 <b>Сезон #{r['id']}: {html.escape(r['name'])}</b>\n{html.escape(r['description'])}",parse_mode='HTML'); return
    if cmd == '/events':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_events WHERE status='open'").fetchall()
        await message.answer('🎯 <b>Сюжетные события</b>\n'+('\n'.join(f"#{r['id']} {html.escape(r['title'])} — награда {_fmt(r['reward'])}. /eventjoin {r['id']}" for r in rows) or 'Активных событий нет.'),parse_mode='HTML'); return
    if cmd == '/eventjoin':
        try: eid=int(a1)
        except: await message.answer('Формат: /eventjoin ID'); return
        with _conn() as c:
            r=c.execute("SELECT * FROM rp_demo_events WHERE id=? AND status='open'",(eid,)).fetchone()
            if not r: await message.answer('Событие не найдено.'); return
            cur=c.execute("INSERT OR IGNORE INTO rp_demo_event_members VALUES(?,?)",(eid,uid))
            if cur.rowcount:
                c.execute("UPDATE rp_demo_users SET cash=cash+? WHERE uid=?",(r['reward'],uid))
                c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'event_reward',r['reward'],r['title'],int(time.time())))
        await message.answer('🎉 Участие зарегистрировано. Награда начисляется один раз.'); return

    if cmd == '/tenders':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_tenders WHERE status='open'").fetchall()
        await message.answer('📑 <b>Государственные тендеры</b>\n'+('\n'.join(f"#{r['id']} {html.escape(r['title'])} · бюджет {_fmt(r['budget'])}\n{html.escape(r['description'])}\n/bid {r['id']} СУММА" for r in rows) or 'Открытых тендеров нет.'),parse_mode='HTML'); return
    if cmd == '/bid':
        try: tid=int(a1); amount=int(rest.split()[0])
        except: await message.answer('Формат: /bid ID СУММА'); return
        with _conn() as c:
            t=c.execute("SELECT * FROM rp_demo_tenders WHERE id=? AND status='open'",(tid,)).fetchone()
            if not t: await message.answer('Тендер не найден или закрыт.'); return
            if amount<=0 or amount>t['budget']: await message.answer('Предложение должно быть положительным и не превышать бюджет.'); return
            c.execute("INSERT OR REPLACE INTO rp_demo_bids VALUES(?,?,?,?)",(tid,uid,amount,int(time.time())))
        await message.answer('✅ Заявка на тендер подана. Победителя определяет администрация.'); return

    if cmd == '/property':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_properties").fetchall()
        await message.answer('🏠 <b>Каталог недвижимости</b>\n'+'\n'.join(f"#{r['id']} {html.escape(r['title'])} · {_fmt(r['price'])} · аренда {_fmt(r['daily_rent'])}/день · владелец {r['owner_uid'] or 'город'}" for r in rows)+'\nПокупка: /propertybuy ID',parse_mode='HTML'); return
    if cmd == '/propertybuy':
        try: pid=int(a1)
        except: await message.answer('Формат: /propertybuy ID'); return
        with _conn() as c:
            p=c.execute("SELECT * FROM rp_demo_properties WHERE id=?",(pid,)).fetchone()
            if not p or p['owner_uid'] is not None: await message.answer('Объект уже продан или не найден.'); return
            bal=c.execute("SELECT cash FROM rp_demo_users WHERE uid=?",(uid,)).fetchone()[0]
            if bal<p['price']: await message.answer('Недостаточно тестовых денег.'); return
            c.execute("UPDATE rp_demo_users SET cash=cash-? WHERE uid=?",(p['price'],uid))
            c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'property_buy',-p['price'],p['title'],int(time.time())))
            c.execute("UPDATE rp_demo_properties SET owner_uid=? WHERE id=? AND owner_uid IS NULL",(uid,pid))
        await message.answer('🏠 Недвижимость куплена.'); return
    if cmd == '/propertyrent':
        try: pid=int(a1); daily=int(rest.split()[0])
        except: await message.answer('Формат: /propertyrent ID СУММА_В_ДЕНЬ'); return
        if daily<0 or daily>100000: await message.answer('Ставка должна быть от 0 до 100 000.'); return
        with _conn() as c:
            p=c.execute("SELECT owner_uid FROM rp_demo_properties WHERE id=?",(pid,)).fetchone()
            if not p or p['owner_uid']!=uid: await message.answer('Можно менять аренду только у своей недвижимости.'); return
            c.execute("UPDATE rp_demo_properties SET daily_rent=? WHERE id=?",(daily,pid))
        await message.answer(f'🏠 Ставка аренды объекта #{pid}: {_fmt(daily)} в день.'); return
    if cmd == '/rent':
        try: pid=int(a1); days=int(rest.split()[0])
        except: await message.answer('Формат: /rent ID ДНЕЙ'); return
        if days<1 or days>30: await message.answer('Аренда доступна на 1–30 дней.'); return
        with _conn() as c:
            p=c.execute("SELECT * FROM rp_demo_properties WHERE id=?",(pid,)).fetchone()
            if not p: await message.answer('Объект не найден.'); return
            cost=p['daily_rent']*days
            if p['owner_uid']==uid: await message.answer('Нельзя арендовать собственную недвижимость.'); return
            bal=c.execute("SELECT cash FROM rp_demo_users WHERE uid=?",(uid,)).fetchone()[0]
            if bal<cost: await message.answer('Недостаточно средств.'); return
            c.execute("UPDATE rp_demo_users SET cash=cash-? WHERE uid=?",(cost,uid))
            c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(uid,'rent',-cost,f'property {pid}, {days} days',int(time.time())))
            if p['owner_uid']:
                c.execute("UPDATE rp_demo_users SET cash=cash+? WHERE uid=?",(cost,p['owner_uid']))
                c.execute("INSERT INTO rp_demo_audit(uid,action,amount,details,created_at) VALUES(?,?,?,?,?)",(p['owner_uid'],'rent_income',cost,f'property {pid}',int(time.time())))
            c.execute("INSERT INTO rp_demo_rentals(property_id,tenant_uid,paid_amount,start_at,end_at) VALUES(?,?,?,?,?)",(pid,uid,cost,int(time.time()),int(time.time())+days*86400))
        await message.answer(f'🔑 Аренда оформлена на {days} дн. Стоимость: {_fmt(cost)}.'); return

    if cmd == '/achievements':
        with _conn() as c: rows=c.execute("SELECT * FROM rp_demo_achievements WHERE uid=? ORDER BY unlocked_at",(uid,)).fetchall()
        await message.answer('🏆 <b>Достижения</b>\n'+('\n'.join(f"✅ {html.escape(r['title'])} · награда {_fmt(r['reward'])}" for r in rows) or 'Пока нет достижений.'),parse_mode='HTML'); return

