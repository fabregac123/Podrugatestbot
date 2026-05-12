with open('bot.py', 'r') as f:
    lines = f.readlines()

# Ищем начало callback_handler
new_lines = []
found_handler = False
inserted = False

for i, line in enumerate(lines):
    new_lines.append(line)
    
    # Нашли начало callback_handler (после data = query.data)
    if 'data = query.data' in line and not inserted:
        found_handler = True
        continue
    
    if found_handler and not inserted and line.strip() == '':
        # Вставляем наши проверки перед первым if
        new_lines.append('    # === ПРЕМИУМ КНОПКИ (ПРОВЕРЯЕМ ПЕРВЫМИ) ===\n')
        new_lines.append('    if data in ["buy_15days", "buy_month"]:\n')
        new_lines.append('        await buy_premium(update, context)\n')
        new_lines.append('        return\n')
        new_lines.append('    elif data.startswith("check_payment_"):\n')
        new_lines.append('        await check_payment(update, context)\n')
        new_lines.append('        return\n')
        new_lines.append('    elif data == "cancel_premium":\n')
        new_lines.append('        await cancel_premium(update, context)\n')
        new_lines.append('        return\n')
        new_lines.append('\n')
        inserted = True
        found_handler = False

# Удаляем старые проверки buy_15days (они ниже)
final_lines = []
skip_next = 0
for line in new_lines:
    if 'elif data in ["buy_15days", "buy_month"]' in line and not line.strip().startswith('#'):
        skip_next = 2  # Пропускаем строку elif и следующую await
        continue
    if skip_next > 0:
        skip_next -= 1
        continue
    final_lines.append(line)

with open('bot.py', 'w') as f:
    f.writelines(final_lines)

print("✅ Исправлено! Кнопки премиума теперь проверяются первыми")
