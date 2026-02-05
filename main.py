import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date

app = Flask(__name__)

# --- CONFIG ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this-in-prod')
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///regis_life.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    timing = db.Column(db.String(20), default='later') 
    is_completed = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Boolean, default=True)

class WeeklyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    habit_score = db.Column(db.Integer, default=0)
    tasks_done = db.Column(db.Integer, default=0)
    tasks_total = db.Column(db.Integer, default=0)
    motivation_msg = db.Column(db.String(200))

# --- HELPERS ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

with app.app_context(): db.create_all()

def get_week_dates():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    return [start_of_week + timedelta(days=i) for i in range(7)]

def calculate_current_stats(user):
    user_habits = Habit.query.filter_by(user_id=user.id).all()
    habit_score = 0
    if user_habits:
        habit_ids = [h.id for h in user_habits]
        total_slots = len(user_habits) * 7
        start_of_week = date.today() - timedelta(days=date.today().weekday())
        completed = HabitLog.query.filter(HabitLog.habit_id.in_(habit_ids), HabitLog.date >= start_of_week).count()
        habit_score = int((completed / total_slots) * 100)
    
    tasks_all = Task.query.filter_by(user_id=user.id, is_archived=False).all()
    tasks_total = len(tasks_all)
    tasks_done = len([t for t in tasks_all if t.is_completed])
    return habit_score, tasks_done, tasks_total

# --- ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if len(username) > 99 or User.query.filter_by(username=username).first(): return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Tasks & Habits Logic (Same as before)
    tasks = Task.query.filter_by(user_id=current_user.id, is_archived=False).all()
    timing_order = {'urgent': 0, 'this_week': 1, 'next_week': 2, 'later': 3}
    tasks.sort(key=lambda t: (t.is_completed, timing_order.get(t.timing, 3)))
    categories = sorted(list(set([t.category for t in tasks if t.category])))
    
    habits = Habit.query.filter_by(user_id=current_user.id).all()
    week_dates = get_week_dates()
    habit_grid = []
    for habit in habits:
        days_status = []
        completed_count = 0
        for day in week_dates:
            log = HabitLog.query.filter_by(habit_id=habit.id, date=day).first()
            status = 'done' if log else ('today' if day == date.today() else 'missed')
            if log: completed_count += 1
            days_status.append({'date': day, 'status': status})
        progress = int((completed_count / 7) * 100)
        habit_grid.append({'obj': habit, 'days': days_status, 'progress': progress})

    # Stats Logic
    habit_score, tasks_done, tasks_total = calculate_current_stats(current_user)
    verdict = "Normal"
    if habit_score > 85: verdict = "Legendary! 🔥"
    elif habit_score > 50: verdict = "Stable 👍"
    else: verdict = "Needs Focus 😬"

    # --- Отримуємо звіти за ОСТАННІ 2 ТИЖНІ ---
    # Беремо 2 останні записи, сортуємо від нових до старих
    past_reports = WeeklyReport.query.filter_by(user_id=current_user.id)\
        .order_by(WeeklyReport.created_at.desc())\
        .limit(2).all()
    
    # Формуємо дані для графіка (Current + Last + Before Last)
    # Структура: [BeforeLast, Last, Current] (зліва направо по часу)
    
    chart_data = []
    
    # 1. Позаминулий (якщо є)
    if len(past_reports) == 2:
        r = past_reports[1]
        chart_data.append({
            'label': '2 Weeks Ago',
            'score': r.habit_score,
            'tasks': f"{r.tasks_done}/{r.tasks_total}",
            'color': 'bg-gray-300 dark:bg-gray-600'
        })
    else:
        chart_data.append({'label': '2 Weeks Ago', 'score': 0, 'tasks': '-', 'color': 'bg-gray-200 dark:bg-gray-700 opacity-50'})

    # 2. Минулий (якщо є)
    if len(past_reports) >= 1:
        r = past_reports[0]
        chart_data.append({
            'label': 'Last Week',
            'score': r.habit_score,
            'tasks': f"{r.tasks_done}/{r.tasks_total}",
            'color': 'bg-blue-400'
        })
    else:
        chart_data.append({'label': 'Last Week', 'score': 0, 'tasks': '-', 'color': 'bg-gray-200 dark:bg-gray-700 opacity-50'})

    # 3. Поточний (Завжди є "на льоту")
    chart_data.append({
        'label': 'This Week',
        'score': habit_score,
        'tasks': f"{tasks_done}/{tasks_total}",
        'color': 'bg-green-500' # Яскравий, бо це зараз
    })

    return render_template('dashboard.html', 
                           tasks=tasks, categories=categories, habits=habit_grid, 
                           week_dates=week_dates, score=habit_score, verdict=verdict,
                           chart_data=chart_data, # Передаємо дані для графіка
                           today=date.today(), user=current_user)

