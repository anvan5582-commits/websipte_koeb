from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Привіт! Це мій перший сайт на Koyeb! 🚀</h1>"

if __name__ == "__main__":
    # Запускаємо сервер на 8000 порту (стандарт для Koyeb)
    app.run(host="0.0.0.0", port=8000)
