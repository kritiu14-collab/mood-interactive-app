from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import db, User, Task
from datetime import datetime

admin = Blueprint('admin', __name__)

def admin_required(f):
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Access denied. Admins only.')
            return redirect(url_for('index'))  # your main index
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin.route('/')
@admin_required
def dashboard():
    total_users = User.query.count()
    total_tasks = Task.query.count()
    pending_tasks = Task.query.filter_by(status='pending').count()
    done_tasks = Task.query.filter_by(status='done').count()
    
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_tasks = Task.query.order_by(Task.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', 
                         total_users=total_users,
                         total_tasks=total_tasks,
                         pending_tasks=pending_tasks,
                         done_tasks=done_tasks,
                         recent_users=recent_users,
                         recent_tasks=recent_tasks)

@admin.route('/tasks')
@admin_required
def tasks():
    tasks = Task.query.all()
    return render_template('admin/tasks.html', tasks=tasks)

@admin.route('/tasks/new', methods=['GET', 'POST'])
@admin_required
def new_task():
    if request.method == 'POST':
        task = Task(
            title=request.form['title'],
            status=request.form.get('status', 'pending'),
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        flash('Task created!')
        return redirect(url_for('admin.tasks'))
    return render_template('admin/tasks_new.html')

@admin.route('/tasks/<int:task_id>/delete', methods=['POST'])
@admin_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted!')
    return redirect(url_for('admin.tasks'))

@admin.route('/users')
@admin_required
def users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)