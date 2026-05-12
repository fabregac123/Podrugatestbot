import yookassa
from yookassa import Payment, Configuration

Configuration.account_id = "1337862"
Configuration.secret_key = "live_wBwcOU04buIEA0HDSJJotRbZXsbt_ZgfIscV6N356fo"

try:
    payment = Payment.create({
        "amount": {"value": "99.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/test"},
        "description": "Test",
        "capture": True
    })
    print("✅ Платёж создан:", payment.id)
    print("✅ Ссылка:", payment.confirmation.confirmation_url)
except Exception as e:
    print("❌ Ошибка:", type(e).__name__, str(e))
