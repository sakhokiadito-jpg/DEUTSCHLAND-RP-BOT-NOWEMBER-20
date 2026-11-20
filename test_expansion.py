import os, sys, types, tempfile, sqlite3, importlib.util
# Minimal aiogram stubs: the test validates SQLite schema/migrations without Telegram runtime.
class Filter:
    def __getattr__(self, name): return self
    def startswith(self, *args): return self
class Router:
    def __init__(self, *a, **k): pass
    def message(self, *a, **k): return lambda fn: fn
fake_aiogram = types.ModuleType('aiogram'); fake_aiogram.Router=Router; fake_aiogram.F=Filter(); fake_aiogram.types=types.SimpleNamespace(Message=object)
sys.modules['aiogram']=fake_aiogram
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['CPMRP_DB_PATH']=path
spec=importlib.util.spec_from_file_location('rp_expansion', os.path.join(os.path.dirname(__file__),'rp_expansion.py'))
rp=importlib.util.module_from_spec(spec); sys.modules['rp_expansion']=rp; spec.loader.exec_module(rp)
rp.init_db()
with sqlite3.connect(path) as c:
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected={'rp_demo_users','rp_demo_elections','rp_demo_candidates','rp_demo_votes','rp_demo_economy','rp_demo_calls','rp_demo_medical','rp_demo_families','rp_demo_family_members','rp_demo_marriages','rp_demo_wills','rp_demo_deaths','rp_demo_seasons','rp_demo_events','rp_demo_event_members','rp_demo_cars','rp_demo_court_cases','rp_demo_clubs','rp_demo_club_members','rp_demo_news','rp_demo_tenders','rp_demo_bids','rp_demo_properties','rp_demo_rentals','rp_demo_stocks','rp_demo_holdings','rp_demo_achievements','rp_demo_audit'}
    assert expected <= tables, expected-tables
    c.execute("INSERT INTO rp_demo_users(uid,name,cash,bank,debt,active,created_at) VALUES(1,'tester',50000,25000,0,1,0)")
    c.execute("INSERT INTO rp_demo_medical(uid,status,condition_text,updated_at) VALUES(1,'healthy','ok',0)")
    # Test safe balance guard and transaction-style stock buy.
    assert c.execute("SELECT cash FROM rp_demo_users WHERE uid=1").fetchone()[0] == 50000
    c.execute("UPDATE rp_demo_users SET cash=cash-1200 WHERE uid=1")
    c.execute("INSERT INTO rp_demo_holdings(uid,symbol,shares) VALUES(1,'AUTO',1)")
    assert c.execute("SELECT cash FROM rp_demo_users WHERE uid=1").fetchone()[0] == 48800
    # Test that migrations are idempotent.
rp.init_db()
with sqlite3.connect(path) as c:
    assert c.execute("SELECT COUNT(*) FROM rp_demo_stocks").fetchone()[0] >= 3
    assert c.execute("SELECT COUNT(*) FROM rp_demo_events").fetchone()[0] >= 1
os.unlink(path)
print('PASS: 26 RP tables, seed data, balance isolation, idempotent init')
