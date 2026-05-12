with open('bot.py', 'r') as f:
    content = f.read()

# ===== НОВЫЕ ФУНКЦИИ ДЛЯ БИТВ =====

battle_functions = '''
# === ФУНКЦИИ БИТВ ===
def create_battle(creator_id, test_id, max_players=3, time_limit=600):
    """Создаёт новую битву"""
    import secrets
    battle_code = secrets.token_hex(4)[:8]
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO battles (creator_id, test_id, battle_code, max_players, time_limit)
                 VALUES (?, ?, ?, ?, ?)''',
              (creator_id, test_id, battle_code, max_players, time_limit))
    conn.commit()
    conn.close()
    return battle_code

def get_battle_by_code(battle_code):
    """Получает битву по коду"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM battles WHERE battle_code = ?', (battle_code,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def join_battle(battle_code, user_id, total_questions):
    """Подруга присоединяется к битве"""
    conn = get_db()
    c = conn.cursor()
    battle = get_battle_by_code(battle_code)
    if not battle:
        conn.close()
        return False, "Битва не найдена"
    
    # Проверяем лимит участниц
    c.execute('SELECT COUNT(*) FROM battle_players WHERE battle_id = ?', (battle['id'],))
    count = c.fetchone()[0]
    if count >= battle['max_players']:
        conn.close()
        return False, f"Битва заполнена! Максимум {battle['max_players']} участниц"
    
    # Добавляем участницу
    c.execute('''INSERT OR IGNORE INTO battle_players (battle_id, user_id, total_questions)
                 VALUES (?, ?, ?)''', (battle['id'], user_id, total_questions))
    
    # Если битва ещё не начата - запускаем
    if battle['status'] == 'waiting':
        c.execute('UPDATE battles SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?',
                  ('active', battle['id']))
    
    conn.commit()
    conn.close()
    return True, battle

def update_battle_progress(battle_code, user_id, progress, score):
    """Обновляет прогресс участницы в битве"""
    conn = get_db()
    c = conn.cursor()
    battle = get_battle_by_code(battle_code)
    if battle:
        c.execute('''UPDATE battle_players SET progress = ?, score = ?
                     WHERE battle_id = ? AND user_id = ?''',
                  (progress, score, battle['id'], user_id))
        conn.commit()
    conn.close()

def get_battle_leaderboard(battle_code):
    """Получает рейтинг битвы"""
    conn = get_db()
    c = conn.cursor()
    battle = get_battle_by_code(battle_code)
    if not battle:
        conn.close()
        return None, []
    c.execute('''SELECT u.first_name, bp.score, bp.progress, bp.total_questions, bp.user_id
                 FROM battle_players bp
                 JOIN users u ON bp.user_id = u.user_id
                 WHERE bp.battle_id = ?
                 ORDER BY bp.score DESC''', (battle['id'],))
    players = [dict(row) for row in c.fetchall()]
    conn.close()
    return battle, players

def get_battle_status_text(battle, players, current_user_id=None):
    """Форматирует статус битвы"""
    if not battle:
        return "Битва не найдена"
    
    time_left = "завершена"
    if battle['status'] == 'active' and battle['started_at']:
        elapsed = (datetime.now() - datetime.fromisoformat(battle['started_at'])).total_seconds()
        remaining = battle['time_limit'] - elapsed
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            time_left = f"{mins} мин {secs} сек"
    
    text = f"⚔️ *БИТВА ПОДРУГ*\\n\\n⏱ Осталось: {time_left}\\n👥 Участниц: {len(players)}/{battle['max_players']}\\n\\n🏆 *РЕЙТИНГ:*\\n\\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(players):
        medal = medals[i] if i < 3 else f"{i+1}."
        progress_bar = "🟢" * (p['progress'] or 0) + "⚪" * ((p['total_questions'] or 10) - (p['progress'] or 0))
        marker = " ← ты" if p['user_id'] == current_user_id else ""
        text += f"{medal} *{p['first_name']}* — {p['score']:.0f}%\\n   {progress_bar}{marker}\\n\\n"
    
    return text

def finish_battle(battle_code):
    """Завершает битву"""
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE battles SET status = ?, finished_at = CURRENT_TIMESTAMP WHERE battle_code = ?',
              ('finished', battle_code))
    conn.commit()
    conn.close()
'''

# Вставляем функции перед # === БАЗА ДАННЫХ ===
if '# === БАЗА ДАННЫХ ===' in content:
    content = content.replace('# === БАЗА ДАННЫХ ===', battle_functions + '\n# === БАЗА ДАННЫХ ===')
    print("✅ Функции битв добавлены")
else:
    # Вставляем после импортов
    content += battle_functions
    print("✅ Функции битв добавлены в конец")

with open('bot.py', 'w') as f:
    f.write(content)

print("✅ Часть 2 готова!")
