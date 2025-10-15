from flask import Flask, render_template, session, redirect, url_for,  request, jsonify, flash
from auth import auth
from db import get_db_connection
import psycopg2
from werkzeug.utils import secure_filename
import cv2
import torch
from ultralytics import YOLO
import numpy as np
import os
from datetime import datetime
from flask_login import LoginManager, login_required, current_user
from datetime import datetime, timedelta
import json
from collections import defaultdict


app = Flask(__name__)
app.config.from_pyfile('config.py')
app.register_blueprint(auth, url_prefix='/auth')

model = YOLO('best.pt')
# model = YOLO("yolo11m-pose.pt")

months_ru = {1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'}

from datetime import datetime

def calculate_age(birth_date):
    if not birth_date:
        return "не указан"
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age

# Добавьте функцию в контекст шаблонов
app.jinja_env.globals.update(calculate_age=calculate_age)

@app.route('/')
def index():
    if 'username' in session:
        role = session['role']
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'coach':
            return redirect(url_for('coach_dashboard'))
        elif role == 'athlete':
            return redirect(url_for('athlete_dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем группы и их тренеров
    cursor.execute('''
        SELECT g.group_id, g.group_name, c.coach_surname, c.coach_name, c.coach_patronymic 
        FROM groups g 
        LEFT JOIN coaches c ON g.coach_id = c.coach_id
        ORDER BY g.group_name ASC
    ''')
    groups = cursor.fetchall()

    # Получаем спортсменов по группам (включая group_id)
    groups_with_athletes = []
    for group in groups:
        cursor.execute(
            'SELECT athlete_id, athlete_surname, athlete_name, athlete_patronymic, group_id FROM athletes WHERE group_id = %s order by athlete_patronymic', 
            (group[0],))
        athletes = cursor.fetchall()
        groups_with_athletes.append({
            "id": group[0],
            "name": group[1],
            "coach": f"{group[2]} {group[3]} {group[4] if group[4] else ''}" if group[2] else "Нет тренера",
            "athletes": athletes
        })

    # Получаем список тренеров и их групп
    cursor.execute('''
        SELECT c.coach_id, c.coach_surname, c.coach_name, c.coach_patronymic, g.group_id, g.group_name 
        FROM coaches c 
        LEFT JOIN groups g ON c.coach_id = g.coach_id
        ORDER BY c.coach_surname ASC
    ''')
    coaches_data = cursor.fetchall()

    # Структурируем данные о тренерах и их группах
    coaches = {}
    for coach_id, coach_surname, coach_name, coach_patronymic, group_id, group_name in coaches_data:
        if coach_id not in coaches:
            coaches[coach_id] = {
                "coach_id": coach_id,
                "coach_name": f"{coach_surname} {coach_name} {coach_patronymic if coach_patronymic else ''}",
                "groups": []
            }
        if group_id:  # Если у тренера есть группы
            coaches[coach_id]["groups"].append({
                "group_id": group_id,
                "group_name": group_name
            })

    # Получаем расписание
    cursor.execute('''
        SELECT 
            s.schedule_id,
            TO_CHAR(s.training_date, 'DD.MM.YYYY') AS training_date,
            TO_CHAR(s.start_time, 'HH24:MI') AS start_time,
            TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
            s.training_type,
            s.location,
            CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
            g.group_name,
            CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name
        FROM 
            schedule s
        LEFT JOIN 
            coaches c ON s.coach_id = c.coach_id
        LEFT JOIN 
            groups g ON s.group_id = g.group_id
        LEFT JOIN 
            athletes a ON s.athlete_id = a.athlete_id
        ORDER BY 
            s.training_date, s.start_time
    ''')
    schedule = cursor.fetchall()

    conn.close()

    return render_template('groups.html', 
                         groups=groups_with_athletes, 
                         coaches=coaches.values(),
                         schedule=schedule)

@app.route('/coach/dashboard')
def coach_dashboard():
    if 'username' in session and session['role'] == 'coach':
        username = session['username']
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем ID тренера по его username
        cur.execute("""
            SELECT c.coach_id, c.coach_surname, c.coach_name, c.coach_patronymic,
                   c.photo, c.phone_number 
            FROM coaches c 
            JOIN passwords p ON p.password_id = c.password_id
            WHERE p.username = %s
        """, (username,))
        coach_data = cur.fetchone()
        coach_id = coach_data[0]
        coach_info = {
            'name': f"{coach_data[1]} {coach_data[2]} {coach_data[3] or ''}",
            'photo': coach_data[4],
            'phone': coach_data[5]
        }

        # Получаем группы, закрепленные за этим тренером
        cur.execute('SELECT group_id, group_name FROM groups WHERE coach_id = %s', (coach_id,))
        groups = cur.fetchall()

        # Получаем спортсменов по группам
        groups_with_athletes = []
        for group in groups:
            cur.execute('SELECT athlete_id, athlete_surname, athlete_name, athlete_patronymic FROM athletes WHERE group_id = %s', 
                (group[0],))
            athletes = cur.fetchall()
            groups_with_athletes.append({
                "id": group[0],
                "name": group[1],
                "athletes": athletes
            })

        cur.close()
        conn.close()

        return render_template('coach.html', groups=groups_with_athletes, coach_info=coach_info)
    
    return redirect(url_for('auth.login'))

# Панель спортсмена
@app.route('/athlete/dashboard')
def athlete_dashboard():
    if 'username' in session and session['role'] == 'athlete':
        username = session['username']
        conn = get_db_connection()
        cur = conn.cursor()

        # Получаем ID спортсмена по его username
        cur.execute("""
            SELECT a.athlete_id 
            FROM athletes a 
            JOIN passwords p ON p.password_id = a.password_id
            WHERE p.username = %s
        """, (username,))
        athlete_id = cur.fetchone()[0]

        # Получаем все попытки выполнения элементов для этого спортсмена
        cur.execute(
            '''
            SELECT e.element_id, e.element_name, v.training_date, v.video_path
            FROM video v
            JOIN elements e ON v.element_id = e.element_id
            WHERE v.athlete_id = %s
            ORDER BY e.element_name, v.training_date desc
            ''',
            (athlete_id,)
        )
        attempts = cur.fetchall()

        # Структурируем данные в словарь
        elements = {}
        unique_dates = set()  # Уникальные даты с видео
        for element_id, element_name, training_date, video_path in attempts:
            if element_id not in elements:
                elements[element_id] = {'name': element_name, 'attempts': []}
            elements[element_id]['attempts'].append({
                'training_date': training_date.strftime('%Y-%m-%d'),
                'video_path': video_path
            })
            unique_dates.add(training_date.strftime('%Y-%m-%d'))

        # Получаем данные о спортсмене
        cur.execute(
            '''
            SELECT 
                athlete_surname, 
                athlete_name, 
                athlete_patronymic, 
                group_id, 
                birth_date, 
                photo, 
                category 
            FROM athletes 
            WHERE athlete_id = %s
            ''',
            (athlete_id,)
        )
        athlete = cur.fetchone()
        group_id = athlete[3]  # Получаем group_id из результата запроса

        cur.execute('SELECT group_name FROM groups WHERE group_id = %s', (group_id,))
        group_name = cur.fetchone()[0] if group_id else None
        
        # Получаем имя тренера
        coach_name = None
        if group_id:
            cur.execute('''
                SELECT c.coach_surname, c.coach_name, c.coach_patronymic 
                FROM coaches c 
                JOIN groups g ON c.coach_id = g.coach_id 
                WHERE g.group_id = %s
            ''', (group_id,))
            coach_data = cur.fetchone()
            if coach_data:
                coach_name = f"{coach_data[0]} {coach_data[1]} {coach_data[2] if coach_data[2] else ''}"
        
        return render_template('athlete.html', 
                            athlete=athlete, 
                            elements=elements, 
                            athlete_id=athlete_id, 
                            group_id=group_id,
                            group_name=group_name,
                            coach_name=coach_name,
                            unique_dates=list(unique_dates))
    
    return redirect(url_for('auth.login'))

# Функция для создания замедленного видео
def slow_video(input_path, output_path, slow_factor=2):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print("Не удалось открыть видео.")
        return False
    
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fps = cap.get(cv2.CAP_PROP_FPS) / slow_factor
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        output.write(frame)

    cap.release()
    output.release()
    return True

# Функции для рисования скелета
def draw_skeleton(image, keypoints, confs, connections, color):
    for (p1, p2) in connections:
        if confs[p1] > 0.7 and confs[p2] > 0.7:
            x1, y1 = int(keypoints[p1][0]), int(keypoints[p1][1])
            x2, y2 = int(keypoints[p2][0]), int(keypoints[p2][1])
            if (x1, y1) != (0, 0) and (x2, y2) != (0, 0):
                cv2.line(image, (x1, y1), (x2, y2), color, 2)

def frame2skeleton(image, model):
    colors = {
        "green": (0, 255, 0),
        "blue": (255, 0, 0),
        "red": (0, 0, 255),
        "rose": (152, 52, 219),
        "white": (255, 255, 255),
        "lightblue": (51, 219, 0)
    }
    with torch.no_grad():
        results = model(image)[0]
        if hasattr(results, 'boxes') and hasattr(results.boxes, 'cls') and len(results.boxes.cls) > 0:
            classes_names = results.names
            classes = results.boxes.cls.cpu().numpy()
            boxes = results.boxes.xyxy.cpu().numpy().astype(np.int32)
            boxes_confs = results.boxes.conf.cpu().numpy()
            # Обработка ключевых точек
            if results.keypoints:
                keypoints = results.keypoints.data.cpu().numpy()
                confs = results.keypoints.conf.cpu().numpy()
                for i, (class_id, box_conf, box, kp, conf) in enumerate(zip(classes, boxes_confs, boxes, keypoints, confs)):
                    class_name = classes_names[int(class_id)]
                    color = colors['lightblue']
                    x1, y1, x2, y2 = box
                    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                    # Визуализация ключевых точек
                    for j, (point, point_conf) in enumerate(zip(kp, conf)):
                        if point_conf > 0.7:
                            x, y = int(point[0]), int(point[1])
                            if (x, y) != (0, 0):
                                cv2.circle(image, (x, y), 5, colors['white'], -1)
                                # cv2.putText(image, str(j), (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors['white'], 2)
                    # Рисование скелета
                    draw_skeleton(image, kp, conf, [(6, 5), (5, 4), (4, 3), (3, 2), (2, 7), (7, 8), (8, 9), (9, 10)], colors['green'])  # Руки
                    draw_skeleton(image, kp, conf, [(16, 15), (15, 14), (14, 13), (13, 12), (12, 17), (17, 18), (18, 19), (19, 20)], colors['blue'])  # Ноги
                    draw_skeleton(image, kp, conf, [(2, 11), (11, 12)], colors['rose'])  # Тело
                    draw_skeleton(image, kp, conf, [(0, 1), (1, 2)], colors['red'])  # Голова
                return image
        else:
            return None

def process_video(input_path, output_path):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print("Ошибка: Не удалось открыть входное видео.")
        return
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'H264')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not out.isOpened():
        print("Ошибка: Не удалось открыть выходное видео для записи.")
        return
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        skeleton_frame = frame2skeleton(frame_rgb, model)
        if skeleton_frame is not None:
            skeleton_frame_bgr = cv2.cvtColor(skeleton_frame, cv2.COLOR_RGB2BGR)
            skeleton_frame_bgr = cv2.resize(skeleton_frame_bgr, (width, height)) 
            out.write(skeleton_frame_bgr)
    cap.release()
    out.release()
    print("Видео успешно обработано и сохранено в", output_path)

# def process_video(input_path, output_path):
#     cap = cv2.VideoCapture(input_path)
#     if not cap.isOpened():
#         print("Ошибка: Не удалось открыть входное видео.")
#         return
#     fps = int(cap.get(cv2.CAP_PROP_FPS))
#     width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#     height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#     fourcc = cv2.VideoWriter_fourcc(*'H264')
#     out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
#     if not out.isOpened():
#         print("Ошибка: Не удалось открыть выходное видео для записи.")
#         return
#     while cap.isOpened():
#         ret, frame = cap.read()
#         if not ret:
#             break
#         results = model(frame)
#         annotated_frame = results[0].plot()
#         out.write(annotated_frame)
#     cap.release()
#     out.release()
#     print("Видео успешно обработано и сохранено в", output_path)

@app.route('/athlete/<int:athlete_id>')
def get_athlete_elements(athlete_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Исправленный запрос с добавлением недостающих полей
    cursor.execute(
        '''
        SELECT 
            athlete_surname, 
            athlete_name, 
            athlete_patronymic, 
            group_id, 
            birth_date,
            photo, 
            category,
            phone_number
        FROM athletes 
        WHERE athlete_id = %s
        ''',
        (athlete_id,)
    )
    athlete = cursor.fetchone()
    group_id = athlete[3]

    # Получаем имя группы
    cursor.execute('SELECT group_name FROM groups WHERE group_id = %s', (group_id,))
    group_name = cursor.fetchone()[0] if group_id else None

    # Получаем имя тренера
    coach_name = None
    if group_id:
        cursor.execute('''
            SELECT c.coach_surname, c.coach_name, c.coach_patronymic 
            FROM coaches c 
            JOIN groups g ON c.coach_id = g.coach_id 
            WHERE g.group_id = %s
        ''', (group_id,))
        coach_data = cursor.fetchone()
        if coach_data:
            coach_name = f"{coach_data[0]} {coach_data[1]} {coach_data[2] or ''}"

    # Получаем попытки выполнения элементов
    cursor.execute(
        '''
        SELECT e.element_id, e.element_name, v.training_date, v.video_path
        FROM video v
        JOIN elements e ON v.element_id = e.element_id
        WHERE v.athlete_id = %s
        ORDER BY e.element_name, v.training_date desc
        ''',
        (athlete_id,)
    )
    attempts = cursor.fetchall()

    # Формируем структуру данных для элементов
    elements = {}
    unique_dates = set()
    for element_id, element_name, training_date, video_path in attempts:
        if element_id not in elements:
            elements[element_id] = {'name': element_name, 'attempts': []}
        elements[element_id]['attempts'].append({
            'training_date': training_date.strftime('%Y-%m-%d'),
            'video_path': video_path
        })
        unique_dates.add(training_date.strftime('%Y-%m-%d'))

    conn.close()
    
    return render_template(
        'athlete1.html', 
        athlete=athlete, 
        elements=elements, 
        athlete_id=athlete_id, 
        group_id=group_id,
        group_name=group_name,
        coach_name=coach_name,
        unique_dates=list(unique_dates)
    )

@app.route('/athlete/<int:athlete_id>/dates/<date>')
def get_athlete_elements_by_date(athlete_id, date):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''
        SELECT e.element_id, e.element_name, v.training_date, v.video_path
        FROM video v
        JOIN elements e ON v.element_id = e.element_id
        WHERE v.athlete_id = %s AND v.training_date = %s
        ORDER BY e.element_name
        ''',
        (athlete_id, date)
    )
    attempts = cursor.fetchall()

    conn.close()

    # Структурируем данные в словарь
    elements = {}
    for element_id, element_name, training_date, video_path in attempts:
        if element_id not in elements:
            elements[element_id] = {'name': element_name, 'attempts': []}
        elements[element_id]['attempts'].append({
            'training_date': training_date.strftime('%Y-%m-%d'),
            'video_path': video_path
        })

    return jsonify([{'id': element_id, 'name': data['name'], 'attempts': data['attempts']} for element_id, data in elements.items()])

@app.route('/video/<int:athlete_id>/<int:element_id>/<training_date>')
def get_video(athlete_id, element_id, training_date):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем информацию о видео
    cursor.execute(
        '''
        SELECT 
            g.group_name,
            a.athlete_surname, 
            a.athlete_name,
            e.element_name,
            v.training_date,
            v.video_path
        FROM 
            video v
            JOIN athletes a 
            ON v.athlete_id = a.athlete_id
            JOIN groups g
            ON a.group_id = g.group_id
            JOIN elements e
            ON v.element_id = e.element_id
        WHERE 
            v.athlete_id = %s AND v.element_id = %s AND v.training_date = %s
        ''',
        (athlete_id, element_id, training_date)
    )
    video_paths = cursor.fetchall()

    conn.close()

    # Если видео найдено
    if video_paths:
        s = video_paths[0]
        return render_template(
            'upload1.html',
            filename=f"{s[0]}/{s[1]} {s[2]}/{s[3]}/{s[4]}/upload_{s[5]}",
            processed_filename=f"{s[0]}/{s[1]} {s[2]}/{s[3]}/{s[4]}/processed_{s[5]}",
            athlete_id=athlete_id 
        )

    return 'Видео не найдено', 404

@app.route('/video_athlete/<int:athlete_id>/<int:element_id>/<training_date>')
def get_video_athlete(athlete_id, element_id, training_date):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''
        SELECT 
            g.group_name,
            a.athlete_surname, 
            a.athlete_name,
            a.athlete_patronymic,  -- Добавляем отчество
            e.element_name,
            v.training_date,
            v.video_path
        FROM 
            video v
        JOIN 
            athletes a ON v.athlete_id = a.athlete_id
        JOIN 
            groups g ON a.group_id = g.group_id
        JOIN 
            elements e ON v.element_id = e.element_id
        WHERE 
            v.athlete_id = %s AND v.element_id = %s AND v.training_date = %s
        ''',
        (athlete_id, element_id, training_date)
    )
    video_paths = cursor.fetchall()
    conn.close()

    if video_paths:
        s = video_paths[0]
        training_date_obj = s[5]
        formatted_date = f"{training_date_obj.day} {months_ru[training_date_obj.month]} {training_date_obj.year}"
        
        # Формируем ФИО спортсмена
        athlete_fio = f"{s[1]} {s[2]} {s[3] if s[3] else ''}" 

        return render_template(
            'video_athlete.html',
            filename=f"{s[0]}/{s[1]} {s[2]}/{s[4]}/{s[5]}/upload_{s[6]}",
            processed_filename=f"{s[0]}/{s[1]} {s[2]}/{s[4]}/{s[5]}/processed_{s[6]}",
            athlete_id=athlete_id,
            element_name=s[4],
            training_date=formatted_date, 
            attempt_number=1,
            athlete_fio=athlete_fio  
        )
    return 'Видео не найдено', 404

@app.route('/athletes_by_group/<int:group_id>')
def get_athletes_by_group(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT athlete_id, athlete_surname, athlete_name FROM athletes WHERE group_id = %s',
        (group_id,)
    )
    athletes = cursor.fetchall()

    conn.close()

    # Возвращаем данные в формате JSON
    return jsonify([{
        'athlete_id': athlete[0],
        'athlete_surname': athlete[1],
        'athlete_name': athlete[2]
    } for athlete in athletes])

@app.route('/new_video', methods=['GET', 'POST'])
@app.route('/new_video/<int:group_id>/<int:athlete_id>', methods=['GET', 'POST'])
def new_video(group_id=None, athlete_id=None):
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        # Извлекаем данные из формы
        group_id = request.form['group_id']
        athlete_id = request.form['athlete_id']
        element_id = request.form['element_id']
        training_date = request.form['training_date']
        original_video = request.files['original_video']
        # Проверка для тренера: может ли он загружать видео для этой группы
        if session['role'] == 'coach':
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT c.coach_id 
                FROM coaches c 
                JOIN passwords p ON p.password_id = c.password_id
                WHERE p.username = %s
            """, (session['username'],))
            coach_id = cur.fetchone()[0]

            cur.execute('SELECT group_id FROM groups WHERE coach_id = %s AND group_id = %s ORDER BY group_name ASC', (coach_id, group_id))
            if not cur.fetchone():
                flash('Вы не можете загружать видео для этой группы', 'error')
                return redirect(url_for('new_video'))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT group_name FROM groups WHERE group_id = %s', (group_id,))
        group_name = cursor.fetchall()[0][0]

        cursor.execute('SELECT athlete_surname, athlete_name, athlete_patronymic FROM athletes WHERE athlete_id = %s', (athlete_id,))
        athlete = cursor.fetchall()[0]
        athlete_surname = athlete[0]
        athlete_name = athlete[1]
        athlete_patronymic = athlete[2] if athlete[2] else None  # Отчество может быть None

        cursor.execute('SELECT element_name FROM elements WHERE element_id = %s', (element_id,))
        element_name = cursor.fetchall()[0][0]

        original_video_path = f"static/{group_name}/{athlete_surname} {athlete_name}/{element_name}/{training_date}/upload_1.mp4"
        os.makedirs(os.path.dirname(original_video_path), exist_ok=True)

        if os.path.exists(original_video_path):
            original_video_path = f"{original_video_path[:-5]}{int(original_video_path[-5]) + 1}.mp4"
        original_video.save(original_video_path)

        slowed_path = f"static/{group_name}/{athlete_surname} {athlete_name}/{element_name}/{training_date}/slowed_1.mp4"
        if os.path.exists(slowed_path):
            slowed_path = f"{slowed_path[:-5]}{int(slowed_path[-5]) + 1}.mp4"
        if not slow_video(original_video_path, slowed_path):
            return redirect(request.url)

        temp_path = "static/processed/1.mp4"
        process_video(slowed_path, temp_path)
        processed_path = f"static/{group_name}/{athlete_surname} {athlete_name}/{element_name}/{training_date}/processed_1.mp4"
        if os.path.exists(processed_path):
            processed_path = f"{processed_path[:-5]}{int(processed_path[-5]) + 1}.mp4"
        os.rename(temp_path, processed_path)

        # Вставляем данные в таблицу video
        cursor.execute(
            '''
            INSERT INTO video (athlete_id, element_id, training_date, video_path) 
            VALUES (%s, %s, %s, %s)
            ''', 
            (athlete_id, element_id, training_date, original_video_path.split('/')[-1][original_video_path.split('/')[-1].index('_') + 1:])
        )
        conn.commit()
        conn.close()

        # Передаем athlete, element_name и training_date в шаблон
        return render_template(
            'upload1.html', 
            filename=original_video_path[7:], 
            processed_filename=processed_path[7:], 
            athlete_id=athlete_id,
            athlete=[athlete_surname, athlete_name, athlete_patronymic],
            element_name=element_name, 
            training_date=training_date 
        )

    # Загружаем группы и элементы для отображения в форме
    conn = get_db_connection()
    cursor = conn.cursor()

    if session['role'] == 'coach':
        # Тренер видит только свои группы
        cursor.execute("""
            SELECT c.coach_id 
            FROM coaches c 
            JOIN passwords p ON p.password_id = c.password_id
            WHERE p.username = %s
        """, (session['username'],))
        coach_id = cursor.fetchone()[0]
        cursor.execute('SELECT group_id, group_name FROM groups WHERE coach_id = %s ORDER BY group_name ASC', (coach_id,))
    else:
        # Админ видит все группы
        cursor.execute('SELECT group_id, group_name FROM groups ')

    groups = cursor.fetchall()

    cursor.execute('SELECT element_id, element_name FROM elements')
    elements = cursor.fetchall()

    # Если переданы group_id и athlete_id, загружаем соответствующих спортсменов
    if group_id and athlete_id:
        cursor.execute('SELECT athlete_id, athlete_surname, athlete_name FROM athletes WHERE group_id = %s AND athlete_id = %s', (group_id, athlete_id))
        athletes = cursor.fetchall()
    else:
        athletes = []

    conn.close()

    return render_template('add_video.html', groups=groups, elements=elements, group_id=group_id, athlete_id=athlete_id, athletes=athletes)

@app.route('/add_athlete', methods=['GET', 'POST'])
def add_athlete():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        group_id = request.form['group_id']
        surname = request.form['surname']
        name = request.form['name']
        patronymic = request.form.get('patronymic', '') or None
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Проверяем, существует ли уже такое имя пользователя
            cursor.execute('SELECT password_id FROM passwords WHERE username = %s', (username,))
            if cursor.fetchone():
                flash('Имя пользователя уже занято', 'error')
                return redirect(url_for('add_athlete'))

            # Сбрасываем последовательность, если она отстает
            cursor.execute("SELECT MAX(password_id) FROM passwords;")
            max_id = cursor.fetchone()[0] or 0 
            cursor.execute(f"SELECT setval('passwords_password_id_seq', {max_id + 1});")
            conn.commit()

            cursor.execute(
                'INSERT INTO passwords (username, password, role) VALUES (%s, %s, %s) RETURNING password_id',
                (username, password, 'athlete')
            )
            password_id = cursor.fetchone()[0]

            cursor.execute(
                'INSERT INTO athletes (group_id, athlete_surname, athlete_name, athlete_patronymic, password_id) VALUES (%s, %s, %s, %s, %s) RETURNING athlete_id',
                (group_id, surname, name, patronymic, password_id)
            )
            athlete_id = cursor.fetchone()[0]

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Ошибка: {e}") 
        finally:
            conn.close()

        return redirect(url_for('admin_dashboard'))
    
    # Загружаем группы для отображения в форме
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT group_id, group_name FROM groups ORDER BY group_name')
    groups = cursor.fetchall()
    conn.close()
    
    return render_template('add_athlete.html', groups=groups)

@app.route('/add_group', methods=['GET', 'POST'])
def add_group():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        group_name = request.form['group_name']
        coach_id = request.form['coach_id']
        athletes = request.form.getlist('athletes[]')  
        surnames = request.form.getlist('surname[]') 
        names = request.form.getlist('name[]') 
        patronymics = request.form.getlist('patronymic[]') 
        usernames = request.form.getlist('username[]')
        passwords = request.form.getlist('password[]') 

        # Проверка на уникальность названия группы
        cursor.execute('SELECT group_id FROM groups WHERE group_name = %s', (group_name,))
        if cursor.fetchone():
            return redirect(url_for('add_group'))

        # Проверка, что группа не создается без спортсменов
        if not athletes and not surnames:
            return redirect(url_for('add_group'))

        try:
            cursor.execute(
                'INSERT INTO groups (group_name, coach_id) VALUES (%s, %s) RETURNING group_id',
                (group_name, coach_id)
            )
            group_id = cursor.fetchone()[0]

            for athlete_id in athletes:
                cursor.execute(
                    'UPDATE athletes SET group_id = %s WHERE athlete_id = %s',
                    (group_id, athlete_id)
                )

            for surname, name, patronymic, username, password in zip(surnames, names, patronymics, usernames, passwords):
                cursor.execute(
                    'INSERT INTO passwords (username, password, role) VALUES (%s, %s, %s) RETURNING password_id',
                    (username, password, 'athlete')
                )
                password_id = cursor.fetchone()[0]

                cursor.execute(
                    'INSERT INTO athletes (group_id, athlete_surname, athlete_name, athlete_patronymic, password_id) VALUES (%s, %s, %s, %s, %s)',
                    (group_id, surname, name, patronymic, password_id)
                )

            conn.commit()
            return redirect(url_for('groups'))
        except Exception as e:
            conn.rollback()
            print(f"Ошибка: {e}")
        finally:
            conn.close()

        return redirect(url_for('admin_dashboard'))

    # Получаем список тренеров
    cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches')
    coaches = cursor.fetchall()

    # Получаем список спортсменов, которые не состоят в группах
    cursor.execute('SELECT athlete_id, athlete_surname, athlete_name FROM athletes WHERE group_id IS NULL')
    athletes = cursor.fetchall()

    conn.close()

    return render_template('add_group.html', coaches=coaches, athletes=athletes)

@app.route('/add_coach', methods=['GET', 'POST'])
def add_coach():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        surname = request.form['surname']
        name = request.form['name']
        patronymic = request.form.get('patronymic', '')
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Проверяем, существует ли уже такое имя пользователя
            cursor.execute('SELECT password_id FROM passwords WHERE username = %s', (username,))
            if cursor.fetchone():
                return redirect(url_for('add_coach'))

            cursor.execute("SELECT MAX(coach_id) FROM coaches;")
            max_coach_id = cursor.fetchone()[0] or 0 
            cursor.execute(f"SELECT setval('coaches_coach_id_seq', {max_coach_id + 1});")
            conn.commit()

            cursor.execute(
                'INSERT INTO passwords (username, password, role) VALUES (%s, %s, %s) RETURNING password_id',
                (username, password, 'coach')
            )
            password_id = cursor.fetchone()[0]

            cursor.execute(
                'INSERT INTO coaches (coach_surname, coach_name, coach_patronymic, password_id) VALUES (%s, %s, %s, %s) RETURNING coach_id',
                (surname, name, patronymic, password_id)
            )
            coach_id = cursor.fetchone()[0]

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Ошибка: {e}")
        finally:
            conn.close()

        return redirect(url_for('add_group'))
    
    return render_template('add_coach.html')
    
@app.route('/delete_athlete/<int:athlete_id>', methods=['POST'])
def delete_athlete(athlete_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT password_id FROM athletes WHERE athlete_id = %s', (athlete_id,))
        result = cursor.fetchone()
        
        if result:
            password_id = result[0]
            cursor.execute('DELETE FROM video WHERE athlete_id = %s', (athlete_id,))

            cursor.execute('DELETE FROM athletes WHERE athlete_id = %s', (athlete_id,))

            cursor.execute('DELETE FROM passwords WHERE password_id = %s', (password_id,))

            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Ошибка: {e}") 
    finally:
        conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/delete_group/<int:group_id>', methods=['POST'])
def delete_group(group_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('DELETE FROM athletes WHERE group_id = %s', (group_id,))

        cursor.execute('DELETE FROM groups WHERE group_id = %s', (group_id,))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
    finally:
        conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/edit_athlete/<int:athlete_id>', methods=['GET', 'POST'])
def edit_athlete(athlete_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        surname = request.form['surname']
        name = request.form['name']
        patronymic = request.form.get('patronymic', '') or None
        group_id = request.form['group_id']

        try:
            cursor.execute(
                'UPDATE athletes SET athlete_surname = %s, athlete_name = %s, athlete_patronymic = %s, group_id = %s WHERE athlete_id = %s',
                (surname, name, patronymic, group_id, athlete_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            conn.close()

        return redirect(url_for('admin_dashboard'))  # Изменено с 'groups' на 'admin_dashboard'

    cursor.execute('SELECT athlete_surname, athlete_name, athlete_patronymic, group_id FROM athletes WHERE athlete_id = %s', (athlete_id,))
    athlete = cursor.fetchone()

    cursor.execute('SELECT group_id, group_name FROM groups')
    groups = cursor.fetchall()

    conn.close()

    return render_template('edit_athlete.html', athlete=athlete, groups=groups, athlete_id=athlete_id)

# @app.route('/edit_coach/<int:coach_id>', methods=['GET', 'POST'])
# def edit_coach(coach_id):
#     if 'username' not in session or session['role'] != 'admin':
#         return redirect(url_for('auth.login'))

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     if request.method == 'POST':
#         surname = request.form['surname']
#         name = request.form['name']
#         patronymic = request.form.get('patronymic', '') or None

#         try:
#             cursor.execute(
#                 'UPDATE coaches SET coach_surname = %s, coach_name = %s, coach_patronymic = %s WHERE coach_id = %s',
#                 (surname, name, patronymic, coach_id)
#             )
#             conn.commit()
#             flash('Данные тренера успешно обновлены', 'success')
#         except Exception as e:
#             conn.rollback()
#             flash(f'Ошибка при обновлении данных тренера: {str(e)}', 'error')
#         finally:
#             conn.close()

#         return redirect(url_for('admin_dashboard'))  # Изменено с 'groups' на 'admin_dashboard'

#     cursor.execute('SELECT coach_surname, coach_name, coach_patronymic FROM coaches WHERE coach_id = %s', (coach_id,))
#     coach = cursor.fetchone()
#     conn.close()
    
#     return render_template('edit_coach.html', coach=coach, coach_id=coach_id)

@app.route('/edit_coach/<int:coach_id>', methods=['GET', 'POST'])
def edit_coach(coach_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        surname = request.form['surname']
        name = request.form['name']
        patronymic = request.form.get('patronymic', '') or None
        phone = request.form.get('phone', '') or None

        try:
            cursor.execute(
                '''
                UPDATE coaches 
                SET 
                    coach_surname = %s,
                    coach_name = %s,
                    coach_patronymic = %s,
                    phone_number = %s
                WHERE coach_id = %s
                ''',
                (surname, name, patronymic, phone, coach_id)
            )
            conn.commit()
            flash('Данные тренера успешно обновлены', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка при обновлении данных: {str(e)}', 'error')
        finally:
            conn.close()

        return redirect(url_for('view_coach', coach_id=coach_id))

    # GET-запрос: показать форму
    cursor.execute('''
        SELECT 
            coach_surname, 
            coach_name, 
            coach_patronymic,
            phone_number
        FROM coaches 
        WHERE coach_id = %s
    ''', (coach_id,))
    coach = cursor.fetchone()
    conn.close()
    
    return render_template('edit_coach.html', 
                         coach=coach, 
                         coach_id=coach_id)

@app.route('/edit_group/<int:group_id>', methods=['GET', 'POST'])
def edit_group(group_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        group_name = request.form['group_name']
        coach_id = request.form['coach_id']
        try:
            cursor.execute(
                'UPDATE groups SET group_name = %s, coach_id = %s WHERE group_id = %s',
                (group_name, coach_id, group_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
        finally:
            conn.close()

        return redirect(url_for('admin_dashboard'))

    cursor.execute('SELECT group_name, coach_id FROM groups WHERE group_id = %s', (group_id,))
    group = cursor.fetchone()

    cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches')
    coaches = cursor.fetchall()

    conn.close()

    return render_template('edit_group.html', group=group, coaches=coaches, group_id=group_id)

@app.route('/delete_coach/<int:coach_id>', methods=['POST'])
def delete_coach(coach_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Удаляем тренера (группы будут переназначены через отдельный запрос)
        cursor.execute('DELETE FROM coaches WHERE coach_id = %s', (coach_id,))
        cursor.execute('DELETE FROM passwords WHERE password_id = (SELECT password_id FROM coaches WHERE coach_id = %s)', (coach_id,))
        conn.commit()
        flash('Тренер успешно удален', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка при удалении тренера: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/check-coach-groups/<int:coach_id>')
def check_coach_groups(coach_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT EXISTS(SELECT 1 FROM groups WHERE coach_id = %s)', (coach_id,))
    has_groups = cursor.fetchone()[0]
    conn.close()
    return jsonify({'has_groups': has_groups})

@app.route('/reassign_group', methods=['POST'])
def reassign_group():
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})

    data = request.get_json()
    group_id = data.get('group_id')
    new_coach_id = data.get('new_coach_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('UPDATE groups SET coach_id = %s WHERE group_id = %s', 
                     (new_coach_id, group_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conn.close()

@app.route('/reassign_all_groups/<int:coach_id>', methods=['POST'])
def reassign_all_groups(coach_id):
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})

    data = request.get_json()
    group_assignments = data.get('group_assignments', {})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Переназначаем все группы согласно переданным данным
        for group_id, new_coach_id in group_assignments.items():
            cursor.execute(
                'UPDATE groups SET coach_id = %s WHERE group_id = %s',
                (new_coach_id, group_id)
            )
        
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conn.close()

@app.route('/athlete/<int:athlete_id>/profile')
def athlete_profile(athlete_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT athlete_surname, athlete_name, athlete_patronymic, group_id, birth_date, photo, category FROM athletes WHERE athlete_id = %s',
        (athlete_id,)
    )
    athlete = cursor.fetchone()
    
    conn.close()
    
    return render_template('athlete_profile.html', athlete=athlete, athlete_id=athlete_id)

@app.route('/schedule')
def view_schedule():
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # В функции view_schedule() замените запрос на:
        cursor.execute('''
            SELECT 
                s.schedule_id,
                s.training_date,
                s.start_time,
                s.end_time,
                s.training_type,
                s.location,
                c.coach_surname || ' ' || c.coach_name as coach_name,
                g.group_name,
                a.athlete_surname || ' ' || a.athlete_name as athlete_name
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            ORDER BY s.training_date, s.start_time
        ''')
        schedule = cursor.fetchall()
    except Exception as e:
        print(f"Ошибка при выполнении запроса: {e}")
        schedule = []
    finally:
        conn.close()
    
    return render_template('schedule.html', schedule=schedule)

@app.route('/schedule/add', methods=['POST'])
def add_schedule():
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    conn = None
    try:
        data = request.get_json()
        
        # Проверка обязательных полей
        required_fields = ['training_type', 'coach_id', 'location', 
                         'training_date', 'start_time', 'end_time']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Поле {field} обязательно'}), 400

        # Преобразование location
        location_mapping = {'лед': 'ice', 'зал': 'hall', 'другое': 'other'}
        location = location_mapping.get(data['location'], data['location'])

        conn = get_db_connection()
        cursor = conn.cursor()

        # Сначала получаем следующее значение sequence
        cursor.execute("SELECT setval('schedule_schedule_id_seq', (SELECT MAX(schedule_id) FROM schedule) + 1);")
        next_id = cursor.fetchone()[0]
        
        # Затем выполняем вставку
        cursor.execute('''
            INSERT INTO schedule (
                schedule_id, training_type, location, coach_id,
                training_date, start_time, end_time,
                group_id, athlete_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING schedule_id
        ''', (
            next_id,  # Используем полученное значение sequence
            data['training_type'],
            location,
            data['coach_id'],
            data['training_date'],
            data['start_time'],
            data['end_time'],
            data.get('group_id'),
            data.get('athlete_id')
        ))
        
        inserted_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'id': inserted_id})
        
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/schedule/edit/<int:session_id>', methods=['GET', 'POST'])
def edit_schedule(session_id):
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    
    if session['role'] not in ['admin', 'coach']:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('week_schedule'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем данные о тренировке
        cursor.execute('''
            SELECT 
                s.*,
                c.coach_id,
                c.coach_surname,
                c.coach_name,
                g.group_name,
                a.athlete_name,
                a.athlete_surname
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            WHERE s.schedule_id = %s
            ORDER BY group_name ASC
        ''', (session_id,))
        
        training = cursor.fetchone()
        
        if not training:
            flash('Тренировка не найдена', 'error')
            return redirect(url_for('week_schedule'))
        
        # Получаем списки для выпадающих меню
        cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches')
        coaches = cursor.fetchall()
        
        cursor.execute('SELECT group_id, group_name FROM groups ORDER BY group_name ASC')
        groups = cursor.fetchall()
        
        cursor.execute('SELECT athlete_id, athlete_surname, athlete_name FROM athletes')
        athletes = cursor.fetchall()
        
        # Форматируем данные для шаблона
        training_data = {
            'id': training[0],
            'date': training[1].strftime('%Y-%m-%d'),
            'start_time': training[2].strftime('%H:%M'),
            'end_time': training[3].strftime('%H:%M'),
            'type': training[4],
            'location': training[5],
            'coach_id': training[6],
            'group_id': training[7],
            'athlete_id': training[8],
            'coach_name': f"{training[10]} {training[11]}" if training[10] else None,
            'group_name': training[12],
            'athlete_name': f"{training[14]} {training[13]}" if training[13] else None
        }
        
        return render_template('edit_training.html',
                            training=training_data,
                            coaches=coaches,
                            groups=groups,
                            athletes=athletes)
        
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('week_schedule'))
    finally:
        conn.close()

@app.route('/check-auth')
def check_auth():
    if 'username' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'role': session.get('role')})

@app.route('/schedule/calendar-data')
def schedule_calendar_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                s.schedule_id,
                s.training_date,
                s.start_time,
                s.end_time,
                s.training_type,
                s.location,
                c.coach_surname || ' ' || c.coach_name as coach_name,
                g.group_name,
                a.athlete_surname || ' ' || a.athlete_name as athlete_name
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            ORDER BY s.training_date, group_name ASC
        ''')
        
        schedule = cursor.fetchall()
        
        events = []
        for event in schedule:
            # Преобразуем дату и время в строки
            training_date = event[1].strftime('%Y-%m-%d')
            start_time = event[2].strftime('%H:%M:%S') if event[2] else '00:00:00'
            end_time = event[3].strftime('%H:%M:%S') if event[3] else '00:00:00'
            
            events.append({
                'id': event[0],
                'title': event[7] if event[4] == 'group' else event[8],
                'start': f"{training_date}T{start_time}",
                'end': f"{training_date}T{end_time}",
                'color': '#3a87ad' if event[4] == 'group' else '#5b964a',
                'extendedProps': {
                    'description': f"Тренер: {event[6]}\nМесто: {event[5]}"
                }
            })
            
        return jsonify(events)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify([])
    finally:
        conn.close()

def get_day_of_week(date_str):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    return days[date_obj.weekday()]

app.jinja_env.globals.update(get_day_of_week=get_day_of_week)

def group_events_by_time(events):
    time_slots = {}
    for event in events:
        if event['start_time'] not in time_slots:
            time_slots[event['start_time']] = []
        time_slots[event['start_time']].append(event)
    return [{'time': time, 'events': events} for time, events in time_slots.items()]

app.jinja_env.globals.update(group_events_by_time=group_events_by_time)

@app.route('/schedule/week-view')
def week_schedule():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем текущую неделю
        today = datetime.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # Получаем информацию о группах спортсменов
        cursor.execute('''
            SELECT a.athlete_id, g.group_id, g.group_name 
            FROM athletes a
            LEFT JOIN groups g ON a.group_id = g.group_id
            ORDER BY group_name asc
        ''')
        athlete_groups = {row[0]: {'group_id': row[1], 'group_name': row[2]} for row in cursor.fetchall()}

        # Получаем расписание с дополнительной информацией
        cursor.execute('''
            SELECT 
                s.schedule_id,
                TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
                TO_CHAR(s.start_time, 'HH24:MI') AS start_time,
                TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
                s.training_type,
                s.location,
                c.coach_surname || ' ' || c.coach_name as coach_name,
                g.group_name,
                a.athlete_surname || ' ' || a.athlete_name as athlete_name,
                a.athlete_id,
                g.group_id as schedule_group_id,
                a.group_id as athlete_group_id
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id OR (s.athlete_id IS NOT NULL AND g.group_id = (SELECT group_id FROM athletes WHERE athlete_id = s.athlete_id))
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            ORDER BY s.training_date, s.start_time, group_name ASC
        ''')

        schedule = cursor.fetchall()

        # Формируем структуру дней
        days = {}
        current_day = start_of_week
        while current_day <= end_of_week:
            date_str = current_day.strftime('%Y-%m-%d')
            days[date_str] = []
            current_day += timedelta(days=1)

        # Заполняем тренировками
        for event in schedule:
            date = event[1]
            if date in days:
                athlete_id = event[9]
                athlete_group = athlete_groups.get(athlete_id, {})
                
                days[date].append({
                    'start_time': event[2],
                    'end_time': event[3],
                    'type': event[4],
                    'location': event[5],
                    'coach': event[6],
                    'group': event[7],
                    'athlete': event[8],
                    'id': event[0],
                    'athlete_id': athlete_id,
                    'group_id': event[10],
                    'athlete_group_id': athlete_group.get('group_id'),
                    'athlete_group_name': athlete_group.get('group_name')
                })

        # Получаем данные для фильтров
        cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches ORDER BY coach_surname, coach_name')
        coaches = cursor.fetchall()
        
        cursor.execute('SELECT group_id, group_name FROM groups ORDER BY group_name')
        all_groups = cursor.fetchall()
        
        cursor.execute('''
            SELECT a.athlete_id, a.athlete_surname, a.athlete_name, g.group_name 
            FROM athletes a
            LEFT JOIN groups g ON a.group_id = g.group_id
            ORDER BY a.athlete_surname, a.athlete_name
        ''')
        all_athletes = cursor.fetchall()

        return render_template('week_schedule.html', 
                        days=days,
                        coaches=coaches,
                        all_groups=all_groups,
                        all_athletes=all_athletes,
                        athlete_groups_json=json.dumps(athlete_groups))
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return str(e)
    finally:
        conn.close()

@app.route('/schedule/week-data')
def week_schedule_data():
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                s.schedule_id,
                TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
                TO_CHAR(s.start_time, 'HH24:MI') as start_time,
                TO_CHAR(s.end_time, 'HH24:MI') as end_time,
                s.training_type,
                s.location,
                CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
                COALESCE(g.group_name, ag.group_name) as group_name,
                CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name,
                s.group_id,
                a.athlete_id,
                a.group_id as athlete_group_id
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            LEFT JOIN groups ag ON a.group_id = ag.group_id
            WHERE s.training_date BETWEEN %s AND %s
            ORDER BY s.training_date, s.start_time
        ''', (start_date, end_date))
        
        schedule = cursor.fetchall()
        
        days = defaultdict(list)
        for event in schedule:
            date = event[1]
            days[date].append({
                'id': event[0],
                'start_time': event[2],
                'end_time': event[3],
                'type': event[4],
                'location': event[5],
                'coach': event[6],
                'group': event[7],
                'athlete': event[8],
                'group_id': event[9],
                'athlete_id': event[10],
                'athlete_group_id': event[11]
            })
        
        return jsonify({'days': days})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/schedule/update-coach/<int:session_id>', methods=['POST'])
def update_schedule_coach(session_id):
    if 'username' not in session or session['role'] not in ['admin', 'coach']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    
    new_coach_id = request.json.get('new_coach_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE schedule SET coach_id = %s 
            WHERE schedule_id = %s
        ''', (new_coach_id, session_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conn.close()


@app.route('/group/<int:group_id>/athletes')
def get_group_athletes(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT athlete_id, athlete_surname, athlete_name 
        FROM athletes 
        WHERE group_id = %s
        ORDER BY athlete_surname, athlete_name
    ''', (group_id,))
    
    athletes = [{
        'id': row[0],
        'surname': row[1],
        'name': row[2]
    } for row in cursor.fetchall()]
    
    conn.close()
    return jsonify(athletes)

@app.route('/schedule/update-location/<int:session_id>', methods=['POST'])
def update_schedule_location(session_id):
    if 'username' not in session or session['role'] not in ['admin', 'coach']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    
    new_location = request.json.get('new_location')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE schedule SET location = %s 
            WHERE schedule_id = %s
        ''', (new_location, session_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conn.close()

@app.route('/schedule/<int:session_id>/attendance', methods=['POST'])
def update_attendance(session_id):
    if 'username' not in session or session['role'] not in ['admin', 'coach']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        attendance_data = data.get('attendance', [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Удаляем старые записи о посещаемости для этой тренировки
        cursor.execute('DELETE FROM attendance WHERE schedule_id = %s', (session_id,))
        
        # Добавляем новые записи
        for record in attendance_data:
            cursor.execute('''
                INSERT INTO attendance (schedule_id, athlete_id, attended)
                VALUES (%s, %s, %s)
            ''', (session_id, record['athlete_id'], record['attended']))
        
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/schedule/<int:session_id>/attendance-info')
def get_attendance_info(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о тренировке
        cursor.execute('''
            SELECT s.group_id, s.training_date, g.group_name
            FROM schedule s
            LEFT JOIN groups g ON s.group_id = g.group_id
            WHERE s.schedule_id = %s
            ORDER BY group_name ASC
        ''', (session_id,))
        session_info = cursor.fetchone()
        
        if not session_info:
            return jsonify({'error': 'Тренировка не найдена'}), 404
        
        group_id, training_date, group_name = session_info
        
        # Проверяем, что тренировка уже прошла
        if datetime.strptime(training_date, '%Y-%m-%d').date() > datetime.today().date():
            return jsonify({'error': 'Тренировка еще не прошла'}), 400
        
        # Получаем список спортсменов группы
        cursor.execute('''
            SELECT a.athlete_id, a.athlete_surname, a.athlete_name
            FROM athletes a
            WHERE a.group_id = %s
            ORDER BY a.athlete_surname, a.athlete_name
        ''', (group_id,))
        athletes = cursor.fetchall()
        
        # Получаем информацию о посещаемости
        cursor.execute('''
            SELECT a.athlete_id, COALESCE(at.attended, FALSE) as attended
            FROM athletes a
            LEFT JOIN attendance at ON a.athlete_id = at.athlete_id AND at.schedule_id = %s
            WHERE a.group_id = %s
        ''', (session_id, group_id))
        attendance = {row[0]: row[1] for row in cursor.fetchall()}
        
        result = {
            'group_name': group_name,
            'training_date': training_date,
            'athletes': [{
                'id': athlete[0],
                'name': f"{athlete[1]} {athlete[2]}",
                'attended': attendance.get(athlete[0], False)
            } for athlete in athletes]
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/schedule/<int:session_id>/details')
def get_schedule_details(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                s.schedule_id,
                s.training_type,
                s.training_date,
                TO_CHAR(s.start_time, 'HH24:MI') as start_time,
                TO_CHAR(s.end_time, 'HH24:MI') as end_time,
                s.location,
                s.coach_id,
                s.group_id,
                s.athlete_id
            FROM schedule s
            WHERE s.schedule_id = %s
        ''', (session_id,))
        
        training = cursor.fetchone()
        
        if not training:
            return jsonify({'error': 'Тренировка не найдена'}), 404
            
        return jsonify({
            'id': training[0],
            'training_type': training[1],
            'training_date': training[2].strftime('%Y-%m-%d'),
            'start_time': training[3],
            'end_time': training[4],
            'location': training[5],
            'coach_id': training[6],
            'group_id': training[7],
            'athlete_id': training[8]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/schedule/update', methods=['POST'])
def update_schedule():
    if 'username' not in session or session['role'] not in ['admin', 'coach']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['id', 'training_type', 'coach_id', 'location', 
                          'training_date', 'start_time', 'end_time']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'Поле {field} обязательно'}), 400
        
        # Преобразуем русские значения location в английские
        location_mapping = {
            'лед': 'ice',
            'зал': 'hall',
            'другое': 'other'
        }
        location = location_mapping.get(data['location'], data['location'])
        
        # Проверяем, что указана либо группа, либо спортсмен в зависимости от типа
        if data['training_type'] == 'group' and not data.get('group_id'):
            return jsonify({'status': 'error', 'message': 'Для групповой тренировки укажите группу'}), 400
        if data['training_type'] == 'individual' and not data.get('athlete_id'):
            return jsonify({'status': 'error', 'message': 'Для индивидуальной тренировки укажите спортсмена'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE schedule SET
                training_type = %s,
                coach_id = %s,
                location = %s,
                training_date = %s,
                start_time = %s,
                end_time = %s,
                group_id = %s,
                athlete_id = %s
            WHERE schedule_id = %s
        ''', (
            data['training_type'],
            data['coach_id'],
            location,  # Используем преобразованное значение
            data['training_date'],
            data['start_time'],
            data['end_time'],
            data.get('group_id'),
            data.get('athlete_id'),
            data['id']
        ))
        
        conn.commit()
        return jsonify({'status': 'success'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/schedule/add', methods=['POST'])
def add_schedule_via_modal():
    if 'username' not in session or session['role'] not in ['admin', 'coach']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['training_type', 'coach_id', 'location', 
                          'training_date', 'start_time', 'end_time']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'Поле {field} обязательно'}), 400
        
        # Проверяем, что указана либо группа, либо спортсмен
        if data['training_type'] == 'group' and not data.get('group_id'):
            return jsonify({'status': 'error', 'message': 'Для групповой тренировки укажите группу'}), 400
        if data['training_type'] == 'individual' and not data.get('athlete_id'):
            return jsonify({'status': 'error', 'message': 'Для индивидуальной тренировки укажите спортсмена'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO schedule (
                training_type, location, coach_id,
                training_date, start_time, end_time,
                group_id, athlete_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['training_type'],
            data['location'],
            data['coach_id'],
            data['training_date'],
            data['start_time'],
            data['end_time'],
            data.get('group_id'),
            data.get('athlete_id')
        ))
        
        conn.commit()
        return jsonify({'status': 'success'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/delete_training/<int:training_id>', methods=['POST'])
def delete_training(training_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM schedule WHERE schedule_id = %s', (training_id,))
        conn.commit()
        return '', 204  # Успешно
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при удалении тренировки: {e}")
        return 'Ошибка при удалении тренировки', 500
    finally:
        conn.close()

@app.route('/attendance/<int:schedule_id>')
def get_attendance(schedule_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.athlete_id, a.athlete_surname, a.athlete_name, 
               COALESCE(at.present, false)
        FROM athletes a
        JOIN schedule s ON (a.group_id = s.group_id OR a.athlete_id = s.athlete_id)
        LEFT JOIN attendance at ON at.athlete_id = a.athlete_id AND at.schedule_id = %s
        WHERE s.schedule_id = %s
    ''', (schedule_id, schedule_id))

    data = cursor.fetchall()
    conn.close()

    return jsonify([{
        'athlete_id': row[0],
        'surname': row[1],
        'name': row[2],
        'present': row[3]
    } for row in data])
    
@app.route('/attendance/<int:schedule_id>', methods=['POST'])
def save_attendance(schedule_id):
    data = request.json  # список ID спортсменов, которые присутствовали
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # удалим старые отметки
        cursor.execute('DELETE FROM attendance WHERE schedule_id = %s', (schedule_id,))

        # вставим новые
        for athlete_id in data.get('present_ids', []):
            cursor.execute('INSERT INTO attendance (schedule_id, athlete_id, present) VALUES (%s, %s, TRUE)',
                           (schedule_id, athlete_id))

        conn.commit()
        return '', 204
    except Exception as e:
        conn.rollback()
        print(f"Ошибка сохранения посещаемости: {e}")
        return 'Ошибка сервера', 500
    finally:
        conn.close()

@app.route('/attendance/отметка/<int:schedule_id>')
def mark_attendance(schedule_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.athlete_id, a.athlete_surname, a.athlete_name, 
               COALESCE(at.present, false)
        FROM athletes a
        JOIN schedule s ON (a.group_id = s.group_id OR a.athlete_id = s.athlete_id)
        LEFT JOIN attendance at ON at.athlete_id = a.athlete_id AND at.schedule_id = %s
        WHERE s.schedule_id = %s
    ''', (schedule_id, schedule_id))

    athletes = cursor.fetchall()

    cursor.execute('''
        SELECT training_date, start_time, end_time
        FROM schedule
        WHERE schedule_id = %s
    ''', (schedule_id,))
    info = cursor.fetchone()

    conn.close()

    return render_template('attendance_mark.html', 
        schedule_id=schedule_id, 
        athletes=athletes,
        date=info[0],
        start=info[1],
        end=info[2])

@app.route('/group/<int:group_id>/schedule')
def group_schedule(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем расписание для конкретной группы (групповые и индивидуальные занятия участников этой группы)
    cursor.execute('''
        SELECT 
            s.schedule_id,
            TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
            TO_CHAR(s.start_time, 'HH24:MI') AS start_time,
            TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
            s.training_type,
            s.location,
            CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
            g.group_name,
            s.group_id,
            a.athlete_id,
            a.group_id AS athlete_group_id,
            CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name
        FROM schedule s
        LEFT JOIN coaches c ON s.coach_id = c.coach_id
        LEFT JOIN groups g ON s.group_id = g.group_id
        LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
        WHERE s.group_id = %s OR a.group_id = %s
    ''', (group_id, group_id))
    events = cursor.fetchall()

    # Получаем имя группы и тренера
    cursor.execute('''
        SELECT g.group_name, CONCAT(c.coach_surname, ' ', c.coach_name) 
        FROM groups g
        LEFT JOIN coaches c ON g.coach_id = c.coach_id
        WHERE g.group_id = %s
    ''', (group_id,))
    group_info = cursor.fetchone()
    group_name = group_info[0]
    coach_name = group_info[1]

    # Структурируем события по дням
    days = defaultdict(list)
    for row in events:
        days[row[1]].append({
            'id': row[0],
            'start_time': row[2],
            'end_time': row[3],
            'type': row[4],
            'location': row[5],
            'coach': row[6],
            'group': row[7],
            'group_id': row[8],
            'athlete_id': row[9],
            'athlete_group_id': row[10],
            'athlete': row[11],
        })

    # Получаем все группы и тренеров для фильтров
    cursor.execute('SELECT group_id, group_name FROM groups')
    all_groups = cursor.fetchall()
    cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches')
    coaches = cursor.fetchall()
    cursor.execute('SELECT athlete_id, athlete_surname, athlete_name FROM athletes')
    all_athletes = cursor.fetchall()

    conn.close()

    return render_template('group_schedule.html', 
                           days=days,
                           is_group_view=True,
                           group_id=group_id,
                           group_name=group_name,
                           coach_name=coach_name,
                           all_groups=all_groups,
                           coaches=coaches,
                           all_athletes=all_athletes,
                           athlete_groups_json=json.dumps({a[0]: {'athlete_surname': a[1], 'athlete_name': a[2]} for a in all_athletes}),
                           selected_group_id=group_id)  # Добавляем selected_group_id

@app.route('/athlete/<int:group_id>/schedule')
def athlete_schedule(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 
            s.schedule_id,
            TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
            TO_CHAR(s.start_time, 'HH24:MI') AS start_time,
            TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
            s.training_type,
            s.location,
            CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
            g.group_name,
            s.group_id,
            a.athlete_id,
            a.group_id AS athlete_group_id,
            CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name
        FROM schedule s
        LEFT JOIN coaches c ON s.coach_id = c.coach_id
        LEFT JOIN groups g ON s.group_id = g.group_id
        LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
        WHERE s.group_id = %s OR a.group_id = %s
    ''', (group_id, group_id))
    events = cursor.fetchall()

    # Получаем имя группы и тренера
    cursor.execute('''
        SELECT g.group_name, CONCAT(c.coach_surname, ' ', c.coach_name) 
        FROM groups g
        LEFT JOIN coaches c ON g.coach_id = c.coach_id
        WHERE g.group_id = %s
    ''', (group_id,))
    group_info = cursor.fetchone()
    group_name = group_info[0]
    coach_name = group_info[1]

    # Структурируем события по дням
    days = defaultdict(list)
    for row in events:
        days[row[1]].append({
            'id': row[0],
            'start_time': row[2],
            'end_time': row[3],
            'type': row[4],
            'location': row[5],
            'coach': row[6],
            'group': row[7],
            'group_id': row[8],
            'athlete_id': row[9],
            'athlete_group_id': row[10],
            'athlete': row[11],
        })

    # Получаем все группы и тренеров для фильтров
    cursor.execute('SELECT group_id, group_name FROM groups')
    all_groups = cursor.fetchall()
    cursor.execute('SELECT coach_id, coach_surname, coach_name FROM coaches')
    coaches = cursor.fetchall()
    cursor.execute('SELECT athlete_id, athlete_surname, athlete_name FROM athletes')
    all_athletes = cursor.fetchall()

    conn.close()

    return render_template('athlete_schedule.html', 
                           days=days,
                           is_group_view=True,
                           group_id=group_id,
                           group_name=group_name,
                           coach_name=coach_name,
                           all_groups=all_groups,
                           coaches=coaches,
                           all_athletes=all_athletes,
                           athlete_groups_json=json.dumps({a[0]: {'athlete_surname': a[1], 'athlete_name': a[2]} for a in all_athletes}),
                           selected_group_id=group_id)  # Добавляем selected_group_id

@app.route('/groups/<int:group_id>/attendance')
def group_attendance(group_id):
    # Получаем текущую неделю из параметра или используем текущую дату
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
    else:
        today = datetime.today().date()
        week_start = today - timedelta(days=today.weekday())
    
    week_end = week_start + timedelta(days=6)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем тренировки за выбранную неделю
    cursor.execute('''
        SELECT schedule_id, training_date, start_time, end_time
        FROM schedule
        WHERE group_id = %s 
        AND training_date BETWEEN %s AND %s
        ORDER BY training_date, start_time
    ''', (group_id, week_start, week_end))
    trainings = cursor.fetchall()

    # Получаем спортсменов группы
    cursor.execute('''
        SELECT athlete_id, athlete_surname, athlete_name, athlete_patronymic
        FROM athletes
        WHERE group_id = %s
        ORDER BY athlete_surname, athlete_name
    ''', (group_id,))
    athletes = cursor.fetchall()

    # Получаем данные о посещаемости
    attendance_data = {}
    attendance_count = defaultdict(int)
    
    if trainings:
        training_ids = [t[0] for t in trainings]
        cursor.execute('''
            SELECT athlete_id, schedule_id
            FROM attendance
            WHERE schedule_id IN %s AND present = TRUE
        ''', (tuple(training_ids),))
        
        for athlete_id, schedule_id in cursor.fetchall():
            attendance_data[(athlete_id, schedule_id)] = True
            attendance_count[athlete_id] += 1

    cursor.execute('SELECT group_name FROM groups WHERE group_id = %s', (group_id,))
    group_name = cursor.fetchone()[0]

    conn.close()

    # Даты для навигации по неделям
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    return render_template('group_attendance.html', 
                         group_name=group_name,
                         group_id=group_id,
                         week_start=week_start,
                         week_end=week_end,
                         prev_week=prev_week,
                         next_week=next_week,
                         trainings=trainings,
                         athletes=athletes,
                         attendance_data=attendance_data,
                         attendance_count=attendance_count,
                         athletes_count=len(athletes))


@app.route('/athlete/<int:athlete_id>/attendance')
def athlete_attendance(athlete_id):
    # Обработка параметров недели
    week_start_str = request.args.get('week_start')
    if week_start_str:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
    else:
        today = datetime.today().date()
        week_start = today - timedelta(days=today.weekday())
    
    week_end = week_start + timedelta(days=6)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Получаем данные о спортсмене
    cur.execute('''
        SELECT 
            a.athlete_surname, 
            a.athlete_name, 
            a.athlete_patronymic,
            a.photo,
            g.group_name,
            CONCAT(c.coach_surname, ' ', c.coach_name, ' ', COALESCE(c.coach_patronymic, '')) 
        FROM athletes a
        LEFT JOIN groups g ON a.group_id = g.group_id
        LEFT JOIN coaches c ON g.coach_id = c.coach_id
        WHERE a.athlete_id = %s
    ''', (athlete_id,))
    athlete_data = cur.fetchone()
    
    # Исправленный SQL-запрос
    cur.execute('''
        SELECT 
            s.training_date,
            s.start_time,
            s.end_time,
            s.location,
            COALESCE(at.present, FALSE) as present
        FROM schedule s
        LEFT JOIN attendance at 
            ON s.schedule_id = at.schedule_id 
            AND at.athlete_id = %s
        WHERE (
            s.group_id = (SELECT group_id FROM athletes WHERE athlete_id = %s)
            OR s.athlete_id = %s
        )
        AND s.training_date BETWEEN %s AND %s
        ORDER BY s.training_date DESC
    ''', (athlete_id, athlete_id, athlete_id, week_start, week_end))
    
    trainings = cur.fetchall()
    conn.close()

    attended_count = sum(1 for t in trainings if t[4])

    return render_template('athlete_attendance.html',
                         athlete_data=athlete_data,
                         trainings=trainings,
                         athlete_id=athlete_id,
                         week_start=week_start,
                         week_end=week_end,
                         prev_week=prev_week,
                         next_week=next_week,
                         attended_count=attended_count)

@app.route('/coach/groups/<int:group_id>/schedule')
@login_required
def coach_group_schedule(group_id):
    # Проверка что группа принадлежит тренеру
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT coach_id FROM groups WHERE group_id = %s", (group_id,))
    group_coach = cur.fetchone()[0]
      
    # Далее логика отображения расписания группы
    return render_template('group_schedule.html', ...)

@app.route('/coach/groups/<int:group_id>/attendance')
@login_required
def coach_group_attendance(group_id):
    # Логика отображения посещаемости
    return render_template('group_attendance.html', ...)

@app.route('/coach/schedule')
def coach_schedule():
    if 'username' not in session or session['role'] != 'coach':
        return redirect(url_for('auth.login'))
    
    username = session['username']
    conn = get_db_connection()
    cur = conn.cursor()

    # Получаем ID тренера
    cur.execute("""
        SELECT c.coach_id, c.coach_surname, c.coach_name, c.coach_patronymic,
               c.photo, c.phone_number 
        FROM coaches c 
        JOIN passwords p ON p.password_id = c.password_id
        WHERE p.username = %s
    """, (username,))
    coach_data = cur.fetchone()
    coach_id = coach_data[0]
    coach_info = {
        'name': f"{coach_data[1]} {coach_data[2]} {coach_data[3] or ''}",
        'photo': coach_data[4],
        'phone': coach_data[5]
    }

    # Получаем группы тренера
    cur.execute('''
        SELECT g.group_id, g.group_name 
        FROM groups g 
        WHERE g.coach_id = %s
        ORDER BY g.group_name
    ''', (coach_id,))
    groups = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    # Получаем текущую неделю
    # today = datetime.today()
    # start_of_week = today - timedelta(days=today.weekday())
    # end_of_week = start_of_week + timedelta(days=6)

    # Получаем расписание тренера
    cur.execute('''
            SELECT 
                s.schedule_id,
                TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
                TO_CHAR(s.start_time, 'HH24:MI') AS start_time,
                TO_CHAR(s.end_time, 'HH24:MI') AS end_time,
                s.training_type,
                s.location,
                CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
                g.group_name AS group_name,  -- Явный алиас
                s.group_id,
                a.athlete_id,
                CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name
            FROM schedule s
            LEFT JOIN coaches c ON s.coach_id = c.coach_id
            LEFT JOIN groups g ON s.group_id = g.group_id
            LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
            WHERE s.coach_id = %s 
            OR g.coach_id = %s 
            OR a.group_id IN (SELECT group_id FROM groups WHERE coach_id = %s)
        ''', (coach_id, coach_id, coach_id))
    schedule = cur.fetchall()

    # Формируем структуру дней
    # days = defaultdict(list)
    # current_day = start_of_week
    # while current_day <= end_of_week:
    #     date_str = current_day.strftime('%Y-%m-%d')
    #     days[date_str] = []
    #     current_day += timedelta(days=1)
    days = defaultdict(list)
    for event in schedule:
        date = event[1]
        days[date].append({
            'id': event[0],
            'start_time': event[2],
            'end_time': event[3],
            'type': event[4],
            'location': event[5],
            'coach': event[6],
            'group': event[7],
            'group_id': event[8],
            'athlete_id': event[9],
            'athlete': event[10]
        })

    conn.close()
    
    return render_template('coach_schedule.html', 
                         days=days,
                         coach_info=coach_info,
                         coach_id=coach_id,
                         groups=groups)

# @app.route('/schedule/coach-week-data')
# def coach_week_schedule_data():
#     start_date = request.args.get('start')
#     end_date = request.args.get('end')
#     coach_id = request.args.get('coach_id')
    
#     conn = get_db_connection()
#     cursor = conn.cursor()
    
#     try:
#         cursor.execute('''
#             SELECT 
#                 s.schedule_id,
#                 TO_CHAR(s.training_date, 'YYYY-MM-DD') AS training_date,
#                 TO_CHAR(s.start_time, 'HH24:MI') as start_time,
#                 TO_CHAR(s.end_time, 'HH24:MI') as end_time,
#                 s.training_type,
#                 s.location,
#                 CONCAT(c.coach_surname, ' ', c.coach_name) as coach_name,
#                 g.group_name,
#                 s.group_id,
#                 a.athlete_id,
#                 CONCAT(a.athlete_surname, ' ', a.athlete_name) as athlete_name
#             FROM schedule s
#             LEFT JOIN coaches c ON s.coach_id = c.coach_id
#             LEFT JOIN groups g ON s.group_id = g.group_id
#             LEFT JOIN athletes a ON s.athlete_id = a.athlete_id
#             WHERE s.coach_id = %s 
#             OR g.coach_id = %s 
#             OR a.group_id IN (SELECT group_id FROM groups WHERE coach_id = %s)
#             AND s.training_date BETWEEN %s AND %s
#             ORDER BY s.training_date, s.start_time
#         ''', (coach_id, coach_id, coach_id, start_date, end_date))
        
#         schedule = cursor.fetchall()
        
#         days = {}
#         for event in schedule:
#             date = event[1]
#             if date not in days:
#                 days[date] = []
                
#             days[date].append({
#                 'id': event[0],
#                 'start_time': event[2],
#                 'end_time': event[3],
#                 'type': event[4],
#                 'location': event[5],
#                 'coach': event[6],
#                 'group': event[7] if event[7] else None,
#                 'group_id': event[8] if event[8] else None,
#                 'athlete': event[10] if event[10] else None,
#                 'athlete_id': event[9] if event[9] else None
#             })
        
#         return jsonify({'days': days})
#     except Exception as e:
#         print(f"Ошибка: {e}")
#         return jsonify({'error': str(e)}), 500
#     finally:
#         conn.close()

@app.route('/coach/<int:coach_id>')
def view_coach(coach_id):
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT coach_id, coach_surname, coach_name, coach_patronymic, 
                   photo, phone_number
            FROM coaches 
            WHERE coach_id = %s
        ''', (coach_id,))
        coach_data = cursor.fetchone()
        coach_id = coach_data[0]
        coach_info = {
            'id': coach_data[0],  # Добавьте ID
            'name': f"{coach_data[1]} {coach_data[2]} {coach_data[3] or ''}",
            'photo': coach_data[4],
            'phone': coach_data[5]
        }
        print(coach_info)
        # Получаем группы, закрепленные за этим тренером
        cursor.execute('SELECT group_id, group_name FROM groups WHERE coach_id = %s', (coach_id,))
        groups = cursor.fetchall()

        # Получаем спортсменов по группам
        groups_with_athletes = []
        for group in groups:
            cursor.execute('SELECT athlete_id, athlete_surname, athlete_name, athlete_patronymic FROM athletes WHERE group_id = %s', 
                (group[0],))
            athletes = cursor.fetchall()
            groups_with_athletes.append({
                "id": group[0],
                "name": group[1],
                "athletes": athletes
            })

        cursor.close()
        conn.close()

        return render_template('coach1.html', groups=groups_with_athletes, coach_info=coach_info)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return redirect(url_for('admin_dashboard'))
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)