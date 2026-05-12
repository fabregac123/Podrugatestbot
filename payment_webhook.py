import sqlite3
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

DB_NAME = 'bot_simple.db'

def process_payment(amount, user_id, tariff):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if tariff == '24h' or amount == 79:
        days = 1
    elif tariff == 'week' or amount == 149:
        days = 7
    elif tariff == 'forever' or amount == 499:
        days = 365
    else:
        days = 1
    
    until = (datetime.now() + timedelta(days=days)).isoformat()
    c.execute('UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?', (until, user_id))
    c.execute('''INSERT INTO payments (payment_id, user_id, days, amount, status) 
                 VALUES (?, ?, ?, ?, ?)''', 
              (f"sbp_{user_id}_{int(datetime.now().timestamp())}", user_id, days, amount, 'success'))
    conn.commit()
    conn.close()
    print(f"✅ Премиум выдан: user={user_id}, days={days}, amount={amount}")
    return True

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)
        
        user_id = data.get('user_id')
        amount = data.get('amount')
        tariff = data.get('tariff', '')
        
        if user_id and amount:
            process_payment(int(amount), int(user_id), tariff)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(400)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8888), WebhookHandler)
    print("🚀 Платёжный вебхук запущен на порту 8888")
    server.serve_forever()
