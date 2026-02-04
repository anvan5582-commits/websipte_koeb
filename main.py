import os
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

@app.before_request
def before_request():
    # Наш редірект на HTTPS
    if not request.is_secure and request.headers.get('X-Forwarded-Proto') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

@app.route("/")
def home():
    # Відкриваємо ваш HTML-файл з папки templates
    return render_template("index.html") 

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
