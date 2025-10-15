from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from db import get_db_connection

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT password, role FROM passwords WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user[0] == password:
            session['username'] = username
            session['role'] = user[1]
            if user[1] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user[1] == 'coach':
                return redirect(url_for('coach_dashboard'))
            elif user[1] == 'athlete':
                return redirect(url_for('athlete_dashboard'))
        else:
            flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')

@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
