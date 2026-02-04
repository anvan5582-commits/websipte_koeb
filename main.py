import os
from flask import Flask, request, redirect

app = Flask(__name__)

@app.before_request
def before_request():
    # Koyeb передає заголовок X-Forwarded-Proto, щоб ми знали, який протокол у юзера
    if not request.is_secure and request.headers.get('X-Forwarded-Proto') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

@app.route("/")
def home():
    # Додаємо заголовок HSTS вручну для безпеки
    response = app.make_response("<h1>Привіт! Тепер редірект працює на рівні коду! 🔐</h1>")
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
