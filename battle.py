"""Битвы подруг — отдельный модуль"""
import sqlite3
import secrets
from datetime import datetime

DB = 'bot_simple.db'

def init_battle_tables():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS battles_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        title TEXT,
        questions TEXT,
        options TEXT,
        correct TEXT,
        battle_code TEXT UNIQUE,
        max_players INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT "waiting"
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS battle_players_new (
        battle_id INTEGER,
        user_id INTEGER,
        score REAL DEFAULT 0,
        answers TEXT,
        finished_at TIMESTAMP,
        UNIQUE(battle_id, user_id)
    )''')
    conn.commit()
    conn.close()

def create_battle(creator_id, title, questions, options, correct, max_players=3):
    """Создаёт новую битву"""
    import json
    battle_code = secrets.token_hex(4)[:8]
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""INSERT INTO battles_new (creator_id, title, questions, options, correct, battle_code, max_players)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (creator_id, title, json.dumps(questions), json.dumps(options), json.dumps(correct), battle_code, max_players))
    conn.commit()
    conn.close()
    return battle_code

def get_battle(battle_code):
    import json
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM battles_new WHERE battle_code = ?", (battle_code,))
    row = c.fetchone()
    conn.close()
    if row:
        battle = dict(row)
        battle['questions'] = json.loads(battle['questions'])
        battle['options'] = json.loads(battle['options'])
        battle['correct'] = json.loads(battle['correct'])
        return battle
    return None

def join_battle(battle_code, user_id):
    """Подруга присоединяется к битве"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    battle = get_battle(battle_code)
    if not battle:
        conn.close()
        return False, "Битва не найдена"
    c.execute("SELECT COUNT(*) FROM battle_players_new WHERE battle_id = ?", (battle['id'],))
    count = c.fetchone()[0]
    if count >= battle['max_players']:
        conn.close()
        return False, f"Битва заполнена! Максимум {battle['max_players']} участниц"
    c.execute("INSERT OR IGNORE INTO battle_players_new (battle_id, user_id) VALUES (?, ?)",
              (battle['id'], user_id))
    if battle['status'] == 'waiting':
        c.execute("UPDATE battles_new SET status = 'active' WHERE id = ?", (battle['id'],))
    conn.commit()
    conn.close()
    return True, battle

def save_battle_result(battle_code, user_id, answers, score):
    import json
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    battle = get_battle(battle_code)
    if battle:
        c.execute("""UPDATE battle_players_new 
                     SET answers = ?, score = ?, finished_at = CURRENT_TIMESTAMP 
                     WHERE battle_id = ? AND user_id = ?""",
                  (json.dumps(answers), score, battle['id'], user_id))
        conn.commit()
    conn.close()

def get_battle_results(battle_code):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    battle = get_battle(battle_code)
    if not battle:
        conn.close()
        return None, []
    c.execute("""SELECT u.first_name, bp.score, bp.user_id
                 FROM battle_players_new bp
                 JOIN users u ON bp.user_id = u.user_id
                 WHERE bp.battle_id = ?
                 ORDER BY bp.score DESC""", (battle['id'],))
    players = [dict(row) for row in c.fetchall()]
    conn.close()
    return battle, players

def finish_battle(battle_code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE battles_new SET status = 'finished' WHERE battle_code = ?", (battle_code,))
    conn.commit()
    conn.close()

# Инициализируем таблицы при импорте
init_battle_tables()
