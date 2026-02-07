import os
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from itertools import groupby

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
    archived_at = db.Column(db.Date, nullable=True) 
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
    grid_snapshot = db.Column(db.Text, default="[]") 

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

def get_live_weekly_grid(user):
    today = date.today()
    start_date = today - timedelta(days=today.weekday())
    user_habits = Habit.query.filter_by(user_id=user.id).all()
    grid_rows = []
    total_checks = 0
    total_slots = len(user_habits) * 7 if user_habits else 1

    for habit in user_habits:
        days_status = []
        for i in range(7):
            current_day = start_date + timedelta(days=i)
            is_done = HabitLog.query.filter_by(habit_id=habit.id, date=current_day).first() is not None
            days_status.append(is_done)
            if is_done: total_checks += 1
        grid_rows.append({'name': habit.name, 'days': days_status})

    week_score = int((total_checks / total_slots) * 100)
    mood = 'sad'
    if week_score >= 80: mood = 'wow'
    elif week_score >= 40: mood = 'ok'
    return {'rows': grid_rows, 'score': week_score, 'mood': mood}

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
        db.session.add(new_user); db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user); return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
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

    habit_score, tasks_done, tasks_total = calculate_current_stats(current_user)
    verdict = "Normal"
    if habit_score > 85: verdict = "Legendary! 🔥"
    elif habit_score > 50: verdict = "Stable 👍"
    else: verdict = "Needs Focus 😬"

    # --- HISTORY SNAPSHOTS ---
    past_reports = WeeklyReport.query.filter_by(user_id=current_user.id)\
        .order_by(WeeklyReport.created_at.desc()).limit(2).all()
    past_reports.reverse() 

    heatmap_data = []
    for r in past_reports:
        try: grid_rows = json.loads(r.grid_snapshot)
        except: grid_rows = []
        mood = 'sad'
        if r.habit_score >= 80: mood = 'wow'
        elif r.habit_score >= 40: mood = 'ok'
        heatmap_data.append({'label': 'Past', 'score': r.habit_score, 'rows': grid_rows, 'mood': mood, 'trend': 'flat'})
    
    while len(heatmap_data) < 2:
        heatmap_data.insert(0, {'label': 'No Data', 'score': 0, 'rows': [], 'mood': 'sad', 'trend': 'flat'})

    heatmap_data[0]['label'] = '2 Weeks Ago'
    heatmap_data[1]['label'] = 'Last Week'

    live_data = get_live_weekly_grid(current_user)
    heatmap_data.append({
        'label': 'This Week',
        'score': live_data['score'],
        'rows': live_data['rows'],
        'mood': live_data['mood'],
        'trend': 'flat'
    })

    for i in range(1, 3):
        prev = heatmap_data[i-1]['score']
        curr = heatmap_data[i]['score']
        diff = curr - prev
        if diff >= 5: heatmap_data[i]['trend'] = 'up'
        elif diff <= -5: heatmap_data[i]['trend'] = 'down'
        else: heatmap_data[i]['trend'] = 'flat'

    return render_template('dashboard.html', 
                           tasks=tasks, categories=categories, habits=habit_grid, 
                           week_dates=week_dates, score=habit_score, verdict=verdict,
                           heatmap_data=heatmap_data, today=date.today(), user=current_user)

@app.route('/archive')
@login_required
def archive():
    tasks = Task.query.filter_by(user_id=current_user.id, is_archived=True).order_by(Task.archived_at.desc()).all()
    grouped_tasks = {}
    for key, group in groupby(tasks, key=lambda x: x.archived_at):
        date_label = key.strftime('%B %d, %Y') if key else "Unknown Date"
        grouped_tasks[date_label] = list(group)
    return render_template('archive.html', grouped_tasks=grouped_tasks, user=current_user)

@app.route('/api/restore_task/<int:id>', methods=['POST'])
@login_required
def restore_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    task.is_archived = False
    task.archived_at = None
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/simulate_week_end', methods=['POST'])
@login_required
def simulate_week_end():
    current_grid_data = get_live_weekly_grid(current_user)
    habit_score = current_grid_data['score']
    tasks_done = Task.query.filter_by(user_id=current_user.id, is_archived=False, is_completed=True).count()
    tasks_total = Task.query.filter_by(user_id=current_user.id, is_archived=False).count()

    last_report = WeeklyReport.query.filter_by(user_id=current_user.id).order_by(WeeklyReport.created_at.desc()).first()
    msg = "Good job!"
    if last_report:
        if habit_score > last_report.habit_score: msg = "Better than last week! 🚀"
        elif habit_score < last_report.habit_score: msg = "A bit lower than before."

    grid_json = json.dumps(current_grid_data['rows'])

    report = WeeklyReport(
        user_id=current_user.id,
        week_start_date=date.today() - timedelta(days=date.today().weekday()),
        habit_score=habit_score,
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        motivation_msg=msg,
        grid_snapshot=grid_json 
    )
    db.session.add(report)
    
    completed_tasks = Task.query.filter_by(user_id=current_user.id, is_completed=True, is_archived=False).all()
    for task in completed_tasks: 
        task.is_archived = True
        task.archived_at = date.today()
        
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    user_habits = Habit.query.filter_by(user_id=current_user.id).all()
    habit_ids = [h.id for h in user_habits]
    if habit_ids:
        HabitLog.query.filter(HabitLog.habit_id.in_(habit_ids), HabitLog.date >= start_of_week).delete(synchronize_session=False)

    db.session.commit()
    return jsonify({'success': True, 'report_msg': msg})

# --- CRUD APIs ---
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
    task.title=data.get('title', task.title)
    task.category=data.get('category', task.category)
    task.timing=data.get('timing', task.timing)
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
    # FIX: use 'description' to match frontend request
    new_habit = Habit(name=data.get('name'), description=data.get('description'), user_id=current_user.id)
    db.session.add(new_habit); db.session.commit()
    return jsonify({'success': True})

# --- НОВИЙ МАРШРУТ: РЕДАГУВАННЯ ЗВИЧКИ ---
@app.route('/api/habits/<int:id>', methods=['PUT'])
@login_required
def edit_habit(id):
    habit = Habit.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    data = request.json
    habit.name = data.get('name', habit.name)
    habit.description = data.get('description', habit.description)
    db.session.commit()
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