# --- API ---
@app.route('/api/simulate_week_end', methods=['POST'])
@login_required
def simulate_week_end():
    habit_score, tasks_done, tasks_total = calculate_current_stats(current_user)
    last_report = WeeklyReport.query.filter_by(user_id=current_user.id).order_by(WeeklyReport.created_at.desc()).first()
    msg = "Good job!"
    if last_report:
        if habit_score > last_report.habit_score: msg = "Improved since last week!"
        elif habit_score < last_report.habit_score: msg = "A bit lower than before."
    
    report = WeeklyReport(
        user_id=current_user.id,
        week_start_date=date.today() - timedelta(days=date.today().weekday()),
        habit_score=habit_score,
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        motivation_msg=msg
    )
    db.session.add(report)
    
    completed_tasks = Task.query.filter_by(user_id=current_user.id, is_completed=True, is_archived=False).all()
    count_archived = len(completed_tasks)
    for task in completed_tasks: task.is_archived = True
        
    db.session.commit()
    return jsonify({'success': True, 'archived_count': count_archived, 'report_msg': msg})

# CRUD (Task/Habit/Toggle) - БЕЗ ЗМІН (як в попередньому коді)
@app.route('/api/tasks', methods=['POST'])
@login_required
def add_task():
    data = request.json
    new_task = Task(title=data.get('title'), category=data.get('category'), timing=data.get('timing', 'later'), user_id=current_user.id)
    db.session.add(new_task); db.session.commit()
    return jsonify({'success': True})
@app.route('/api/tasks/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(task); db.session.commit()
    return jsonify({'success': True})
@app.route('/api/tasks/<int:id>', methods=['PUT'])
@login_required
def edit_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    data = request.json
    task.title=data.get('title'); task.category=data.get('category'); task.timing=data.get('timing')
    db.session.commit()
    return jsonify({'success': True})
@app.route('/api/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.is_completed = not task.is_completed
    db.session.commit()
    return jsonify({'success': True})
@app.route('/api/habits', methods=['POST'])
@login_required
def add_habit():
    data = request.json
    new_habit = Habit(name=data.get('name'), description=data.get('description'), user_id=current_user.id)
    db.session.add(new_habit); db.session.commit()
    return jsonify({'success': True})
@app.route('/api/habits/<int:id>', methods=['DELETE'])
@login_required
def delete_habit(id):
    habit = Habit.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    HabitLog.query.filter_by(habit_id=id).delete(); db.session.delete(habit); db.session.commit()
    return jsonify({'success': True})
@app.route('/api/toggle_habit', methods=['POST'])
@login_required
def toggle_habit():
    data = request.json
    habit = Habit.query.filter_by(id=data.get('habit_id'), user_id=current_user.id).first_or_404()
    log_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    log = HabitLog.query.filter_by(habit_id=habit.id, date=log_date).first()
    if log: db.session.delete(log); status = 'today' if log_date == date.today() else 'missed'
    else: db.session.add(HabitLog(habit_id=habit.id, date=log_date, status=True)); status = 'done'
    db.session.commit()
    habit_score, tasks_done, tasks_total = calculate_current_stats(current_user)
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    habit_logs = HabitLog.query.filter(HabitLog.habit_id==habit.id, HabitLog.date >= start_of_week).count()
    habit_progress = int((habit_logs / 7) * 100)
    verdict = "Normal"
    if habit_score > 85: verdict = "Legendary! 🔥"
    elif habit_score > 50: verdict = "Stable 👍"
    else: verdict = "Needs Focus 😬"
    return jsonify({'success': True, 'status': status, 'new_score': habit_score, 'new_verdict': verdict, 'habit_progress': habit_progress})

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=8000)
