from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, date

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///regis_life.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    # timing: 'urgent', 'this_week', 'next_week', 'later'
    timing = db.Column(db.String(20), default='later') 
    is_completed = db.Column(db.Boolean, default=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Boolean, default=True)

# --- LOGIC ---
def get_week_dates():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    return [start_of_week + timedelta(days=i) for i in range(7)]

def calculate_stats():
    total_slots = Habit.query.count() * 7
    if total_slots == 0: return 0, "N/A"
    
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    completed = HabitLog.query.filter(HabitLog.date >= start_of_week).count()
    
    score = int((completed / total_slots) * 100)
    
    verdict = "Normal"
    if score > 85: verdict = "Legendary! 🔥"
    elif score > 50: verdict = "Stable 👍"
    else: verdict = "Needs Focus 😬"
    
    return score, verdict

# --- ROUTES ---
@app.route('/')
def index():
    # Fetch all tasks
    tasks = Task.query.all()
    
    # Custom Sort: 
    # 1. Not completed first (False < True)
    # 2. Priority: Urgent(0) > ThisWeek(1) > NextWeek(2) > Later(3)
    timing_order = {'urgent': 0, 'this_week': 1, 'next_week': 2, 'later': 3}
    tasks.sort(key=lambda t: (t.is_completed, timing_order.get(t.timing, 3)))
    
    categories = sorted(list(set([t.category for t in tasks if t.category])))
    
    habits = Habit.query.all()
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

    score, verdict = calculate_stats()
    
    return render_template('dashboard.html', 
                           tasks=tasks, 
                           categories=categories,
                           habits=habit_grid, 
                           week_dates=week_dates, 
                           score=score, 
                           verdict=verdict, 
                           today=date.today())

# --- API ---
@app.route('/api/tasks', methods=['POST'])
def add_task():
    data = request.json
    new_task = Task(title=data.get('title'), category=data.get('category'), timing=data.get('timing', 'later'))
    db.session.add(new_task)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):
    task = Task.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:id>', methods=['PUT'])
def edit_task(id):
    task = Task.query.get_or_404(id)
    data = request.json
    task.title = data.get('title', task.title)
    task.category = data.get('category', task.category)
    task.timing = data.get('timing', task.timing)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/toggle_task/<int:task_id>', methods=['POST'])
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.is_completed = not task.is_completed
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/habits', methods=['POST'])
def add_habit():
    data = request.json
    new_habit = Habit(name=data.get('name'), description=data.get('description'))
    db.session.add(new_habit)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/habits/<int:id>', methods=['DELETE'])
def delete_habit(id):
    habit = Habit.query.get_or_404(id)
    HabitLog.query.filter_by(habit_id=id).delete()
    db.session.delete(habit)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/habits/<int:id>', methods=['PUT'])
def edit_habit(id):
    habit = Habit.query.get_or_404(id)
    data = request.json
    habit.name = data.get('name', habit.name)
    habit.description = data.get('description', habit.description)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/toggle_habit', methods=['POST'])
def toggle_habit():
    data = request.json
    habit_id = data.get('habit_id')
    day_str = data.get('date')
    log_date = datetime.strptime(day_str, '%Y-%m-%d').date()
    
    log = HabitLog.query.filter_by(habit_id=habit_id, date=log_date).first()
    if log:
        db.session.delete(log)
        status = 'today' if log_date == date.today() else 'missed'
    else:
        db.session.add(HabitLog(habit_id=habit_id, date=log_date, status=True))
        status = 'done'
        
    db.session.commit()
    score, verdict = calculate_stats()
    
    start_of_week = date.today() - timedelta(days=date.today().weekday())
    habit_logs = HabitLog.query.filter(HabitLog.habit_id==habit_id, HabitLog.date >= start_of_week).count()
    habit_progress = int((habit_logs / 7) * 100)

    return jsonify({'success': True, 'status': status, 'new_score': score, 'new_verdict': verdict, 'habit_progress': habit_progress})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8000)
