"""
Мини-сервер для проксирования платежей YooKassa
Запускается отдельно и принимает запросы от страниц оплаты
"""
import http.server
import json
import ssl
import urllib.request
import urllib.parse
import base64
import os

SHOP_ID = "1337862"
SECRET_KEY = "live_wBwcOU04buIEA0HDSJJotRbZXsbt_ZgfIscV6N356fo"
PORT = 8443

class PaymentHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)
        
        # Проксируем запрос к YooKassa
        auth = base64.b64encode(f"{SHOP_ID}:{SECRET_KEY}".encode()).decode()
        
        req = urllib.request.Request(
            'https://api.yookassa.ru/v3/payments',
            data=json.dumps(data).encode(),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Basic {auth}',
                'Idempotence-Key': os.urandom(16).hex()
            }
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(result)
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), PaymentHandler)
    print(f"🚀 Прокси YooKassa запущен на порту {PORT}")
    server.serve_forever()
