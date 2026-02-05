import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date

app = Flask(__name__)

# --- CONFIGURATION ---
# Секретний ключ (береться з Environment Variables або дефолтний для тесту)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this-in-prod')

# База даних: Якщо є DATABASE_URL (Koyeb/Heroku), юзаємо її. Якщо ні — локальний файл.
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///regis_life.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    # timing values: 'urgent', 'this_week', 'next_week', 'later'
    timing = db.Column(db.String(20), default='later') 
    is_completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Boolean, default=True)

# --- AUTH & HELPERS ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_week_dates():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    return [start_of_week + timedelta(days=i) for i in range(7)]

def calculate_stats(user):
    user_habits = Habit.query.filter_by(user_id=user.id).all()
    if not user_habits: return 0, "N/A"
    
    habit_ids = [h.id for h in user_habits]
    total_slots = len(user_habits) * 7
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    
    completed = HabitLog.query.filter(HabitLog.habit_id.in_(habit_ids), HabitLog.date >= start_of_week).count()
    score = int((completed / total_slots) * 100)
    
    verdict = "Normal"
    if score > 85: verdict = "Legendary! 🔥"
    elif score > 50: verdict = "Stable 👍"
    else: verdict = "Needs Focus 😬"
    
    return score, verdict

# --- ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
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
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Tasks
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    # Sort: Urgent(0) > ThisWeek(1) > Next(2) > Later(3). Completed at bottom.
    timing_order = {'urgent': 0, 'this_week': 1, 'next_week': 2, 'later': 3}
    tasks.sort(key=lambda t: (t.is_completed, timing_order.get(t.timing, 3)))
    
    categories = sorted(list(set([t.category for t in tasks if t.category])))
    
    # Habits
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

    score, verdict = calculate_stats(current_user)
    
    return render_template('dashboard.html', 
                           tasks=tasks, categories=categories, habits=habit_grid, 
                           week_dates=week_dates, score=score, verdict=verdict, 
                           today=date.today(), user=current_user)

# --- API (CRUD) ---

@app.route('/api/tasks', methods=['POST'])
@login_required
def add_task():
    data = request.json
    new_task = Task(title=data.get('title'), category=data.get('category'), 
                    timing=data.get('timing', 'later'), user_id=current_user.id)
    db.session.add(new_task)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:id>', methods=['PUT'])
@login_required
def edit_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    data = request.json
    task.title = data.get('title', task.title)
    task.category = data.get('category', task.category)
    task.timing = data.get('timing', task.timing)
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
    db.session.add(new_habit)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/habits/<int:id>', methods=['DELETE'])
@login_required
def delete_habit(id):
    habit = Habit.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    HabitLog.query.filter_by(habit_id=id).delete()
    db.session.delete(habit)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/toggle_habit', methods=['POST'])
@login_required
def toggle_habit():
    data = request.json
    habit = Habit.query.filter_by(id=data.get('habit_id'), user_id=current_user.id).first_or_404()
    
    log_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    log = HabitLog.query.filter_by(habit_id=habit.id, date=log_date).first()
    
    if log:
        db.session.delete(log)
        status = 'today' if log_date == date.today() else 'missed'
    else:
        db.session.add(HabitLog(habit_id=habit.id, date=log_date, status=True))
        status = 'done'
        
    db.session.commit()
    
    score, verdict = calculate_stats(current_user)
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    habit_logs = HabitLog.query.filter(HabitLog.habit_id==habit.id, HabitLog.date >= start_of_week).count()
    habit_progress = int((habit_logs / 7) * 100)

    return jsonify({'success': True, 'status': status, 'new_score': score, 'new_verdict': verdict, 'habit_progress': habit_progress})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8000)
