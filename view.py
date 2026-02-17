import flask
import requests
from sqlalchemy.sql.functions import count
from werkzeug.utils import redirect, secure_filename
import calendar
from werkzeug.security import generate_password_hash, check_password_hash
import tm_depart.get_departament
import tm_users.get_users
from application import app, db, allowed_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, flash, session, url_for, redirect, jsonify, Response, g, make_response, send_file
from model import *
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from datetime import datetime, timedelta, time as dtimeonly, date
from reportlab.lib.pagesizes import A4, A3, A2, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak  # Додано PageBreak
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
import hashlib, os, random, string, time
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, literal, desc, case, not_
from tm_auth import auth
from io import BytesIO
from reportlab.lib.units import inch
import smtplib
import pickle
from email.mime.text import MIMEText
from config import EXCLUDED_RECEIVER_CORRESPONDENTS
#from transliterate import translit



login_manager = LoginManager(app)
login_manager.login_view = 'login'


def check_access(access_level, permission):
    if access_level and permission:
        return access_level & permission != 0


def find_sequences(records):
    sequences = []
    current_sequence = None

    for record in records:
        if record.reason == "vacation":
            if current_sequence is None:
                current_sequence = {'start_date': record.today_date, 'end_date': record.today_date}
            else:
                # Перевірка, чи поточний запис є безпосередньо після останньої дати у поточній послідовності
                if (record.today_date - current_sequence['end_date']).days == 1:
                    current_sequence['end_date'] = record.today_date
                else:
                    # Закінчення поточної послідовності та початок нової
                    sequences.append(current_sequence)
                    current_sequence = {'start_date': record.today_date, 'end_date': record.today_date}
        else:
            if current_sequence is not None:
                sequences.append(current_sequence)
                current_sequence = None

    print(current_sequence)
    # Перевірка для останньої послідовності
    if current_sequence is not None:
        sequences.append(current_sequence)

    return sequences

@login_manager.user_loader
def load_user(user_id):
    # Повертає користувача за його ID
    return users.query.get(user_id)

@app.route('/')
def home_page():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()
    selcted_years = datetime.now().year

    return redirect(url_for('calendar_view'))

    departament_list = [user_info['user_departament_id']]
    companies = []

    # Отримання списку ідентифікаторів департаментів
    if 'departaments' in request.args:
        departament_list_str = request.args.get('departaments', '')
        # Приведення ідентифікаторів до типу int, якщо потрібно
        if departament_list_str:  # перевіряємо, чи рядок не пустий
            departament_list = [int(id) for id in
                                departament_list_str.split(',')]  # розділяємо рядок і конвертуємо кожен елемент
            departament_list.append(0)
        else:
            departament_list = []

    # Отримання списку ідентифікаторів компаній
    if 'companies' in request.args:
        companies_list_str = request.args.get('companies', '')
        # Приведення ідентифікаторів до типу int, якщо потрібно
        if companies_list_str:
            companies = [int(id) for id in companies_list_str.split(',')]
        else:
            companies = []

    print(departament_list, companies)

    current_month = datetime.now().month
    current_year = datetime.now().year
    first_day_of_current_month = datetime(current_year, current_month, 1)
    first_day_of_next_month = datetime(current_year, current_month + 1, 1) if current_month < 12 else datetime(
        current_year + 1, 1, 1)

    # Віднімання одного дня від першого дня наступного місяця для отримання останнього дня поточного місяця
    last_day_of_current_month = first_day_of_next_month - timedelta(days=1)
    if 'start' in request.args:
        first_day_of_current_month = datetime.strptime(request.args['start'], '%Y-%m-%d')
        last_day_of_current_month = datetime.strptime(request.args['end'], '%Y-%m-%d')
        selcted_years = last_day_of_current_month.year
    worked_fact = calendar_work.query.with_entities(func.sum(calendar_work.work_fact)) \
        .filter(and_(calendar_work.today_date >= first_day_of_current_month,
                     calendar_work.today_date <= last_day_of_current_month)) \
        .scalar()

    worked_plan = db.session.query(func.sum(calendar_work.work_time)) \
        .filter(and_(calendar_work.today_date >= first_day_of_current_month,
                     calendar_work.today_date <= last_day_of_current_month)) \
        .scalar()
    if not worked_plan:
        worked_plan = 0
    if not worked_fact:
        worked_fact = 0

    dashboard_info = {
        'count_users': db.session.query(func.count(users.id.distinct())).\
    join(calendar_work, users.id == calendar_work.user_id).\
    filter(users.display == 1).\
    filter(and_(
        calendar_work.today_date >= first_day_of_current_month,
        calendar_work.today_date <= last_day_of_current_month
    )).\
    scalar(),
        'count_departaments': departaments.query.count(),
        'count_worked_hours': worked_fact,
        'count_do_worked_hours': worked_fact - worked_plan
    }
    full_info = tm_users.get_users.Users(user_id).get_users_calendar_full_info(departament_list, companies,
                                   first_day_of_current_month, last_day_of_current_month)
    departaments_list = tm_depart.get_departament.Departaments().get_departaments_list()
    company_docs = tm_users.get_users.Users(user_id).get_list_companyes()
    users_info = sorted(full_info, key=lambda x: (x['sort'], x['num_in_list']))
    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True
    return render_template('dashboard.html', user_info=user_info, dashboard_info=dashboard_info,
                       full_info=users_info, start_date=first_day_of_current_month, end_date=last_day_of_current_month,
                           departaments_list=departaments_list, company_docs=company_docs, selcted_years=selcted_years,
                           vacation_report_access=vacation_report_access)

import logging

# Налаштування логування
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.route('/users', methods=['GET', 'POST'])
@login_required
def users_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        # Отримання даних з форми
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone1 = request.form.get('phone1')
        phone2 = request.form.get('phone2')
        birthdate = request.form.get('birthdate')
        join_date = request.form.get('join_date')
        gender = request.form.get('gender')
        department = request.form.getlist('department[]')
        company = request.form.get('company')
        dept_head = request.form.get('dept_head') == 'on'
        admin = request.form.get('admin') == 'on'

        fuel_consumption = request.form.get('fuel_consumption')  # Розхід палива (л/100 км)
        car_brand = request.form.get('car_brand')  # Марка авто
        fuel_types = request.form.getlist('fuel_types[]')

        access = 3
        if dept_head:
            access = 2
            users_departament.query.filter_by(user_id=user_id).delete()
            db.session.commit()

        if admin:
            access = 1

        hash_pwd = generate_password_hash(password)
        add_in_users = users(user_email=email, user_pass=hash_pwd, user_avatar='static/assets/images/users/avatar-2.jpg',
                             user_fullname=full_name, user_departament=department[0], phone_num_one=phone1,
                             phone_num_two=phone2, user_access=access, birthdate=birthdate, join_date=join_date,
                             gender=gender, company=company, display=1, user_num_list=0)
        db.session.add(add_in_users)
        db.session.commit()
        created_user_id = add_in_users.id
        for dep in department:
            print(dep, created_user_id)
            add_to_depart = users_departament(user_id=created_user_id, dep_id=dep)
            db.session.add(add_to_depart)
            db.session.commit()

        user_avto_cls = tm_users.get_users.UserAuto(created_user_id)
        if car_brand is not None and car_brand != '':
            user_avto_cls.insert_user_avto(car_brand, fuel_consumption, fuel_types, 0)

    if user_id == 11:
        user_list = user_class.get_list_users()
    else:
        user_list = user_class.get_list_users_departements()
    get_company_list = user_class.get_list_companyes()
    department_list = tm_depart.get_departament.Departaments().get_departaments_list()

    # Додаємо кількість днів роботи до user_list у форматі "X р. Y м. Z д."
    enhanced_user_list = []
    current_date = date.today()  # Поточна дата (30.04.2025)

    for user in user_list:
        user_dict = user.copy()  # Копіюємо словник користувача
        user_id = user.get('id')

        # Логування повного словника користувача
        logger.debug(f"Processing user {user_id}: {user.get('user_fullname')}, full dict: {user}")

        # Отримуємо дату приєднання з ключа 'join'
        join_date = user.get('join')
        logger.debug(f"Raw join_date for user {user_id}: {join_date} (type: {type(join_date)})")

        # Обробка join_date
        if join_date:
            if isinstance(join_date, str):
                try:
                    join_date = datetime.strptime(join_date, '%Y-%m-%d').date()
                except ValueError as e:
                    logger.error(f"Failed to parse join_date '{join_date}' for user {user_id}: {e}")
                    join_date = None
            elif isinstance(join_date, datetime):
                join_date = join_date.date()
            elif isinstance(join_date, date):
                pass  # Уже date, нічого не робимо
            else:
                logger.error(f"Unexpected join_date type for user {user_id}: {type(join_date)}")
                join_date = None
        else:
            # Якщо join_date відсутнє у словнику, пробуємо отримати з бази
            user_record = users.query.filter_by(id=user_id).first()
            join_date = user_record.join_date if user_record else None
            logger.debug(f"Fallback join_date from DB for user {user_id}: {join_date} (type: {type(join_date)})")

        # Зберігаємо join_date у словнику для консистентності
        user_dict['join_date'] = join_date
        logger.debug(f"Processed join_date for user {user_id}: {join_date}")

        # Розраховуємо кількість років, місяців і днів
        if join_date:
            end_date = current_date
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            try:
                days_worked = (end_date - join_date).days
                if days_worked >= 0:
                    years = days_worked // 365
                    remaining_days = days_worked % 365
                    months = remaining_days // 30
                    days = remaining_days % 30
                    user_dict['days_worked_formatted'] = f"{years} р. {months} м. {days} д."
                else:
                    user_dict['days_worked_formatted'] = "Немає"
            except TypeError as e:
                logger.error(f"Error calculating days_worked for user {user_id}: {e}")
                user_dict['days_worked_formatted'] = "Немає"
        else:
            user_dict['days_worked_formatted'] = "Немає"

        logger.debug(f"Formatted days worked for user {user_id}: {user_dict['days_worked_formatted']}")

        enhanced_user_list.append(user_dict)

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    return render_template('users/users_list.html',
                           user_info=user_info,
                           user_list=enhanced_user_list,
                           company_list=get_company_list,
                           department_list=department_list,
                           vacation_report_access=vacation_report_access)

@app.route('/users-all', methods=['GET', 'POST'])
@login_required
def users_all_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone1 = request.form.get('phone1')
        phone2 = request.form.get('phone2')
        birthdate = request.form.get('birthdate')
        join_date = request.form.get('join_date')
        gender = request.form.get('gender')
        department = request.form.getlist('department[]')
        company = request.form.get('company')
        dept_head = request.form.get('dept_head') == 'on'
        admin = request.form.get('admin') == 'on'

        access = 3
        if dept_head:
            access = 2
        if admin:
            access = 1

        hash_pwd = generate_password_hash(password)
        add_in_users = users(user_email=email, user_pass=hash_pwd,
                             user_avatar='static/assets/images/users/avatar-2.jpg',
                             user_fullname=full_name, user_departament=department[0], phone_num_one=phone1,
                             phone_num_two=phone2, user_access=access, birthdate=birthdate, join_date=join_date,
                             gender=gender, company=company, display=1)
        db.session.add(add_in_users)
        db.session.commit()
        created_user_id = add_in_users.id
        for dep in department:
            print(dep, created_user_id)
            add_to_depart = users_departament(user_id=created_user_id, dep_id=dep)
            db.session.add(add_to_depart)
            db.session.commit()

    get_company_list = user_class.get_list_companyes()
    user_list = user_class.get_all_list_users()
    department_list = tm_depart.get_departament.Departaments().get_departaments_list()

    # Додаємо дату звільнення та кількість днів роботи до user_list
    enhanced_user_list = []
    current_date = date.today()  # Поточна дата (30.04.2025)

    for user in user_list:
        user_dict = user.copy()  # Копіюємо словник користувача
        user_id = user.get('id')

        # Логування повного словника користувача
        logger.debug(f"Processing user {user_id}: {user.get('user_fullname')}, full dict: {user}")

        # Отримуємо дату звільнення
        dismissal_record = calendar_work.query.filter_by(
            user_id=user_id, reason='dripicons-tag-delete'
        ).first()
        dismissal_date = dismissal_record.today_date if dismissal_record else None
        user_dict['dismissal_date'] = dismissal_date
        logger.debug(f"Dismissal date for user {user_id}: {dismissal_date}")

        # Отримуємо дату приєднання з ключа 'join'
        join_date = user.get('join')
        logger.debug(f"Raw join_date for user {user_id}: {join_date} (type: {type(join_date)})")

        # Обробка join_date
        if join_date:
            if isinstance(join_date, str):
                try:
                    join_date = datetime.strptime(join_date, '%Y-%m-%d').date()
                except ValueError as e:
                    logger.error(f"Failed to parse join_date '{join_date}' for user {user_id}: {e}")
                    join_date = None
            elif isinstance(join_date, datetime):
                join_date = join_date.date()
            elif isinstance(join_date, date):
                pass  # Уже date, нічого не робимо
            else:
                logger.error(f"Unexpected join_date type for user {user_id}: {type(join_date)}")
                join_date = None
        else:
            user_record = users.query.filter_by(id=user_id).first()
            join_date = user_record.join_date if user_record else None
            logger.debug(f"Fallback join_date from DB for user {user_id}: {join_date} (type: {type(join_date)})")

        user_dict['join_date'] = join_date
        logger.debug(f"Processed join_date for user {user_id}: {join_date}")

        # Розраховуємо кількість днів роботи у форматі "X р. Y м. Z д."
        if join_date:
            end_date = dismissal_date if dismissal_date else current_date
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            try:
                days_worked = (end_date - join_date).days
                if days_worked >= 0:
                    years = days_worked // 365
                    remaining_days = days_worked % 365
                    months = remaining_days // 30
                    days = remaining_days % 30
                    user_dict['days_worked'] = f"{years} р. {months} м. {days} д."
                else:
                    user_dict['days_worked'] = "Немає"
            except TypeError as e:
                logger.error(f"Error calculating days_worked for user {user_id}: {e}")
                user_dict['days_worked'] = "Немає"
        else:
            user_dict['days_worked'] = "Немає"

        logger.debug(f"Formatted days worked for user {user_id}: {user_dict['days_worked']}")

        enhanced_user_list.append(user_dict)

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    return render_template('users/users_all_list.html',
                           user_info=user_info,
                           user_list=enhanced_user_list,
                           company_list=get_company_list,
                           department_list=department_list,
                           vacation_report_access=vacation_report_access)

@app.route('/users-mob', methods=['GET', 'POST'])
@login_required
def users_mob_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone1 = request.form.get('phone1')
        phone2 = request.form.get('phone2')
        birthdate = request.form.get('birthdate')
        join_date = request.form.get('join_date')
        gender = request.form.get('gender')
        department = request.form.getlist('department[]')
        company = request.form.get('company')
        dept_head = request.form.get('dept_head') == 'on'
        admin = request.form.get('admin') == 'on'

        access = 3
        if dept_head:
            access = 2
        if admin:
            access = 1

        hash_pwd = generate_password_hash(password)
        add_in_users = users(user_email=email, user_pass=hash_pwd,
                             user_avatar='static/assets/images/users/avatar-2.jpg',
                             user_fullname=full_name, user_departament=department[0], phone_num_one=phone1,
                             phone_num_two=phone2, user_access=access, birthdate=birthdate, join_date=join_date,
                             gender=gender, company=company, display=1)
        db.session.add(add_in_users)
        db.session.commit()
        created_user_id = add_in_users.id
        for dep in department:
            print(dep, created_user_id)
            add_to_depart = users_departament(user_id=created_user_id, dep_id=dep)
            db.session.add(add_to_depart)
            db.session.commit()

    get_company_list = user_class.get_list_companyes()
    user_list = user_class.get_mob_list_users()
    department_list = tm_depart.get_departament.Departaments().get_departaments_list()

    # Додаємо дату звільнення, кількість днів роботи та дні після звільнення до user_list
    enhanced_user_list = []
    current_date = date.today()  # Поточна дата (30.04.2025)

    for user in user_list:
        user_dict = user.copy()  # Копіюємо словник користувача
        user_id = user.get('id')

        # Логування повного словника користувача
        logger.debug(f"Processing user {user_id}: {user.get('user_fullname')}, full dict: {user}")

        # Отримуємо дату звільнення (мобілізації)
        dismissal_record = calendar_work.query.filter_by(
            user_id=user_id, reason='dripicons-crop'
        ).first()
        dismissal_date = dismissal_record.today_date if dismissal_record else None
        user_dict['dismissal_date'] = dismissal_date
        logger.debug(f"Dismissal date for user {user_id}: {dismissal_date}")

        # Отримуємо дату приєднання з ключа 'join'
        join_date = user.get('join')
        logger.debug(f"Raw join_date for user {user_id}: {join_date} (type: {type(join_date)})")

        # Обробка join_date
        if join_date:
            if isinstance(join_date, str):
                try:
                    join_date = datetime.strptime(join_date, '%Y-%m-%d').date()
                except ValueError as e:
                    logger.error(f"Failed to parse join_date '{join_date}' for user {user_id}: {e}")
                    join_date = None
            elif isinstance(join_date, datetime):
                join_date = join_date.date()
            elif isinstance(join_date, date):
                pass  # Уже date, нічого не робимо
            else:
                logger.error(f"Unexpected join_date type for user {user_id}: {type(join_date)}")
                join_date = None
        else:
            user_record = users.query.filter_by(id=user_id).first()
            join_date = user_record.join_date if user_record else None
            logger.debug(f"Fallback join_date from DB for user {user_id}: {join_date} (type: {type(join_date)})")

        user_dict['join_date'] = join_date
        logger.debug(f"Processed join_date for user {user_id}: {join_date}")

        # Розраховуємо кількість днів роботи у форматі "X р. Y м. Z д."
        if join_date:
            end_date = dismissal_date if dismissal_date else current_date
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            try:
                days_worked = (end_date - join_date).days
                if days_worked >= 0:
                    years = days_worked // 365
                    remaining_days = days_worked % 365
                    months = remaining_days // 30
                    days = remaining_days % 30
                    user_dict['days_worked'] = f"{years} р. {months} м. {days} д."
                else:
                    user_dict['days_worked'] = "Немає"
            except TypeError as e:
                logger.error(f"Error calculating days_worked for user {user_id}: {e}")
                user_dict['days_worked'] = "Немає"
        else:
            user_dict['days_worked'] = "Немає"
        logger.debug(f"Formatted days worked for user {user_id}: {user_dict['days_worked']}")

        # Розраховуємо кількість днів від дати звільнення до поточної дати у форматі "X р. Y м. Z д."
        if dismissal_date:
            if isinstance(dismissal_date, datetime):
                dismissal_date = dismissal_date.date()
            try:
                days_since_dismissal = (current_date - dismissal_date).days
                if days_since_dismissal >= 0:
                    years = days_since_dismissal // 365
                    remaining_days = days_since_dismissal % 365
                    months = remaining_days // 30
                    days = remaining_days % 30
                    user_dict['days_since_dismissal'] = f"{years} р. {months} м. {days} д."
                else:
                    user_dict['days_since_dismissal'] = "Немає"
            except TypeError as e:
                logger.error(f"Error calculating days_since_dismissal for user {user_id}: {e}")
                user_dict['days_since_dismissal'] = "Немає"
        else:
            user_dict['days_since_dismissal'] = "Немає"
        logger.debug(f"Formatted days since dismissal for user {user_id}: {user_dict['days_since_dismissal']}")

        enhanced_user_list.append(user_dict)

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    return render_template('users/users_all_list.html',
                           user_info=user_info,
                           user_list=enhanced_user_list,
                           company_list=get_company_list,
                           department_list=department_list,
                           vacation_report_access=vacation_report_access,
                           is_mob_page=True)


@app.route('/delete-user', methods=['POST'])
@login_required
def remove_user():
    if request.method == 'POST':
        # Отримання даних з форми
        user_id = request.form.get('user_id')
        date_deleted = request.form.get('date-remove')
        remove_reson = request.form.get('remove_reson')
        print(user_id, date_deleted, remove_reson)

        date_deleted = datetime.strptime(date_deleted, '%Y-%m-%d')

        # Додавання одного дня до дати видалення
        next_day = date_deleted + timedelta(days=1)

        add_user_in_removed_list = absens_from_work(user_id=user_id, date_remove=date_deleted, remove_reason=remove_reson)
        db.session.add(add_user_in_removed_list)

        users.query.filter_by(id=user_id).update(dict(display=0))
        calendar_work.query.filter(calendar_work.user_id==user_id, calendar_work.today_date>=date_deleted).delete()
        db.session.commit()

        add_calendar = calendar_work(today_date=date_deleted, user_id=int(user_id), work_fact=0,
                                     work_time=0, work_status=1, reason='dripicons-tag-delete')
        print('add_calendar')
        db.session.add(add_calendar)
        add_log = log_system(user_id=user_id, type_event=f'Видалив інформацію про користувача {user_id}')
        db.session.add(add_log)
        db.session.commit()
        db.session.close()
    return redirect(url_for('users_page'))


@app.route('/mobi-user', methods=['POST'])
@login_required
def mobi_user():
    if request.method == 'POST':
        # Отримання даних з форми
        user_id = request.form.get('user_id')
        date_deleted = request.form.get('date-remove')
        print(user_id, date_deleted)
        users.query.filter_by(id=user_id).update(dict(display=2))

        date_deleted = datetime.strptime(date_deleted, '%Y-%m-%d')

        # Додавання одного дня до дати видалення
        next_day = date_deleted + timedelta(days=1)

        calendar_work.query.filter(calendar_work.user_id==int(user_id), calendar_work.today_date>=date_deleted).delete()
        db.session.commit()
        add_calendar = calendar_work(today_date=date_deleted, user_id=int(user_id), work_fact=0,
                                     work_time=0, work_status=1, reason='dripicons-crop')
        db.session.add(add_calendar)
        db.session.commit()
        print('add_calendar')

        db.session.close()
    return redirect(url_for('users_page'))


@app.route('/api/user/<int:user_id>')
def get_user(user_id):
    user = tm_users.get_users.Users(user_id).get_user_info()  # Функція, яка отримує дані користувача з бази даних
    print(user)
    return jsonify(user)

@app.route('/departament-<int:departament_id>', methods=['GET', 'POST'])
@login_required
def update_users_position_in_departament(departament_id):
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        data = request.form.to_dict()
        print(data)  # Виведення даних для перевірки

        for key, position in data.items():
            if key.startswith('sort_order_'):
                user_id = int(key.split('_')[-1])  # Отримання ID користувача
                position = int(position)  # Перетворення позиції в число
                # Оновлення користувача в базі даних
                print(user_id, position)
                user_to_update = users.query.filter_by(id=user_id).update(dict(user_num_list=position))
                db.session.commit()

        return jsonify({'status': 'success', 'message': 'Дані успішно збережено!'})

    departaments_users = tm_depart.get_departament.Departaments().get_departaments_users_position(departament_id)
    return render_template('departaments/departament.html', user_info=user_info,
                           user_list=departaments_users, departament_id=departament_id)


@app.route('/departaments', methods=['GET', 'POST'])
@login_required
def users_departament_list_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        # Отримання даних з форми
        dep_name = request.form.get('dep-name')
        leader = request.form.get('leader')
        print(dep_name, leader)

        add_departament = departaments(dep_name=dep_name, leader=leader, sort_num=99)
        db.session.add(add_departament)
        users.query.filter_by(id=leader).update(dict(user_access=2))
        db.session.commit()
        db.session.close()
        return redirect(url_for('users_departament_list_page'))

    if user_id == 11:
        departament_list = tm_depart.get_departament.Departaments().get_departaments_list()
    else:
        departament_list = tm_depart.get_departament.Departaments().get_departaments_list_userdep(user_id)

    departaments_users = tm_depart.get_departament.Departaments().get_departaments_users()

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True
    return render_template('departaments/departaments.html', user_info=user_info,
                           departament_list=departament_list, user_list=departaments_users,
                           vacation_report_access=vacation_report_access)


@app.route('/fuel-report', methods=['GET', 'POST'])
@login_required
def fuel_report_page():
    from calendar import monthrange
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    selected_month = int(request.args.get('month', datetime.now().month))
    selected_year = int(request.args.get('year', datetime.now().year))

    months = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
              "Жовтень", "Листопад", "Грудень"]
    years = [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036, 2037, 2038, 2039, 2040]

    fuel_data = tm_users.get_users.UserAuto(user_id).get_fuel_report_info(selected_month, selected_year)
    extra_expenses = tm_users.get_users.UserAuto(user_id).get_comments_report_info(selected_month, selected_year)
    technoforum_data = tm_users.get_users.UserAuto(user_id).get_technoforum_report_info(selected_month, selected_year)
    print(technoforum_data)

    # Визначаємо початок і кінець періоду для середньої ціни
    today = date.today()
    month_start = date(selected_year, selected_month, 1)
    last_day_of_month = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    # Додаємо середню ціну та приблизні витрати для fuel_data
    for driver in fuel_data:
        fuel_type = driver['fuel_type']

        # Якщо це минулий місяць або рік, беремо ціни за весь місяць
        if selected_year < today.year or (selected_year == today.year and selected_month < today.month):
            price_period_start = month_start
            price_period_end = last_day_of_month
        # Якщо це поточний місяць, беремо ціни від початку місяця до сьогодні
        else:
            price_period_start = month_start
            price_period_end = today

        prices = fuel_price.query.filter(
            fuel_price.created_at.between(price_period_start, price_period_end),
            fuel_price.fuel_type == fuel_type
        ).all()

        if prices:
            avg_price = sum(p.price for p in prices) / len(prices)
        else:
            avg_price = 0.0

        driver['avg_fuel_price'] = avg_price
        driver['approx_cost'] = int(avg_price * driver['refueled_this_month']) if avg_price else 0  # Число, а не рядок

    # Додаємо середню ціну та приблизні витрати для technoforum_data
    for driver in technoforum_data:
        fuel_type = driver['fuel_type']

        # Якщо це минулий місяць або рік, беремо ціни за весь місяць
        if selected_year < today.year or (selected_year == today.year and selected_month < today.month):
            price_period_start = month_start
            price_period_end = last_day_of_month
        # Якщо це поточний місяць, беремо ціни від початку місяця до сьогодні
        else:
            price_period_start = month_start
            price_period_end = today

        prices = fuel_price.query.filter(
            fuel_price.created_at.between(price_period_start, price_period_end),
            fuel_price.fuel_type == fuel_type
        ).all()

        if prices:
            avg_price = sum(p.price for p in prices) / len(prices)
        else:
            avg_price = 0.0

        driver['avg_fuel_price'] = avg_price
        driver['approx_cost'] = int(avg_price * driver['refuel']) if avg_price else 0  # Використовуємо refuel як число

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    avg_price = db.session.query(
        fuel_price.fuel_type,
        func.avg(fuel_price.price).label("average_price")
    ).group_by(fuel_price.fuel_type).all()
    avg_price_dict = {fuel: round(price, 1) for fuel, price in avg_price}
    # Передаємо дату в функцію (наприклад, останній день обраного місяця або сьогодні для поточного)
    selected_date = last_day_of_month if (
                selected_year < today.year or (selected_year == today.year and selected_month < today.month)) else today
    avg_price_string = get_avg_fuel_prices_string(selected_date)
    return render_template('fuel/fuel-report.html', user_info=user_info, years=years,
                           vacation_report_access=vacation_report_access, months=months, fuel_data=fuel_data,
                           selected_month=selected_month, selected_year=selected_year, extra_expenses=extra_expenses,
                           avg_price='', technoforum_data=technoforum_data, avg_price_dict=avg_price_dict)

@app.template_filter('format_thousands')
def format_thousands(value):
    return "{:,}".format(int(value)).replace(",", " ")


@app.route('/download_fuel_report/<int:month>/<int:year>')
@login_required
def download_fuel_report(month, year):
    user = current_user
    user_id = user.id
    from calendar import monthrange
    # Отримуємо дані для основної таблиці
    fuel_data = tm_users.get_users.UserAuto(user_id).get_fuel_report_info(month, year)

    # Отримуємо дані для Технофоруму
    technoforum_data = tm_users.get_users.UserAuto(user_id).get_technoforum_report_info(month, year)

    # Отримуємо дані для додаткових витрат
    extra_expenses = tm_users.get_users.UserAuto(user_id).get_comments_report_info(month, year)

    # Додаємо середню ціну та приблизні витрати для fuel_data
    for driver in fuel_data:
        fuel_type = driver.get('fuel_type', '')
        today = date.today()
        last_5_days = [today - timedelta(days=i) for i in range(5)]

        if year < today.year or (year == today.year and month < today.month):
            last_day_of_month = date(year, month, monthrange(year, month)[1])
            last_5_days = [last_day_of_month - timedelta(days=i) for i in range(5)]

        prices = fuel_price.query.filter(
            fuel_price.created_at.in_(last_5_days),
            fuel_price.fuel_type == fuel_type
        ).all()

        if prices:
            avg_price = sum(p.price for p in prices) / len(prices)
        else:
            avg_price = 0.0

        driver['avg_fuel_price'] = avg_price
        driver['approx_cost'] = int(
            sum(t.get('price', 0) for t in driver.get('transactions', []))
        )

    # Додаємо середню ціну та приблизні витрати для technoforum_data
    for driver in technoforum_data:
        fuel_type = driver.get('fuel_type', '')
        today = date.today()
        last_5_days = [today - timedelta(days=i) for i in range(5)]

        if year < today.year or (year == today.year and month < today.month):
            last_day_of_month = date(year, month, monthrange(year, month)[1])
            last_5_days = [last_day_of_month - timedelta(days=i) for i in range(5)]

        prices = fuel_price.query.filter(
            fuel_price.created_at.in_(last_5_days),
            fuel_price.fuel_type == fuel_type
        ).all()

        if prices:
            avg_price = sum(p.price for p in prices) / len(prices)
        else:
            avg_price = 0.0

        driver['avg_fuel_price'] = avg_price
        driver['approx_cost'] = int(
            sum(t.get('price', 0) for t in driver.get('transactions', []))
        )

    # Реєстрація шрифту
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))

    # Налаштування PDF із альбомною орієнтацією
    month_names = {
        1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень", 6: "Червень",
        7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"
    }
    month_name = month_names[month]
    filename = f"fuel_report_{month_name}_{year}.pdf"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []

    # Стилі
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontName='DejaVuSans',
        fontSize=16,
        alignment=1,
        spaceAfter=12
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=14,
        alignment=1,
        spaceAfter=20
    )
    cell_style = ParagraphStyle(
        'Cell',
        fontName='DejaVuSans',
        fontSize=9,
        alignment=1,
        leading=10
    )
    header_style = ParagraphStyle(
        'Header',
        fontName='DejaVuSans',
        fontSize=10,
        alignment=1,
        leading=12,
        textColor=colors.black
    )
    total_style = ParagraphStyle(
        'Total',
        fontName='DejaVuSans',
        fontSize=10,
        alignment=1,
        leading=12,
        textColor=colors.black,
        fontWeight='bold'
    )

    # Заголовок
    header_title = f"Облік витрат пального по паливним карткам - {month_name} {year}"
    subtitle = "Дніпро-Сервіс"
    elements.append(Paragraph(header_title, title_style))
    elements.append(Paragraph(subtitle, subtitle_style))

    # Основна таблиця (Дніпро Скан Сервіс)
    headers = ["ПІБ", "км.", "Тип палива", "Залишок на початок, л", "Заправлено, л", "Норма на день, л",
               "Днів поїздок", "Витрати за місяць, л", "Додаткові витрати, л", "Залишок на кінець, л",
               "Приблизні витрати, грн"]
    table_data = [[Paragraph(h, header_style) for h in headers]]

    total_approx_cost = 0
    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWHEIGHT', (0, 0), (-1, 0), 40),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    for i, data in enumerate(fuel_data, start=1):
        formatted_approx_cost = "{:,}".format(int(data['approx_cost'])).replace(",", " ")
        row = [
            Paragraph(str(data.get("driver_name", "")), cell_style),
            Paragraph(str(data.get("distance", 0)), cell_style),
            Paragraph(str(data.get("fuel_type", "")), cell_style),
            Paragraph(str(data.get("start_balance", 0)), cell_style),
            Paragraph(str(data.get("refueled_this_month", 0)), cell_style),
            Paragraph(str(data.get("day_norm", 0)), cell_style),
            Paragraph(str(data.get("travel_days", 0)), cell_style),
            Paragraph(str(data.get("total_fuel_usage", 0)), cell_style),
            Paragraph(str(data.get("additional_fuel_usage", 0)), cell_style),
            Paragraph(str(data.get("end_balance", 0)), cell_style),
            Paragraph(formatted_approx_cost, cell_style)
        ]
        table_data.append(row)
        total_approx_cost += data['approx_cost']

        if data.get("end_balance", 0) > 0:
            table_styles.append(('BACKGROUND', (9, i), (9, i), colors.Color(1, 0.8, 0.8)))

    formatted_total = "{:,}".format(int(total_approx_cost)).replace(",", " ")
    total_row = [
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"Всього: {sum(d.get('refueled_this_month', 0) for d in fuel_data):.1f}", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"{formatted_total}", total_style)
    ]
    table_data.append(total_row)

    table = Table(table_data, colWidths=[100, 50, 70, 70, 70, 70, 70, 70, 70, 70, 90])
    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    # Таблиця Додаткові витрати
    elements.append(Paragraph("<br/><br/>", cell_style))  # Відступ
    elements.append(Paragraph("Додаткові витрати", title_style))

    extra_headers = ["ПІБ", "Дата", "Витрата, л", "Коментар"]
    extra_table_data = [[Paragraph(h, header_style) for h in extra_headers]]

    extra_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWHEIGHT', (0, 0), (-1, 0), 40),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    for data in extra_expenses:
        row = [
            Paragraph(str(data.get("driver_name", "")), cell_style),
            Paragraph(str(data.get("date", "")), cell_style),
            Paragraph(str(data.get("fuel_spent", 0)), cell_style),
            Paragraph(str(data.get("comment", "")), cell_style),
        ]
        extra_table_data.append(row)

    if not extra_expenses:
        extra_table_data.append([Paragraph("Немає записів про додаткові витрати", cell_style)])
        extra_styles.append(('SPAN', (0, 1), (-1, 1)))  # Об'єднуємо всі 4 колонки в рядку 1

    extra_table = Table(extra_table_data, colWidths=[200, 100, 70, 300])
    extra_table.setStyle(TableStyle(extra_styles))
    elements.append(extra_table)

    # Перехід на нову сторінку перед таблицею Технофорум
    elements.append(PageBreak())

    # Таблиця Технофорум
    elements.append(Paragraph("ТФ", title_style))

    technoforum_table_data = [[Paragraph(h, header_style) for h in headers]]
    technoforum_total_approx_cost = 0
    technoforum_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWHEIGHT', (0, 0), (-1, 0), 40),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    for i, data in enumerate(technoforum_data, start=1):
        formatted_approx_cost = "{:,}".format(int(data['approx_cost'])).replace(",", " ")
        row = [
            Paragraph(str(data.get("driver_name", "")), cell_style),
            Paragraph(str(data.get("distance", 0)), cell_style),
            Paragraph(str(data.get("fuel_type", "")), cell_style),
            Paragraph(str(data.get("start_balance", 0)), cell_style),
            Paragraph(str(data.get("refuel", 0)), cell_style),
            Paragraph(str(data.get("day_norm", 0)), cell_style),
            Paragraph(str(data.get("travel_days", 0)), cell_style),
            Paragraph(str(data.get("total_fuel_usage", 0)), cell_style),
            Paragraph(str(data.get("additional_fuel_usage", 0)), cell_style),
            Paragraph(str(data.get("end_balance", 0)), cell_style),
            Paragraph(formatted_approx_cost, cell_style)
        ]
        technoforum_table_data.append(row)
        technoforum_total_approx_cost += data['approx_cost']

        if data.get("end_balance", 0) > 0:
            technoforum_styles.append(('BACKGROUND', (9, i), (9, i), colors.Color(1, 0.8, 0.8)))

    technoforum_formatted_total = "{:,}".format(int(technoforum_total_approx_cost)).replace(",", " ")
    technoforum_total_row = [
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"Всього: {sum(d.get('refuel', 0) for d in technoforum_data):.1f}", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"Всього: {sum(d.get('travel_days', 0) for d in technoforum_data)}", cell_style),
        Paragraph(f"Всього: {sum(d.get('total_fuel_usage', 0) for d in technoforum_data):.1f}", cell_style),
        Paragraph(f"Всього: {sum(d.get('additional_fuel_usage', 0) for d in technoforum_data):.1f}", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"{technoforum_formatted_total}", total_style)
    ]
    technoforum_table_data.append(technoforum_total_row)

    technoforum_table = Table(technoforum_table_data, colWidths=[100, 50, 70, 70, 70, 70, 70, 70, 70, 70, 90])
    technoforum_table.setStyle(TableStyle(technoforum_styles))
    elements.append(technoforum_table)

    # Генерація PDF
    doc.build(elements)
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    buffer.close()
    response.mimetype = 'application/pdf'
    response.headers['Content-Disposition'] = f"inline; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"
    return response


@app.route('/fuel-cash-report', methods=['GET', 'POST'])
@login_required
def fuel_cash_report_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    selected_month = int(request.args.get('month', datetime.now().month))
    selected_year = int(request.args.get('year', datetime.now().year))

    months = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
              "Жовтень", "Листопад", "Грудень"]
    years = [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036, 2037, 2038, 2039, 2040]

    cash_fuel_data = tm_users.get_users.UserAuto(user_id).get_cash_fuel_report_info(selected_month, selected_year)

    # Додаємо логіку для підрахунку середньої вартості палива
    for data in cash_fuel_data:
        fuel_type = data['fuel_type']
        today = datetime.now().date()
        last_5_days = [today - timedelta(days=i) for i in range(5)]

        # Визначаємо, які 5 днів брати (останні 5 днів місяця або від сьогодні)
        if selected_year < today.year or (selected_year == today.year and selected_month < today.month):
            from datetime import date
            # Для попереднього місяця беремо останні 5 днів цього місяця
            last_day_of_month = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])
            last_5_days = [last_day_of_month - timedelta(days=i) for i in range(5)]

        # Отримуємо ціни за останні 5 днів
        prices = fuel_price.query.filter(
            fuel_price.created_at.in_(last_5_days),
            fuel_price.fuel_type == fuel_type
        ).all()
        print(prices, last_5_days)
        if prices:
            avg_price = sum(p.price for p in prices) / len(prices)
        else:
            avg_price = 0.0  # Якщо даних немає, ставимо 0

        data['avg_fuel_price'] = avg_price
        data['total_cost'] = int(avg_price * data['total_fuel_usage']) if avg_price else 0

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    from datetime import date
    today = date.today()
    selected_date = date(selected_year, selected_month, 1)
    avg_price = get_avg_fuel_prices_string(selected_date)

    return render_template('fuel/fuel-cash-report.html', user_info=user_info, years=years,
                           vacation_report_access=vacation_report_access, months=months, avg_price=avg_price,
                           cash_fuel_data=cash_fuel_data, selected_month=selected_month, selected_year=selected_year)


@app.route('/download_fuel_cash_report/<int:month>/<int:year>')
def download_fuel_cash_report(month, year):
    # Отримуємо PDF у пам’яті
    buffer = tm_users.get_users.UserAuto(11).generate_fuel_cash_report_pdf(month, year)

    # Відправляємо PDF для перегляду в браузері
    response = make_response(buffer.getvalue())
    buffer.close()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"inline; filename*=UTF-8''fuel_cash_report_{month}_{year}.pdf"
    return response

@app.route('/fuel-users', methods=['GET', 'POST'])
@login_required
def fuel_users_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    user_list = tm_users.get_users.UserAuto(user_id).get_all_users_and_car()

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True
    print(user_list)

    okko_card_catalog = fuel_okko_cards.query.all()
    okko_cards = []
    for card in okko_card_catalog:
        okko_cards.append({
            'id': card.id,
            'card_num': card.card_num,
            'user_id': card.user_id,
        })

    return render_template('fuel/fuel-users.html', user_info=user_info, okko_cards=okko_cards,
                           user_list=user_list, last_department="", vacation_report_access=vacation_report_access)

@app.route('/departaments-edet', methods=['GET', 'POST'])
@login_required
def users_departament_edit_page():
    if request.method == 'POST':
        # Отримання даних з форми
        dep_id = request.form.get('edit-dep_id')
        dep_name = request.form.get('edit-dep-name')
        leader = request.form.get('edit-leader')

        users.query.filter_by(id=leader).update(dict(user_departament=dep_id, user_access=2))
        departaments.query.filter_by(id=dep_id).update(dict(dep_name=dep_name, leader=leader))
        db.session.commit()
        db.session.close()
    return redirect(url_for('users_departament_list_page'))


@app.route('/departament-remove-<int:dep_id>')
@login_required
def departament_remove(dep_id):
    # Спочатку знайдіть всіх користувачів, які належать до цього відділу
    users_to_remove = users.query.filter_by(user_departament=dep_id).all()

    # Видаліть цих користувачів
    for user in users_to_remove:
        db.session.delete(user)

    # Тепер видаліть відділ
    departament_to_remove = departaments.query.get(dep_id)
    add_log = log_system(user_id=users_to_remove, type_event=f'Видалив департамент')
    db.session.add(add_log)
    db.session.delete(departament_to_remove)

    db.session.commit()
    return redirect(url_for('users_departament_list_page'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    if request.method == 'POST':
        new_cost = request.form.get('compensation_cost', type=int)
        if new_cost is not None and new_cost >= 0:
            setting = settings_table.query.filter_by(key='compensation_cost').first()
            if setting:
                setting.value = new_cost
            else:
                setting = settings_table(key='compensation_cost', value=new_cost)
                db.session.add(setting)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Вартість компенсації успішно оновлено!'})
        else:
            return jsonify({'success': False, 'message': 'Введіть коректне значення (не менше 0 грн)'})

    setting = settings_table.query.filter_by(key='compensation_cost').first()
    compensation_cost = setting.value if setting else 100
    
    # Отримуємо API ключ для цін на пальне
    fuel_api_key_setting = settings_table.query.filter_by(key='fuel_price_api_key').first()
    fuel_price_api_key = fuel_api_key_setting.value if fuel_api_key_setting else ''

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = user_departament_access is not None or user_id == 11

    return render_template('settings.html',
                         compensation_cost=compensation_cost,
                         fuel_price_api_key=fuel_price_api_key,
                         user_info=current_user,
                         vacation_report_access=vacation_report_access)

@app.route('/api/save-fuel-api-key', methods=['POST'])
@login_required
def save_fuel_api_key():
    """Збереження API ключа для цін на пальне"""
    try:
        user_id = current_user.id
        # Перевіряємо чи користувач адмін
        if user_id != 11:
            return jsonify({'success': False, 'error': 'Недостатньо прав доступу'}), 403
        
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API ключ не може бути порожнім'}), 400
        
        # Зберігаємо або оновлюємо API ключ
        setting = settings_table.query.filter_by(key='fuel_price_api_key').first()
        if setting:
            setting.value = api_key
        else:
            setting = settings_table(key='fuel_price_api_key', value=api_key)
            db.session.add(setting)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'API ключ успішно збережено!'
        })
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Помилка при збереженні API ключа: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500


@app.route('/api/test-fuel-api-key', methods=['POST'])
@login_required
def test_fuel_api_key():
    """Тестування API ключа для цін на пальне"""
    try:
        user_id = current_user.id
        # Перевіряємо чи користувач адмін
        if user_id != 11:
            return jsonify({'success': False, 'error': 'Недостатньо прав доступу'}), 403

        from scraper import OkkoAPIFuelPriceScraper

        # Створюємо екземпляр парсера для тестування
        scraper = OkkoAPIFuelPriceScraper()
        api_info = scraper.get_api_key_info()

        # Тестуємо API ключ
        is_valid = scraper.test_api_key()

        return jsonify({
            'success': True,
            'api_key_info': api_info,
            'is_valid': is_valid,
            'message': 'API ключ валідний' if is_valid else 'API ключ невалідний або відсутній'
        })

    except Exception as e:
        app.logger.error(f"Помилка при тестуванні API ключа: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500


@app.route('/api/update-fuel-prices', methods=['POST'])
@login_required
def update_fuel_prices():
    """Оновлення цін на пальне з OKKO API"""
    try:
        user_id = current_user.id
        # Перевіряємо чи користувач адмін
        if user_id != 11:
            return jsonify({'success': False, 'error': 'Недостатньо прав доступу'}), 403

        from scraper import OkkoAPIFuelPriceScraper

        # Запускаємо парсер
        scraper = OkkoAPIFuelPriceScraper()
        results = scraper.run()

        if results:
            return jsonify({
                'success': True,
                'message': f'Ціни успішно оновлено! Оновлено {len(results)} типів палива.',
                'data': results
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Не вдалося отримати ціни з API. Перевірте API ключ.'
            }), 400

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        app.logger.error(f"Помилка при оновленні цін на пальне: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500

@app.route('/transport-report-view', methods=['GET'])
@login_required
def transport_report_view():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    # Отримуємо поточний місяць та рік за замовчуванням
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Перевіряємо, чи передані параметри через GET
    month = request.args.get('month', current_month, type=int)
    year = request.args.get('year', current_year, type=int)

    # Отримуємо дані з функції get_transport_data
    transport_data, weekends = tm_users.get_users.get_transport_data(month, year)
    days_in_month = calendar.monthrange(year, month)[1]

    # Додаємо коментарі до transport_data
    for entry in transport_data:
        user_id = entry['user_id']  # Тепер user_id доступний
        daily_comments = {}
        # Отримуємо записи з employee_transport для цього користувача за місяць
        records = employee_transport.query.filter(
            employee_transport.user_id == user_id,
            employee_transport.date.between(
                date(year, month, 1),
                date(year, month, days_in_month)
            )
        ).all()

        # Формуємо словник коментарів для кожного дня
        for record in records:
            day = record.date.day
            comments = []
            if record.day_shift and record.day_comment:
                comments.append(f"Ранок: {record.day_comment}")
            if record.night_shift and record.night_comment:
                comments.append(f"Вечір: {record.night_comment}")
            daily_comments[day] = comments if comments else ["Без коментарів"]

        # Додаємо коментарі до entry
        entry['daily_comments'] = daily_comments

    # Додаємо індекси до transport_data
    transport_data_with_index = [(idx + 1, entry) for idx, entry in enumerate(transport_data)]

    # Список місяців українською для селекту
    month_names_uk = [
        "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
        "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"
    ]

    # Список років
    years = list(range(2020, 2100))
    price_for_day = settings_table.query.with_entities(settings_table.value).filter_by(
        key='compensation_cost').scalar() or 0
    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    return render_template(
        'fuel/transport_report_view.html',
        transport_data=transport_data_with_index,
        days_in_month=days_in_month,
        weekends=weekends,
        month=month,
        year=year,
        month_names_uk=month_names_uk,
        years=years,
        user_info=user_info,
        price_for_day=int(price_for_day),
        vacation_report_access=vacation_report_access
    )

@app.route('/transport-report/<int:month>/<int:year>')
@login_required
def generate_transport_report_pdf(month, year):
    user = current_user
    user_id = user.id

    pdfmetrics.registerFont(TTFont("DejaVuSerif", "static/fonts/DejaVuSerif.ttf"))

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    if not user_departament_access and user_id != 11:
        return "Доступ заборонено", 403

    days_in_month = calendar.monthrange(year, month)[1]

    month_names_uk = {
        1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень", 6: "Червень",
        7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"
    }
    month_name_uk = month_names_uk.get(month, "Невідомий місяць")

    month_names_en = {
        1: "Sichen", 2: "Lyutiy", 3: "Berezen", 4: "Kviten", 5: "Traven", 6: "Cherven",
        7: "Lipen", 8: "Serpen", 9: "Veresen", 10: "Zhovten", 11: "Listopad", 12: "Gruden"
    }
    month_name_en = month_names_en.get(month, "Unknown")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=20, leftMargin=20, rightMargin=20)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontName='DejaVuSerif', fontSize=12, alignment=1, spaceAfter=10)
    header_style = ParagraphStyle('Header', fontName='DejaVuSerif', fontSize=6, alignment=1, textColor=colors.black, leading=8)
    cell_style = ParagraphStyle('Cell', fontName='DejaVuSerif', fontSize=6, alignment=1, leading=8)
    total_style = ParagraphStyle('Total', fontName='DejaVuSerif', fontSize=6, alignment=1, textColor=colors.black, leading=8, fontWeight='bold')

    title = Paragraph(f"Список працівників підприємства, які відвозять працівників за {month_name_uk} {year}<br/>Сформовано: {datetime.now().strftime('%d-%m-%Y')}", title_style)

    elements.append(title)

    # Отримання даних і вихідних
    transport_data, weekends = tm_users.get_users.get_transport_data(month, year)

    headers = ["П/П", "ПІБ працівника"] + [f"{i}" for i in range(1, days_in_month + 1)] + ["Всього", "Сума, грн"]
    table_data = [[Paragraph(h, header_style) for h in headers]]

    for idx, entry in enumerate(transport_data, start=1):
        row = [
            Paragraph(str(idx), cell_style),
            Paragraph(entry['full_name'], cell_style),
        ]
        daily_counts = entry['daily_counts']
        for day in range(1, days_in_month + 1):
            count = daily_counts.get(day, 0)
            row.append(Paragraph(str(count) if count > 0 else "", cell_style))
        total = entry['total_count']
        price_for_day = settings_table.query.with_entities(settings_table.value).filter_by(key='compensation_cost').scalar() or 0
        amount = int(total * float(price_for_day))  # Округляємо до цілого числа
        formatted_amount = "{:,}".format(amount).replace(",", " ")  # Форматуємо з пробілами
        row.extend([Paragraph(str(total), cell_style), Paragraph(formatted_amount, cell_style)])
        table_data.append(row)

    # Підрахунок загальних значень
    total_count = sum(entry['total_count'] for entry in transport_data)
    total_sum = int(sum(entry['total_count'] * float(price_for_day) for entry in transport_data))  # Округляємо до цілого
    formatted_total_sum = "{:,}".format(total_sum).replace(",", " ")  # Форматуємо з пробілами

    # Додавання рядка з загальною сумою
    total_row = [
        Paragraph("", total_style),
        Paragraph("", total_style),
    ]
    for _ in range(days_in_month):
        total_row.append(Paragraph("", total_style))
    total_row.extend([Paragraph(str(total_count), total_style), Paragraph(formatted_total_sum, total_style)])
    table_data.append(total_row)

    # Оптимізована ширина колонок
    col_widths = [20, 100] + [20] * days_in_month + [25, 40]
    table = Table(table_data, colWidths=col_widths, hAlign='CENTER')

    # Базові стилі таблиці
    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # Сірий фон для заголовків
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
        ('FONTSIZE', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]

    # Явно задаємо білий фон для всіх клітинок
    for row in range(1, len(table_data) - 1):  # Починаємо з 1, закінчуємо перед останнім рядком
        for col in range(0, len(headers)):
            if col < 2 or col > days_in_month + 1:  # "П/П", "ПІБ", "Всього", "Сума, грн"
                table_styles.append(('BACKGROUND', (col, row), (col, row), colors.white))
            elif (col - 1) not in weekends:  # Будні (не вихідні)
                table_styles.append(('BACKGROUND', (col, row), (col, row), colors.white))

    # Додаємо заливку для вихідних
    for day in weekends:
        col_index = day + 1  # +1 для "П/П", +1 для "ПІБ"
        table_styles.append(('BACKGROUND', (col_index, 0), (col_index, 0), colors.lightgrey))  # Заголовки вихідних
        table_styles.append(('BACKGROUND', (col_index, 1), (col_index, -2), colors.lightgrey))  # Клітинки вихідних (до передостаннього рядка)

    # Виділення підсумкового рядка
    table_styles.append(('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey))  # Сірий фон для підсумків
    table_styles.append(('FONTWEIGHT', (0, -1), (-1, -1), 'bold'))  # Жирний текст для підсумків

    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    def add_page_number(canvas, doc):
        page_number = canvas.getPageNumber()
        text = f"Сторінка {page_number}"
        canvas.setFont("DejaVuSerif", 8)
        canvas.drawString(500, 15, text)

    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)

    buffer.seek(0)
    response = make_response(buffer.getvalue())
    buffer.close()
    response.mimetype = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=transport_report_{month_name_en}_{year}.pdf'
    return response

@app.route('/company-cars')
@login_required
def company_cars():

    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    # Отримуємо всі автомобілі з бази
    cars = company_car.query.filter(or_(company_car.avtopark==None, company_car.avtopark==0)).order_by(company_car.car_name).all()
    today = date.today()

    return render_template('company/company_cars.html', cars=cars, today=today, user_info=user_info)


@app.route('/company-cars-pdf')
@login_required
def company_cars_pdf():
    try:
        user = current_user
        user_id = user.id
        user_class = tm_users.get_users.Users(user_id)
        user_info = user_class.get_user_info()

        # Отримуємо рік і car_id із параметрів запиту
        year = request.args.get('year', type=int, default=datetime.now().year)
        car_id = request.args.get('car_id', type=int)

        if not car_id:
            return "Не вказано car_id", 400

        # Отримуємо конкретний автомобіль
        car = company_car.query.get_or_404(car_id)

        # Реєстрація шрифту для української мови
        pdfmetrics.registerFont(TTFont('DejaVuSerif', 'static/fonts/DejaVuSerif.ttf'))

        # Створюємо буфер для PDF із альбомною орієнтацією
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=20, leftMargin=20, rightMargin=20)
        elements = []

        # Стилі
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.fontName = 'DejaVuSerif'
        title_style.fontSize = 16
        title_style.alignment = 1  # Центрування

        normal_style = styles['Normal']
        normal_style.fontName = 'DejaVuSerif'
        normal_style.fontSize = 8
        normal_style.wordWrap = 'CJK'  # Дозволяє перенос тексту в заголовках

        # Заголовок із вказівкою року та назви автомобіля
        title = Paragraph(f"Звіт по автомобілю {car.car_name} ({car.car_number}) за {year} рік - {datetime.now().strftime('%d-%m-%Y')}", title_style)
        elements.append(title)
        elements.append(Paragraph("<br/>", normal_style))  # Порожній рядок

        # Дані для основної таблиці (загальні дані за останній місяць року)
        table_data = [
            [
                Paragraph("Держ. номер", normal_style),
                #Paragraph("Підприємство", normal_style),
                Paragraph("За ким закріплена", normal_style),
                Paragraph("Пробіг на початок місяця", normal_style),
                Paragraph("Пробіг на кінець місяця", normal_style),
                Paragraph("Пробіг за місяць", normal_style),
                Paragraph("Заправка за місяць (л)", normal_style),
                Paragraph("Норма витрат, л/100 км", normal_style),
                Paragraph("Витрата за місяць (л)", normal_style),
                Paragraph("Залишок у баку на початок місяця", normal_style),
                Paragraph("Залишок у баку на кінець місяця", normal_style),
                Paragraph("Об’єм бака", normal_style),
                Paragraph("Дельта", normal_style),
                #Paragraph("Страховка (Громадянка)", normal_style),
                #Paragraph("Страховка (КАСКО)", normal_style),
                Paragraph("Витрати на паливо (грн)", normal_style)
            ]
        ]

        # Отримуємо дані пробігу за рік із бази даних
        mileage_records = car_mileage.query.filter(
            car_mileage.car_id == car_id,
            car_mileage.date.between(f'{year}-01-01', f'{year}-12-31')
        ).order_by(car_mileage.date).all()

        # Розрахунок даних за останній місяць року
        tank_volume = car.tank_volume or 80  # Об’єм бака за замовчуванням
        fuel_norm = car.fuel_norm or 11.8    # Норма витрат за замовчуванням
        fuel_price_per_liter = 50            # Ціна палива за літр (грн)

        # Беремо останній місяць із записами
        last_month = datetime.strptime(f'{year}-12-01', '%Y-%m-%d').date()  # Приводимо до date
        mileage_dict = {record.date: record for record in mileage_records}
        prev_record = None
        last_record = None

        # Знаходимо останній запис і попередній до нього
        for month in sorted(mileage_dict.keys(), reverse=True):
            if month <= last_month:  # Порівняння date з date
                last_record = mileage_dict[month]
                prev_month = datetime(year, month.month - 1, 1).date() if month.month > 1 else datetime(year - 1, 12, 1).date()
                prev_record = mileage_dict.get(prev_month)
                break

        if last_record:
            mileage_end = last_record.mileage
            fuel_added = last_record.fuel_added or 0
            mileage_start = prev_record.mileage if prev_record else 0
        else:
            mileage_end = 0
            fuel_added = 0
            mileage_start = 0

        mileage_month = mileage_end - mileage_start
        fuel_consumed = mileage_month * (fuel_norm / 100)
        fuel_start = tank_volume / 2 if not prev_record else (tank_volume / 2 + (prev_record.fuel_added or 0) - (mileage_start - (mileage_dict.get(datetime(year, prev_record.date.month - 1, 1).date()) or prev_record).mileage) * (fuel_norm / 100))
        fuel_end = fuel_start + fuel_added - fuel_consumed
        delta = fuel_added - fuel_consumed
        fuel_cost = fuel_added * fuel_price_per_liter

        # Додаємо дані в таблицю
        table_data.append([
            car.car_number,                  # Держ. номер
            #car.company_name,                # Підприємство
            car.car_name,                    # За ким закріплена (як приклад)
            str(mileage_start),              # Пробіг на початок місяця
            str(mileage_end),                # Пробіг на кінець місяця
            str(mileage_month),              # Пробіг за місяць
            f"{fuel_added:.2f}" if fuel_added else "-",  # Заправка за місяць
            f"{fuel_norm:.1f}",              # Норма витрат
            f"{fuel_consumed:.2f}",          # Витрата за місяць
            f"{fuel_start:.2f}",             # Залишок на початок місяця
            f"{fuel_end:.2f}",               # Залишок на кінець місяця
            str(tank_volume),                # Об’єм бака
            f"{delta:.2f}",                  # Дельта
            #car.public_insurance.strftime('%d-%m-%Y') if car.public_insurance else '-',  # Страховка (Громадянка)
            #car.kasko_insurance.strftime('%d-%m-%Y') if car.kasko_insurance else '-',    # Страховка (КАСКО)
            f"{fuel_cost:.2f}"               # Витрати на паливо
        ])

        # Створення основної таблиці
        table = Table(table_data, colWidths=[1.0*inch, 1*inch, 1.0*inch, 0.9*inch, 0.9*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1.0*inch, 0.7*inch, 0.7*inch, 0.7*inch]) #, 1.0*inch, 1.0*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(table)
        elements.append(Paragraph("<br/><br/>", normal_style))  # Відступ перед зведеною таблицею

        # Зведена таблиця (дані за місяці)
        summary_data = [
            ["Сводна таблиця за рік", "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"],
            ["Пробіг за місяць", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Заправка за місяць (л)", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Пробіг на початок місяця", "", "", "", "", "", "", "", "", "", "", "", ""]
        ]

        # Ініціалізація змінних для зведеної таблиці
        months = [datetime(year, m, 1).date() for m in range(1, 13)]  # Приводимо до date
        mileage_dict = {record.date: record for record in mileage_records}
        prev_mileage = 0  # Початковий пробіг на початок року

        for i, month in enumerate(months, start=1):
            record = mileage_dict.get(month)
            if record:
                mileage_end = record.mileage
                fuel_added = record.fuel_added or 0
            else:
                mileage_end = prev_mileage
                fuel_added = 0

            mileage_month = mileage_end - prev_mileage
            summary_data[1][i] = str(mileage_month)  # Пробіг за місяць
            summary_data[2][i] = f"{fuel_added:.2f}" if fuel_added else "-"  # Заправка за місяць
            summary_data[3][i] = str(prev_mileage)  # Пробіг на початок місяця
            prev_mileage = mileage_end

        # Створення зведеної таблиці
        summary_table = Table(summary_data, colWidths=[1.5*inch] + [0.7*inch]*12)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(summary_table)

        # Генерація PDF
        doc.build(elements)
        buffer.seek(0)

        # Повернення PDF як відповіді з ASCII-сумісною назвою файлу
        filename = f'car_report_{car_id}_{year}.pdf'
        response = make_response(buffer.getvalue())
        buffer.close()
        response.mimetype = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={filename}'
        return response

    except Exception as e:
        return render_template('error.html', message=f"Помилка при генерації звіту: {str(e)}"), 500

@app.route('/api/check_insurance_expiry', methods=['GET'])
@login_required
def check_insurance_expiry():
    try:
        today = datetime.now().date()
        five_days_later = today + timedelta(days=5)  # Змінено з 10 на 5 днів

        # Отримуємо всі автомобілі
        cars = company_car.query.all()
        expiring_cars = []

        for car in cars:
            public_expiry = car.public_insurance
            kasko_expiry = car.kasko_insurance
            plan_to_expiry = car.plan_to
            has_expiring = False
            car_info = {
                'id': car.id,
                'car_name': car.car_name,
                'car_number': car.car_number,
                'public_insurance': None,
                'kasko_insurance': None,
                'plan_to': None
            }

            # Перевірка державної страховки
            if public_expiry and (public_expiry - today).days <= 5:  # Якщо <= 5 днів або минуло
                car_info['public_insurance'] = public_expiry.strftime('%d-%m-%Y')
                has_expiring = True

            # Перевірка КАСКО
            if kasko_expiry and (kasko_expiry - today).days <= 5:  # Якщо <= 5 днів або минуло
                car_info['kasko_insurance'] = kasko_expiry.strftime('%d-%m-%Y')
                has_expiring = True

            # Перевірка Плану ТО
            if plan_to_expiry and (plan_to_expiry - today).days <= 5:  # Якщо <= 5 днів або минуло
                car_info['plan_to'] = plan_to_expiry.strftime('%d-%m-%Y')
                has_expiring = True

            if has_expiring:
                expiring_cars.append(car_info)

        # Якщо немає автомобілів із закінченням терміну, повертаємо порожній рядок
        if not expiring_cars:
            return jsonify({'html': ''})

        # Генеруємо HTML модалі з кастомними стилями
        modal_html = '''
        <div class="modal fade" id="insuranceWarningModal" tabindex="-1" role="dialog" aria-labelledby="insuranceWarningModalLabel" aria-hidden="true">
            <div class="modal-dialog" role="document" style="max-width: 50%; width: 50%; margin: 0 auto; top: 50%; transform: translateY(-50%); position: relative;">
                <div class="modal-content" style="min-height: 50vh; display: flex; flex-direction: column;">
                    <div class="modal-header bg-warning text-white">
                        <h5 class="modal-title" id="insuranceWarningModalLabel">Попередження про закінчення терміну</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close" style="filter: invert(1);"></button>
                    </div>
                    <div class="modal-body" style="flex-grow: 1; overflow-y: auto; padding: 20px; font-size: 1.1rem;">
        '''

        for car in expiring_cars:
            message = f'<p>Увага! Для автомобіля <strong>{car["car_name"]} ({car["car_number"]})</strong> закінчується '
            parts = []
            if car['public_insurance']:
                parts.append(f'державна страховка <span style="color: red;">{car["public_insurance"]}</span>')
            if car['kasko_insurance']:
                parts.append(f'КАСКО <span style="color: red;">{car["kasko_insurance"]}</span>')
            if car['plan_to']:
                parts.append(f'план ТО <span style="color: red;">{car["plan_to"]}</span>')
            message += ', '.join(parts) + '.</p>'
            modal_html += message

        modal_html += '''
                    </div>
                    <div class="modal-footer" style="padding: 10px;">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Закрити</button>
                    </div>
                </div>
            </div>
        </div>
        '''

        # Повертаємо HTML як частину JSON
        return jsonify({'html': modal_html})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

from calendar import monthrange
@app.route('/company-fuel', methods=['GET'])
@login_required
def company_fuel():
    from calendar import monthrange
    from datetime import date, datetime
    from sqlalchemy import func, desc  # додано desc

    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    selected_month = int(request.args.get('month', datetime.now().month))
    selected_year = int(request.args.get('year', datetime.now().year))

    months = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
              "Жовтень", "Листопад", "Грудень"]
    years = list(range(2020, datetime.now().year + 5))

    today = date.today()
    month_start = date(selected_year, selected_month, 1)
    last_day_of_month = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    if selected_year < today.year or (selected_year == today.year and selected_month < today.month):
        price_period_start = month_start
        price_period_end = last_day_of_month
    else:
        price_period_start = month_start
        price_period_end = today

    avg_price = db.session.query(
        fuel_price.fuel_type,
        func.avg(fuel_price.price).label("average_price")
    ).filter(
        fuel_price.created_at.between(price_period_start, price_period_end)
    ).group_by(fuel_price.fuel_type).all()
    avg_price_dict = {fuel: round(price, 1) for fuel, price in avg_price}

    current_date = datetime.now()

    # межі для місяця
    current_month_start_dt = date(selected_year, selected_month, 1)
    current_month_end_dt = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    cars = company_car.query.filter_by(avtopark=0).all()
    car_data = []
    for car in cars:
        if car.created_at and car.created_at > current_month_end_dt:
            continue

        prev_month = selected_month - 1 if selected_month > 1 else 12
        prev_year = selected_year if selected_month > 1 else selected_year - 1
        last_day_prev_month = monthrange(prev_year, prev_month)[1]
        prev_month_end = f'{prev_year}-{prev_month:02d}-{last_day_prev_month}'

        prev_records = car_mileage.query.filter(
            car_mileage.car_id == car.id,
            car_mileage.date <= prev_month_end
        ).order_by(car_mileage.date).all()

        if prev_records:
            last_prev_record = prev_records[-1]
            start_mileage = last_prev_record.mileage
            total_refueled_until_prev = round(sum(record.fuel_added or 0 for record in prev_records), 2)
            total_mileage_until_prev = last_prev_record.mileage - (car.initial_mileage or 0)
            total_fuel_consumed_until_prev = round(
                (total_mileage_until_prev * car.fuel_norm / 100), 2
            ) if total_mileage_until_prev > 0 else 0
            start_balance = round(
                (car.initial_fuel_balance or 0) + total_refueled_until_prev - total_fuel_consumed_until_prev, 2
            )
        else:
            start_mileage = car.initial_mileage or 0
            start_balance = round(car.initial_fuel_balance or 0, 2)

        # беремо останній запис пробігу за вибраний місяць
        last_rec = car_mileage.query.filter(
            car_mileage.car_id == car.id,
            func.date(car_mileage.date).between(current_month_start_dt, current_month_end_dt)
        ).order_by(car_mileage.date.desc()).first()

        if last_rec:
            end_mileage = last_rec.mileage
        else:
            end_mileage = 0

        # рахуємо суму заправок у БД
        total_refueled = db.session.query(func.coalesce(func.sum(car_mileage.fuel_added), 0)).filter(
            car_mileage.car_id == car.id,
            func.date(car_mileage.date).between(current_month_start_dt, current_month_end_dt)
        ).scalar() or 0
        total_refueled = round(total_refueled, 2)

        # Отримуємо транзакції OKKO
        assigned_user = db.session.query(users.id).filter(users.user_fullname == car.location).first()
        user_ids = [assigned_user.id] if assigned_user else []

        card_nums = db.session.query(fuel_okko_cards.card_num).filter(
            fuel_okko_cards.user_id.in_(user_ids)
        ).all()
        card_nums = [cnum[0] for cnum in card_nums]

        transactions = db.session.query(fuel_okko_transactions).filter(
            fuel_okko_transactions.card_num.in_(card_nums),
            func.date(fuel_okko_transactions.trans_date).between(current_month_start_dt, current_month_end_dt)
        ).all()

        transactions_data = []
        total_okko_fuel = 0
        total_okko_cost = 0

        for t in transactions:
            fuel_amount = (
                round(t.fuel_volume / 1000, 2) if t.trans_type == 774
                else -round(t.fuel_volume / 1000, 2) if t.trans_type == 775
                else round(t.fuel_volume / 1000, 2)
            ) if t.fuel_volume else 0

            cost = (
                round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 774
                else -round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 775
                else round((t.amnt_trans - (t.discount or 0)) / 100, 2)
            ) if t.amnt_trans else 0

            transactions_data.append({
                'id': t.id,
                'date': t.trans_date.strftime('%d.%m.%y') if t.trans_date else '',
                'amount': fuel_amount,
                'cost': cost,
                'card_num': t.card_num,
                'azs_name': t.azs_name or 'Невідома АЗС',
                'addr_name': t.addr_name or 'Невідома адреса',
                'person_name': f"{t.person_first_name or ''} {t.person_last_name or ''}".strip() or 'Невідомо'
            })

            total_okko_fuel += fuel_amount
            total_okko_cost += cost

        approx_cost = round(total_refueled * (avg_price_dict.get(car.fuel_type, 0) or 0), 1)

        car_data.append({
            'id': car.id,
            'car_number': car.car_number,
            'fuel_type': car.fuel_type,
            'fuel_norm': round(car.fuel_norm or 0, 2),
            'tank_volume': car.tank_volume or 0,
            'start_mileage': start_mileage,
            'end_mileage': end_mileage,
            'refueled': total_refueled,
            'okko_refueled': round(total_okko_fuel, 2),
            'start_balance': start_balance,
            'approx_cost': approx_cost,
            'okko_cost': total_okko_cost,
            'company_name': car.company_name,
            'transactions': transactions_data
        })

    dss_cars = [car for car in car_data if car['company_name'] == 'ДНІПРО-СЕРВІС']
    tf_cars = [car for car in car_data if car['company_name'] == 'ТФ']

    selected_date = last_day_of_month if (
            selected_year < today.year or (selected_year == today.year and selected_month < today.month)) else today
    avg_price_string = get_avg_fuel_prices_string(selected_date)

    return render_template('company/company_fuel.html',
                           dss_cars=dss_cars,
                           tf_cars=tf_cars,
                           months=months,
                           years=years,
                           selected_month=selected_month,
                           selected_year=selected_year,
                           user_info=user_info,
                           avg_price_dict=avg_price_dict,
                           avg_price='',
                           today=today)


@app.route('/company-autopark', methods=['GET'])
@login_required
def company_autopark_page():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    # Отримуємо всі автомобілі з бази
    cars = company_car.query.filter_by(avtopark=1).order_by(company_car.car_name).all()
    today = date.today()

    return render_template('company/avtopark.html', cars=cars, today=today, user_info=user_info)

@app.route('/api/company-fuel/save', methods=['POST'])
@login_required
def save_company_fuel():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    for entry in data:
        car_id = entry['car_id']
        end_mileage = entry['end_mileage']
        refueled = entry['refueled']
        month = int(entry['month'])  # Значення від 1 до 12
        year = int(entry['year'])

        # Визначаємо останній день місяця
        if month == 12:
            # Для грудня наступний місяць — січень наступного року
            last_day = (datetime(year + 1, 1, 1) - timedelta(days=1)).day
            record_date = f'{year}-12-{last_day:02d}'
        else:
            # Для інших місяців
            last_day = (datetime(year, month + 1, 1) - timedelta(days=1)).day
            record_date = f'{year}-{month:02d}-{last_day:02d}'

        # Перевіряємо, чи є запис для цього автомобіля і дати
        mileage_record = car_mileage.query.filter_by(
            car_id=car_id,
            date=record_date
        ).first()

        if mileage_record:
            # Оновлюємо існуючий запис
            mileage_record.mileage = end_mileage
            mileage_record.fuel_added = refueled
        else:
            # Створюємо новий запис
            new_record = car_mileage(
                car_id=car_id,
                date=record_date,
                mileage=end_mileage,
                fuel_added=refueled
            )
            db.session.add(new_record)

    try:
        db.session.commit()
        return jsonify({'message': 'Дані успішно збережено!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Помилка при збереженні: {str(e)}'}), 500


@app.route('/company-cars/all-pdf', methods=['GET'])
@login_required
def company_cars_all_pdf():
    from io import BytesIO
    from calendar import monthrange
    from datetime import datetime, date
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from sqlalchemy import func

    try:
        user = current_user
        user_id = user.id
        user_class = tm_users.get_users.Users(user_id)
        user_info = user_class.get_user_info()

        year = request.args.get('year', type=int, default=datetime.now().year)

        # Реєстрація шрифту для української мови
        pdfmetrics.registerFont(TTFont('DejaVuSerif', 'static/fonts/DejaVuSerif.ttf'))

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=20, leftMargin=20,
                                rightMargin=20)
        elements = []

        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.fontName = 'DejaVuSerif'
        title_style.fontSize = 16
        title_style.alignment = 1

        normal_style = styles['Normal']
        normal_style.fontName = 'DejaVuSerif'
        normal_style.fontSize = 8
        normal_style.wordWrap = 'CJK'
        normal_style.alignment = 1

        # Усі авто
        cars = company_car.query.filter_by(avtopark=0).all()

        for i, car in enumerate(cars):
            title = Paragraph(
                f"Звіт по автомобілю {car.car_name} ({car.car_number}) за {year} рік - {datetime.now().strftime('%d-%m-%Y')}",
                title_style
            )
            elements.append(title)
            elements.append(Paragraph("<br/>", normal_style))

            summary_data = [
                ["Сводна таблиця за рік", "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень",
                 "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень", "Тотал"],
                ["Пробіг за місяць", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["Заправка за місяць (л)", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["Витрати на паливо (грн)", "", "", "", "", "", "", "", "", "", "", "", "", ""]
            ]

            # Витягуємо записи пробігу за рік
            mileage_records = car_mileage.query.filter(
                car_mileage.car_id == car.id,
                car_mileage.date.between(f'{year}-01-01', f'{year}-12-31')
            ).order_by(car_mileage.date).all()

            months = [datetime(year, m, 1).date() for m in range(1, 13)]
            prev_mileage = car.initial_mileage or 0
            total_fuel_added = 0.0
            total_fuel_cost = 0.0
            max_mileage = prev_mileage

            # Підготуємо список карток, прив'язаних до машини (через users.user_fullname == car.location)
            assigned_user = db.session.query(users.id).filter(users.user_fullname == car.location).first()
            user_ids = [assigned_user.id] if assigned_user else []
            card_nums = []
            if user_ids:
                card_nums_q = db.session.query(fuel_okko_cards.card_num).filter(
                    fuel_okko_cards.user_id.in_(user_ids)
                ).all()
                card_nums = [c[0] for c in card_nums_q]

            for j, month in enumerate(months, start=1):
                month_start_dt = date(year, j, 1)
                month_end_dt = date(year, j, monthrange(year, j)[1])

                # Пробіг за місяць — беремо останній запис місяця
                month_records = [r for r in mileage_records if month_start_dt <= r.date <= month_end_dt]
                if month_records:
                    mileage_end = month_records[-1].mileage
                    max_mileage = max(max_mileage, mileage_end)
                else:
                    mileage_end = prev_mileage

                mileage_month = mileage_end - prev_mileage

                # КЛЮЧОВА ЗМІНА: тепер беремо дані тільки з OKKO транзакцій
                month_okko_cost = 0.0
                month_okko_fuel = 0.0

                if card_nums:
                    # Отримуємо транзакції OKKO за місяць
                    txns = db.session.query(fuel_okko_transactions).filter(
                        fuel_okko_transactions.card_num.in_(card_nums),
                        func.date(fuel_okko_transactions.trans_date).between(month_start_dt, month_end_dt)
                    ).all()

                    for t in txns:
                        # Розраховуємо об'єм палива
                        fuel_amount = (
                            round(t.fuel_volume / 1000, 2) if t.trans_type == 774
                            else -round(t.fuel_volume / 1000, 2) if t.trans_type == 775
                            else round(t.fuel_volume / 1000, 2)
                        ) if t.fuel_volume else 0

                        # Розраховуємо вартість
                        cost = (
                            round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 774
                            else -round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 775
                            else round((t.amnt_trans - (t.discount or 0)) / 100, 2)
                        ) if t.amnt_trans else 0

                        month_okko_fuel += fuel_amount
                        month_okko_cost += cost

                # Використовуємо дані з OKKO (як на сторінці /company-fuel)
                fuel_added = month_okko_fuel
                fuel_cost_month = month_okko_cost

                total_fuel_added += fuel_added
                total_fuel_cost += fuel_cost_month

                summary_data[1][j] = str(mileage_month)
                summary_data[2][j] = f"{fuel_added:.1f}"
                summary_data[3][j] = f"{fuel_cost_month:.0f}"

                prev_mileage = mileage_end

            # Тотали
            summary_data[1][-1] = str(max_mileage - (car.initial_mileage or 0))
            summary_data[2][-1] = f"{total_fuel_added:.1f}"
            summary_data[3][-1] = f"{total_fuel_cost:.0f}"

            summary_table = Table(summary_data, colWidths=[1.7 * inch] + [0.6 * inch] * 12 + [1.0 * inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 3), (-1, 3), colors.lightgrey),
                ('FONTWEIGHT', (-1, 1), (-1, -1), 'BOLD'),
            ]))
            elements.append(summary_table)
            elements.append(PageBreak())

        # build PDF
        doc.build(elements)
        buffer.seek(0)
        filename = f'company_cars_all_report_{year}.pdf'
        response = make_response(buffer.getvalue())
        buffer.close()
        response.mimetype = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={filename}'
        return response

    except Exception as e:
        return f"Помилка при генерації звіту: {str(e)}", 500


@app.route('/company-fuel/pdf', methods=['GET'])
@login_required
def company_fuel_pdf():
    try:
        from calendar import monthrange
        from datetime import date, datetime
        from sqlalchemy import func

        user = current_user
        user_id = user.id
        user_class = tm_users.get_users.Users(user_id)
        user_info = user_class.get_user_info()

        selected_month = int(request.args.get('month', datetime.now().month))
        selected_year = int(request.args.get('year', datetime.now().year))

        pdfmetrics.registerFont(TTFont('DejaVuSerif', 'static/fonts/DejaVuSerif.ttf'))
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=20, leftMargin=20,
                                rightMargin=20)
        elements = []

        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.fontName = 'DejaVuSerif'
        title_style.fontSize = 16
        title_style.alignment = 1

        subtitle_style = styles['Heading2']
        subtitle_style.fontName = 'DejaVuSerif'
        subtitle_style.fontSize = 12
        subtitle_style.alignment = 0

        normal_style = styles['Normal']
        normal_style.fontName = 'DejaVuSerif'
        normal_style.fontSize = 8
        normal_style.wordWrap = 'CJK'

        month_names_uk = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
                          "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
        month_name = month_names_uk[selected_month - 1]
        generation_date = datetime.now().strftime('%d.%m.%Y')
        title = Paragraph(
            f"Звіт по витратах пального для службових автомобілів за {month_name} {selected_year} року<br/>Сформовано: {generation_date}",
            title_style)
        elements.append(title)
        elements.append(Spacer(1, 12))

        avg_price = db.session.query(
            fuel_price.fuel_type,
            func.avg(fuel_price.price).label("average_price")
        ).group_by(fuel_price.fuel_type).all()
        avg_price_dict = {fuel: round(price, 1) for fuel, price in avg_price}

        # межі для місяця - використовуємо date об'єкти
        current_month_start_dt = date(selected_year, selected_month, 1)
        current_month_end_dt = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

        cars = company_car.query.filter_by(avtopark=0).all()
        car_data = []

        for car in cars:
            # Перевірка чи авто існувало в обраному місяці
            if car.created_at and car.created_at > current_month_end_dt:
                continue

            # Отримуємо user_id для цього авто
            user_name = car.location
            assigned_user = users.query.filter_by(user_fullname=user_name).first()
            if not assigned_user:
                continue
            user_car_id = assigned_user.id

            # Розрахунок попереднього місяця
            prev_month = selected_month - 1 if selected_month > 1 else 12
            prev_year = selected_year if selected_month > 1 else selected_year - 1
            last_day_prev_month = monthrange(prev_year, prev_month)[1]
            prev_month_end = f'{prev_year}-{prev_month:02d}-{last_day_prev_month}'

            # Отримуємо всі записи до кінця попереднього місяця
            prev_records = car_mileage.query.filter(
                car_mileage.car_id == car.id,
                car_mileage.date <= prev_month_end
            ).order_by(car_mileage.date).all()

            # Розраховуємо стартовий пробіг та баланс
            if prev_records:
                last_prev_record = prev_records[-1]
                start_mileage = last_prev_record.mileage
                total_refueled_until_prev = round(sum(record.fuel_added or 0 for record in prev_records), 2)
                total_mileage_until_prev = last_prev_record.mileage - (car.initial_mileage or 0)
                total_fuel_consumed_until_prev = round(
                    (total_mileage_until_prev * car.fuel_norm / 100), 2
                ) if total_mileage_until_prev > 0 else 0
                start_balance = round(
                    (car.initial_fuel_balance or 0) + total_refueled_until_prev - total_fuel_consumed_until_prev, 2
                )
            else:
                start_mileage = car.initial_mileage or 0
                start_balance = round(car.initial_fuel_balance or 0, 2)

            # Отримуємо останній запис пробігу за вибраний місяць
            last_rec = car_mileage.query.filter(
                car_mileage.car_id == car.id,
                func.date(car_mileage.date).between(current_month_start_dt, current_month_end_dt)
            ).order_by(car_mileage.date.desc()).first()

            if last_rec:
                end_mileage = last_rec.mileage
            else:
                end_mileage = start_mileage

            # Отримуємо транзакції OKKO - ТОЧНО ЯК У /company-fuel
            card_nums = db.session.query(fuel_okko_cards.card_num).filter(
                fuel_okko_cards.user_id == user_car_id
            ).all()
            card_nums = [cnum[0] for cnum in card_nums]

            transactions = db.session.query(fuel_okko_transactions).filter(
                fuel_okko_transactions.card_num.in_(card_nums),
                func.date(fuel_okko_transactions.trans_date).between(current_month_start_dt, current_month_end_dt)
            ).all()

            # Розраховуємо загальний об'єм палива та вартість з OKKO транзакцій
            total_okko_fuel = 0
            total_okko_cost = 0

            for t in transactions:
                fuel_amount = (
                    round(t.fuel_volume / 1000, 2) if t.trans_type == 774
                    else -round(t.fuel_volume / 1000, 2) if t.trans_type == 775
                    else round(t.fuel_volume / 1000, 2)
                ) if t.fuel_volume else 0

                cost = (
                    round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 774
                    else -round((t.amnt_trans - (t.discount or 0)) / 100, 2) if t.trans_type == 775
                    else round((t.amnt_trans - (t.discount or 0)) / 100, 2)
                ) if t.amnt_trans else 0

                total_okko_fuel += fuel_amount
                total_okko_cost += cost

            total_okko_fuel = round(total_okko_fuel, 2)

            # Розрахунки - використовуємо okko_refueled як на сторінці
            monthly_mileage = end_mileage - start_mileage
            fuel_norm = round(car.fuel_norm or 0, 2)
            fuel_consumed = round((monthly_mileage * fuel_norm / 100), 2) if monthly_mileage > 0 else 0
            end_balance = round(start_balance + total_okko_fuel - fuel_consumed, 2)
            delta = round(total_okko_fuel - fuel_consumed, 1)

            car_data.append({
                'car_number': car.car_number,
                'start_mileage': start_mileage,
                'end_mileage': end_mileage,
                'monthly_mileage': monthly_mileage,
                'refueled': total_okko_fuel,  # Використовуємо дані з OKKO, як на сторінці
                'fuel_norm': fuel_norm,
                'fuel_consumed': fuel_consumed,
                'start_balance': start_balance,
                'end_balance': end_balance,
                'delta': delta,
                'approx_cost': total_okko_cost,  # Використовуємо вартість з OKKO, як на сторінці
                'company_name': car.company_name
            })

        dss_cars = [car for car in car_data if car['company_name'] == 'ДНІПРО-СЕРВІС']
        tf_cars = [car for car in car_data if car['company_name'] == 'ТФ']

        table_headers = [
            Paragraph("Держ. номер авто", normal_style),
            Paragraph("Пробіг на початок місяця", normal_style),
            Paragraph("Пробіг на кінець місяця", normal_style),
            Paragraph("Пробіг за місяць", normal_style),
            Paragraph("Заправлено за місяць (л)", normal_style),
            Paragraph("Норма на 100 км", normal_style),
            Paragraph("Розхід за місяць (л)", normal_style),
            Paragraph("Залишок на початок місяця (л)", normal_style),
            Paragraph("Залишок на кінець місяця (л)", normal_style),
            Paragraph("Дельта (л)", normal_style),
            Paragraph("Сума в грн", normal_style)
        ]

        def format_number(n):
            return "{:,}".format(n).replace(",", " ") if n else "0"

        light_green = colors.Color(0.9, 1, 0.9)
        light_red = colors.Color(1, 0.9, 0.9)
        footer_color = colors.HexColor('#d3d3d3')

        if dss_cars:
            elements.append(Paragraph("ДНІПРО-СЕРВІС", subtitle_style))
            elements.append(Spacer(1, 6))
            dss_table_data = [table_headers]
            total_cost_dss = 0
            total_refueled_dss = 0

            for car in dss_cars:
                total_cost_dss += car['approx_cost'] or 0
                total_refueled_dss += car['refueled'] or 0
                row = [
                    car['car_number'],
                    format_number(car['start_mileage']),
                    format_number(car['end_mileage']),
                    format_number(car['monthly_mileage']),
                    f"{car['refueled']:.2f}".replace(".", ","),
                    f"{car['fuel_norm']:.2f}".replace(".", ","),
                    f"{car['fuel_consumed']:.2f}".replace(".", ",") if car['fuel_consumed'] else "0,00",
                    f"{car['start_balance']:.2f}".replace(".", ","),
                    f"{car['end_balance']:.2f}".replace(".", ","),
                    f"{car['delta']:.1f}".replace(".", ","),
                    format_number(int(car['approx_cost'])) if car['approx_cost'] else "0"
                ]
                dss_table_data.append(row)

            dss_table_data.append([
                Paragraph("Всього:", normal_style),
                "", "", "",
                f"{total_refueled_dss:.2f}".replace(".", ","),
                "", "", "", "", "",
                format_number(int(total_cost_dss))
            ])

            dss_table = Table(dss_table_data,
                              colWidths=[1.2 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch,
                                         1.0 * inch, 1.2 * inch, 1.2 * inch, 0.8 * inch, 1.0 * inch])
            table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -2), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), footer_color),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]

            for i, car in enumerate(dss_cars, start=1):
                start_balance = car['start_balance']
                table_style.append(('BACKGROUND', (7, i), (7, i), light_green if start_balance >= 0 else light_red))
                end_balance = car['end_balance']
                table_style.append(('BACKGROUND', (8, i), (8, i), light_green if end_balance >= 0 else light_red))
                delta = car['delta']
                table_style.append(('BACKGROUND', (9, i), (9, i), light_red if delta > 0 else light_green))

            dss_table.setStyle(TableStyle(table_style))
            elements.append(dss_table)
            elements.append(Spacer(1, 12))

        if tf_cars:
            elements.append(Paragraph("ТФ", subtitle_style))
            elements.append(Spacer(1, 6))
            tf_table_data = [table_headers]
            total_cost_tf = 0
            total_refueled_tf = 0

            for car in tf_cars:
                total_cost_tf += car['approx_cost'] or 0
                total_refueled_tf += car['refueled'] or 0
                row = [
                    car['car_number'],
                    format_number(car['start_mileage']),
                    format_number(car['end_mileage']),
                    format_number(car['monthly_mileage']),
                    f"{car['refueled']:.2f}".replace(".", ","),
                    f"{car['fuel_norm']:.2f}".replace(".", ","),
                    f"{car['fuel_consumed']:.2f}".replace(".", ",") if car['fuel_consumed'] else "0,00",
                    f"{car['start_balance']:.2f}".replace(".", ","),
                    f"{car['end_balance']:.2f}".replace(".", ","),
                    f"{car['delta']:.1f}".replace(".", ","),
                    format_number(int(car['approx_cost'])) if car['approx_cost'] else "0"
                ]
                tf_table_data.append(row)

            tf_table_data.append([
                Paragraph("Всього:", normal_style),
                "", "", "",
                f"{total_refueled_tf:.2f}".replace(".", ","),
                "", "", "", "", "",
                format_number(int(total_cost_tf))
            ])

            tf_table = Table(tf_table_data,
                             colWidths=[1.2 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch,
                                        1.0 * inch, 1.2 * inch, 1.2 * inch, 0.8 * inch, 1.0 * inch])
            table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -2), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), footer_color),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]

            for i, car in enumerate(tf_cars, start=1):
                start_balance = car['start_balance']
                table_style.append(('BACKGROUND', (7, i), (7, i), light_green if start_balance >= 0 else light_red))
                end_balance = car['end_balance']
                table_style.append(('BACKGROUND', (8, i), (8, i), light_green if end_balance >= 0 else light_red))
                delta = car['delta']
                table_style.append(('BACKGROUND', (9, i), (9, i), light_red if delta > 0 else light_green))

            tf_table.setStyle(TableStyle(table_style))
            elements.append(tf_table)

        doc.build(elements)
        buffer.seek(0)

        filename = f'company_fuel_report_{selected_month}_{selected_year}.pdf'
        response = make_response(buffer.getvalue())
        buffer.close()
        response.mimetype = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={filename}'
        return response

    except Exception as e:
        return render_template('error.html', message=f"Помилка при генерації звіту: {str(e)}"), 500



@app.route('/company-cars/data')
@login_required
def company_cars_data():
    try:
        cars = company_car.query.all()
        data = [{
            'car_number': car.car_number,
            'car_name': car.car_name,
            'company_name': car.company_name,
            'location': car.location,
            'fuel_type': car.fuel_type,
            'fuel_norm': car.fuel_norm,
            'tank_volume': car.tank_volume or '-',
            'public_insurance': car.public_insurance.strftime('%Y-%m-%d') if car.public_insurance else '-',
            'kasko_insurance': car.kasko_insurance.strftime('%Y-%m-%d') if car.kasko_insurance else '-',
            'id': car.id
        } for car in cars]
        return jsonify({'data': data})
    except Exception as e:
        logger.error(f"Error in company_cars_data: {str(e)}")
        return jsonify({'error': 'Не вдалося завантажити дані'}), 500

@app.route('/company-cars/add', methods=['POST'])
@login_required
def add_company_car():
    try:
        data = request.get_json()
        print(data)
        if not data or 'car_number' not in data or 'car_name' not in data:
            print('this')
            return jsonify({'error': 'Відсутні обов’язкові поля'}), 400

        new_car = company_car(
            car_number=data['car_number'],
            car_name=data['car_name'],
            company_name=data.get('company_name', ''),
            location=data.get('location', ''),
            public_insurance=data.get('public_insurance'),
            public_company=data.get('public_company', ''),
            kasko_insurance=data.get('kasko_insurance'),
            kasko_company=data.get('kasko_company', ''),
            plan_to=data.get('plan_to'),
            pay_date=data.get('payment_date'),  # Змінено з pay_date на payment_date
            created_at=datetime.now().date(),
            avtopark=data.get('avtopark')
        )
        db.session.add(new_car)
        db.session.commit()

        return jsonify({'success': True, 'car_id': new_car.id})
    except ValueError as ve:
        print('this 1')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Помилка при додаванні автомобіля'}), 500

@app.route('/company-autopark/pdf', methods=['GET'])
@login_required
def company_autopark_pdf():
    try:
        user = current_user
        user_id = user.id
        user_class = tm_users.get_users.Users(user_id)
        user_info = user_class.get_user_info()

        selected_month = int(request.args.get('month', datetime.now().month))
        selected_year = int(request.args.get('year', datetime.now().year))

        pdfmetrics.registerFont(TTFont('DejaVuSerif', 'static/fonts/DejaVuSerif.ttf'))
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=20, leftMargin=20, rightMargin=20)
        elements = []

        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.fontName = 'DejaVuSerif'
        title_style.fontSize = 16
        title_style.alignment = 1

        normal_style = styles['Normal']
        normal_style.fontName = 'DejaVuSerif'
        normal_style.fontSize = 8
        normal_style.wordWrap = 'CJK'
        normal_style.alignment = 1

        header_style = ParagraphStyle(
            name='HeaderStyle',
            fontName='DejaVuSerif',
            fontSize=8,
            alignment=1,
            leading=10,
            wordWrap='CJK'
        )

        month_names_uk = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
                          "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
        month_name = month_names_uk[selected_month - 1]
        generation_date = datetime.now().strftime('%d.%m.%Y')
        title = Paragraph(f"Автопарк на {generation_date}", title_style)
        elements.append(title)
        elements.append(Spacer(1, 12))

        # Отримуємо всі автомобілі
        cars = company_car.query.filter_by(avtopark=1).all()
        car_data = []
        today = datetime.now().date()
        expiry_threshold = today + timedelta(days=5)

        for car in cars:
            if car.created_at and car.created_at > datetime(selected_year, selected_month,
                                                            monthrange(selected_year, selected_month)[1]).date():
                continue

            # Розрахунок заливки для кожного поля
            plan_to_expiring = car.plan_to and (car.plan_to - today).days <= 5  # Підсвітка, якщо <= 5 днів або минуло
            public_insurance_expiring = car.public_insurance and (
                        car.public_insurance - today).days <= 5  # Підсвітка, якщо <= 5 днів або минуло
            kasko_insurance_expiring = car.kasko_insurance and (
                        car.kasko_insurance - today).days <= 5  # Підсвітка, якщо <= 5 днів або минуло

            car_info = {
                'id': car.id,
                'П.І.Б.': car.location if car.location else ' ',
                'Держ. номер': car.car_number,
                'Марка/Модель': car.car_name,
                'Реєстрація': car.company_name if car.company_name else ' ',
                'План ТО': car.plan_to.strftime('%d.%m.%Y') if car.plan_to else ' ',
                'Страховка': car.public_insurance.strftime('%d.%m.%Y') if car.public_insurance else ' ',
                'Страхова компанія (Держ.)': car.public_company if car.public_company else ' ',
                'КАСКО': car.kasko_insurance.strftime('%d.%m.%Y') if car.kasko_insurance else ' ',
                'Страхова компанія (КАСКО)': car.kasko_company if car.kasko_company else ' ',
                'Дата оплати': car.pay_date if car.pay_date else '',
                # Додаємо поля для заливки
                'plan_to_expiring': plan_to_expiring,
                'public_insurance_expiring': public_insurance_expiring,
                'kasko_insurance_expiring': kasko_insurance_expiring
            }
            car_data.append(car_info)

        # Сортуємо за "Реєстрація"
        car_data.sort(key=lambda x: x['id'] if x['id'] != 'Не вказано' else '', reverse=True)

        # Формуємо заголовки таблиці
        table_headers = [
            Paragraph("№", header_style),
            Paragraph("П.І.Б.", header_style),
            Paragraph("Держ.<br/>номер", header_style),
            Paragraph("Марка/Модель", header_style),
            Paragraph("Реєстрація", header_style),
            Paragraph("План ТО", header_style),
            Paragraph("Страховка", header_style),
            Paragraph("Страхова компанія (Держ.)", header_style),
            Paragraph("КАСКО", header_style),
            Paragraph("Страхова компанія (КАСКО)", header_style),
            Paragraph("Дата оплати", header_style),
        ]

        table_data = [table_headers]
        for index, car in enumerate(car_data, start=1):
            row = [
                str(index),
                car['П.І.Б.'],
                car['Держ. номер'],
                car['Марка/Модель'],
                car['Реєстрація'],
                car['План ТО'],
                car['Страховка'],
                car['Страхова компанія (Держ.)'],
                car['КАСКО'],
                car['Страхова компанія (КАСКО)'],
                car['Дата оплати'],
            ]
            table_data.append(row)

        # Створюємо таблицю
        table = Table(table_data, colWidths=[
            0.3 * inch,  # №
            1.0 * inch,  # П.І.Б.
            0.8 * inch,  # Держ. номер
            1.5 * inch,  # Марка/Модель
            1.3 * inch,  # Реєстрація
            1.0 * inch,  # План ТО
            0.8 * inch,  # Страховка
            0.8 * inch,  # Страхова компанія (Держ.)
            1.0 * inch,  # КАСКО
            0.8 * inch,  # Страхова компанія (КАСКО)
            1.4 * inch,  # Дата оплати
        ])

        # Базові стилі таблиці
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Додаємо умовне форматування на основі car_data
        for i, car in enumerate(car_data, start=1):
            if car['plan_to_expiring']:
                #print(f"plan_to: {(car['plan_to_date'] - today).days} {car['Марка/Модель']} red")
                table_style.append(('BACKGROUND', (5, i), (5, i), colors.Color(1, 0.8, 0.8)))  # Світло-червоний
            if car['public_insurance_expiring']:
                #print(f"public_insurance: {(car['public_insurance_date'] - today).days} {car['Марка/Модель']} red")
                table_style.append(('BACKGROUND', (6, i), (6, i), colors.Color(1, 0.8, 0.8)))  # Світло-червоний
            if car['kasko_insurance_expiring']:
                #print(f"kasko_insurance: {(car['kasko_insurance_date'] - today).days} {car['Марка/Модель']} red")
                table_style.append(('BACKGROUND', (8, i), (8, i), colors.Color(1, 0.8, 0.8)))  # Світло-червоний

        table.setStyle(TableStyle(table_style))
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)

        filename = f'autopark_report_{selected_month}_{selected_year}.pdf'
        response = make_response(buffer.getvalue())
        buffer.close()
        response.mimetype = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={filename}'
        return response

    except Exception as e:
        return render_template('error.html', message=f"Помилка при генерації звіту: {str(e)}"), 500


@app.route('/company-cars/mileage', methods=['POST'])
@login_required
def update_mileage():
    data = request.get_json()
    car_id = int(data['car_id'])
    # Отримуємо дату з форми і фіксуємо її на 1-е число місяця
    input_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    fixed_date = input_date.replace(day=1)  # Завжди 1-е число місяця
    mileage = int(data['mileage'])
    fuel_added = float(data['fuel_added']) if data.get('fuel_added') else None
    public_insurance = datetime.strptime(data['public_insurance'], '%Y-%m-%d').date() if data.get('public_insurance') else None
    kasko_insurance = datetime.strptime(data['kasko_insurance'], '%Y-%m-%d').date() if data.get('kasko_insurance') else None

    car = company_car.query.get_or_404(car_id)

    # Перевіряємо, чи є запис за цей місяць
    mileage_record = car_mileage.query.filter_by(car_id=car_id, date=fixed_date).first()

    if mileage_record:
        # Якщо запис існує, оновлюємо його
        mileage_record.mileage = mileage
        mileage_record.fuel_added = fuel_added
        mileage_record.public_insurance = public_insurance
        mileage_record.kasko_insurance = kasko_insurance
    else:
        # Якщо запису немає, створюємо новий
        new_mileage = car_mileage(
            car_id=car_id,
            date=fixed_date,  # Фіксуємо на 1-е число
            mileage=mileage,
            fuel_added=fuel_added,
            public_insurance=public_insurance,
            kasko_insurance=kasko_insurance
        )
        db.session.add(new_mileage)

    # Оновлення страховок в основній таблиці, якщо вони передані
    if public_insurance:
        car.public_insurance = public_insurance
    if kasko_insurance:
        car.kasko_insurance = kasko_insurance

    db.session.commit()
    return jsonify({'success': True})

@app.route('/company-cars/delete/<int:car_id>', methods=['DELETE'])
@login_required
def delete_company_car(car_id):
    print(car_id)
    car = company_car.query.filter_by(id=car_id).delete()
    db.session.commit()
    return jsonify({'message': 'Автомобіль успішно видалено'}), 200


@app.route('/calendar')
@login_required
def calendar_view():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    import locale
    # Встановлення української локалі
    locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

    current_month = datetime.now().month
    if 'month' in request.args:
        current_month = int(request.args['month'])

    current_year = datetime.now().year
    if 'year' in request.args:
        current_year = int(request.args['year'])
    # Знаходження першого дня наступного місяця
    first_day_of_current_month = datetime(current_year, current_month, 1)
    first_day_of_next_month = datetime(current_year, current_month + 1, 1) if current_month < 12 else datetime(
        current_year + 1, 1, 1)

    # Віднімання одного дня від першого дня наступного місяця для отримання останнього дня поточного місяця
    last_day_of_current_month = first_day_of_next_month - timedelta(days=1)

    # Використання циклу для формування списку дат
    #formatted_dates = [f"{day:02d}.{current_month:02d}<br>{datetime(current_year, current_month, day).strftime('%a')}"
    #                   for day in range(1, last_day_of_current_month.day + 1)]

    formatted_dates = [
        {
            "day_info": f"{day:02d}.{current_month:02d}<br>{datetime(current_year, current_month, day).strftime('%a')}",
            "day_id": day,
            # Додайте іншу необхідну інформацію тут
        }
        for day in range(1, last_day_of_current_month.day + 1)
    ]

    day_now = datetime.now() - timedelta(days=3)

    filename = f'data_files/user_info_list_{current_month}_{current_year}.pkl'
    print(filename)

    # Перевірка, чи існує файл
    """if os.path.exists(filename):
        # Якщо файл існує, завантажуємо дані з Pickle
        with open(filename, 'rb') as f:
            filtered_list = pickle.load(f)

        if user_id != 11:
            get_user_departaments = users_departament.query.filter(users_departament.user_id == user_id,
                                                                   users_departament.access_level >= 1).all()
            dep_id_list = []
            for u_dep in get_user_departaments:
                dep_name = departaments.query.filter_by(id=u_dep.dep_id).first().dep_name
                dep_id_list.append(dep_name)
            print(dep_id_list)
            desired_department = tm_users.get_users.Users(user_id).get_user_info()
            user_info_list = [user_info for user_info in filtered_list if
                             user_info.get('user_departament') in dep_id_list]
        else:
            user_info_list = filtered_list

    else:"""
    user_info_list = tm_users.get_users.Users(user_id).get_users_calendar_info1(user_id, first_day_of_current_month,
                                                                                    last_day_of_current_month)

    # Отримання записів з бази даних
    departaments_edit = users_departament.query.filter_by(user_id=user_id, access_level=6).all()
    department_ids = [record.dep_id for record in departaments_edit]
    # Переконайтеся, що ви імпортували модель 'User'
    if user_info['user_access'] == 1:
        user_ids = users.query.with_entities(users.id).all()
        user_sub_id = []
    else:
        user_ids = users.query.filter(users.user_departament.in_(department_ids)).with_entities(users.id).all()
        user_sub_id = user_head.query.filter_by(head_id=user_id).all()
    user_ids = [uid[0] for uid in user_ids]  # Розпакування ID з результатів запиту
    user_ids.append(user_id)
    for use in user_sub_id:
        user_ids.append(use.user_id)
    this_month = datetime.now().month

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    user_transport = users.query.filter_by(transportation=1).all()
    return render_template('calendar/calendar.html', user_info=user_info, current_month=current_month,
                           days_list=formatted_dates, users_info=user_info_list, today=day_now.day, edit_list=user_ids,
                           this_month=this_month, current_year=current_year, vacation_report_access=vacation_report_access,
                           user_transport=user_transport)


@app.route('/calendar-event', methods=['POST'])
@login_required
def handle_calendar_event():
    get_current_user = current_user.id
    if request.method == 'POST':
        # Отримайте дані з форми
        user_id = request.form.get('user_id')
        date = request.form.get('date_input')
        this_month = request.form.get('this_month')
        worked_hours = request.form.get('workedHours')
        planned_hours = request.form.get('plannedHours')
        absent = request.form.get('absentCheck')
        absence_reason = request.form.get('reason_realy')
        comment = request.form.get('comment')
        car_used = request.form.get('ownCar')
        fuelLiters = request.form.get('fuelLiters')
        fuelComment = request.form.get('fuelComment')
        work_status = 1

        add_work = None

        if fuelComment:
            fuelComment = fuelComment + "|" + str(fuelLiters) + ' л.'

        print(car_used, fuelLiters, fuelComment)
        avto_cls = tm_users.get_users.UserAuto(user_id)
        get_user_car_info = avto_cls.get_user_car_info()

        print('car_used------', car_used)

        if car_used:
            print(get_user_car_info)
            get_fuel_limits = user_car.query.filter_by(user_id=user_id).order_by(user_car.id.desc()).first()
            if get_fuel_limits:
                liters = (get_fuel_limits.fuel_limit / 100) * get_fuel_limits.distance

                get_count_fuel_today = fuel_data.query.filter(
                    fuel_data.user_id == user_id,
                    fuel_data.date_refuel == date,
                    fuel_data.quantity.between(liters - 0.001, liters + 0.001)
                ).first()
                print('-==============', get_count_fuel_today, user_id, date, liters)
                if not get_count_fuel_today and not fuelComment:
                    avto_cls.add_fuel_deff(liters, None, get_user_car_info, date)

        if fuelLiters:
            print(get_user_car_info)
            avto_cls.add_fuel_deff(fuelLiters, fuelComment, get_user_car_info, date)

        print(absence_reason)

        if absence_reason == 'Додатково вийшов' or absence_reason == 'additionalHoursCheck':
            add_work = 1

        try:
            reason_dict = {'Хворіє': 'dripicons-medical', 'Хворіє з лікарняним': 'dripicons-pulse',
                       'Відгул':'dripicons-return', 'Нез\'ясовані причини': 'dripicons-cross',
                       'Відрядження': 'dripicons-suitcase', 'Відпросився': 'dripicons-time-reverse', 'Навчання': 'dripicons-store',
                       'Додатково вийшов':'dripicons-jewel', 'Віддалена робота': 'dripicons-home',
                       'Компенсація відпустки':'dripicons-card', 'Відпустка за свій рахунок':'dripicons-hourglass',
                       'Затримався або вийшов раніше': 'dripicons-media-loop',
                       'medicalReason': 'dripicons-medical', 'flagReason': 'dripicons-return',
                       'gamingReason': 'dripicons-cross', 'medicalReasonLikar': 'dripicons-pulse',
                       'suitcaseReason': 'dripicons-suitcase', 'crossReason': 'dripicons-time-reverse',
                       'todoReason': 'dripicons-store', 'remoteWork': 'dripicons-home',
                       'additionalHoursCheck': 'dripicons-jewel', 'mymoneyReason': 'dripicons-hourglass',
                        'vidabopiz':'dripicons-media-loop'
                   }
            absence_reason = reason_dict[absence_reason]
            print('absence_reason | ', absence_reason)
        except:
            absence_reason = None

        if worked_hours == '':
            worked_hours = planned_hours

        check_old = calendar_work.query.filter_by(today_date=date, user_id=user_id).first()

        """if not absence_reason:
            absence_reason = 'work'
            if worked_hours is not None and planned_hours is not None:
                if float(worked_hours) > float(planned_hours):
                    absence_reason = 'work'
                if float(worked_hours) < float(planned_hours):
                    absence_reason = 'work'"""


        if check_old:
            work_status = check_old.work_status
            print(absence_reason, absence_reason)

            if absence_reason != None:
                calendar_work.query.filter_by(id=check_old.id).update(dict(work_fact=worked_hours, work_time=planned_hours,
                                                                           work_status=work_status, reason=absence_reason))
            db.session.commit()
            if len(comment) > 1:
                add_comment = work_comments(records_id=check_old.id, user_id=user_id, comment=comment, dt_event=datetime.now(),
                                            user_add_comment=get_current_user)
                db.session.add(add_comment)
            if fuelComment != '' and fuelComment != None:
                add_comment_fuel = work_comments(records_id=check_old.id, user_id=user_id, comment=fuelComment,
                                            dt_event=datetime.now(),
                                            user_add_comment=get_current_user)
                db.session.add(add_comment_fuel)
            db.session.commit()
            db.session.close()
        else:
            print(absence_reason, absence_reason)
            add_calendar = calendar_work(today_date=date, user_id=int(user_id), work_fact=worked_hours,
                                         work_time=planned_hours, reason=absence_reason, work_status=work_status)
            db.session.add(add_calendar)
            db.session.commit()
            records_id = add_calendar.id
            if len(comment) > 1:
                add_comment = work_comments(records_id=records_id, user_id=int(user_id), comment=comment,
                                            dt_event=datetime.now(), user_add_comment=get_current_user)
                db.session.add(add_comment)
            db.session.commit()

            db.session.close()

        color_dict = {
            'dripicons-medical': '#587a3a', 'dripicons-return': '#00B0F0',
            'dripicons-cross': '#FF0000', 'dripicons-suitcase': '#C65911',
            'dripicons-time-reverse': '#FFBA00', 'dripicons-store': '#FFFF00',
            'dripicons-jewel': '#CEA5FF', 'dripicons-home': '#A64D79',
            'dripicons-hourglass': '#bdc4ff', 'dripicons-card': '#ff8a82',
            'dripicons-media-loop': '#ea78fc', 'dripicons-pulse': '#9aba29'
            # додайте інші причини та кольори за потреби...
        }


        # Отримання кольору на основі коду іконки
        color_code = color_dict.get(absence_reason, '#FFFFFF')  # Використовуйте білий як запасний колір

        response_data = {
            "reason": absence_reason,
            "work_status": "vacation-day" if absence_reason == 'dripicons-flag' else "work-day",
            "work_time": worked_hours,
            "difference": str(float(worked_hours) - float(planned_hours)),  # Припустимо, що це розрахунок різниці
            "comment": comment,
            "date": date,
            "user_id": user_id,
            "color_code": color_code,
            "color_status": work_status
        }
        add_log = log_system(user_id=get_current_user, type_event=f'Створив подію в календарі про {user_id}')
        db.session.add(add_log)
        db.session.commit()

        # Повернення JSON-відповіді
        return jsonify(response_data)


# Отримання даних про розвезення
@app.route('/api/get_transport_info', methods=['GET'])
def get_transport_info():
    user_id = request.args.get('userId')
    date = request.args.get('date')

    if not user_id or not date:
        return jsonify({'error': 'Missing userId or date parameter'}), 400

    try:
        # Перетворюємо рядок дати у формат datetime.date
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()

        # Запит до бази
        transport = db.session.query(employee_transport).filter_by(user_id=user_id, date=date_obj).first()

        response = {
            'dayShift': transport.day_shift if transport else False,
            'nightShift': transport.night_shift if transport else False,
            'dayComment': transport.day_comment if transport else '',  # Повертаємо коментар для ранку
            'nightComment': transport.night_comment if transport else ''  # Повертаємо коментар для вечора
        }
        return jsonify(response)
    except ValueError as ve:
        return jsonify({'error': f'Invalid date format: {str(ve)}'}), 400
    except Exception as e:
        app.logger.error(f'Error in get_transport_info: {str(e)}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/save_transport_info', methods=['POST'])
def save_transport_info():
    data = request.get_json()

    required_fields = ['userId', 'date', 'dayShift', 'nightShift']
    if not all(key in data for key in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        user_id = int(data['userId'])
        date = data['date']
        day_shift = bool(int(data['dayShift']))
        night_shift = bool(int(data['nightShift']))
        day_comment = data.get('dayComment', '')  # Коментар для ранку
        night_comment = data.get('nightComment', '')  # Коментар для вечора

        # Перетворюємо рядок дати у формат datetime.date
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()

        # Перевіряємо, чи існує запис
        transport = db.session.query(employee_transport).filter_by(user_id=user_id, date=date_obj).first()

        if transport:
            # Оновлюємо існуючий запис
            transport.day_shift = day_shift
            transport.night_shift = night_shift
            transport.day_comment = day_comment
            transport.night_comment = night_comment
            # Якщо обидва поля стають False, видаляємо запис
            if not day_shift and not night_shift:
                db.session.delete(transport)
        else:
            # Створюємо новий запис, якщо хоча б одна зміна увімкнена
            if day_shift or night_shift:
                transport = employee_transport(
                    user_id=user_id,
                    date=date_obj,
                    day_shift=day_shift,
                    night_shift=night_shift,
                    day_comment=day_comment,
                    night_comment=night_comment
                )
                db.session.add(transport)

        db.session.commit()
        return jsonify({
            'success': True,
            'dayComment': day_comment,  # Повертаємо для перевірки
            'nightComment': night_comment
        })
    except ValueError as ve:
        return jsonify({'error': f'Invalid data format: {str(ve)}'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error in save_transport_info: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_calendar_info', methods=['GET'])
@login_required
def get_calendar_info():
    user_id = request.args.get('userId')
    date = request.args.get('date')

    # Отримайте інформацію з бази даних або будь-які інші обчислення, які вам потрібні
    # Поверніть результат у форматі JSON
    get_work = calendar_work.query.filter_by(user_id=user_id, today_date=date).first()
    get_user_car = user_car.query.filter_by(user_id=user_id).first()
    get_user_fuel_data = fuel_data.query.filter_by(user_id=user_id, date_refuel=date).first()

    try:
        if get_work.work_status == 2 and not get_user_fuel_data:
            get_user_car = False
    except Exception as e:
        print(e)

    try:
        get_reason = get_work.reason
        print(get_reason)
        reason_dict = {
            'dripicons-medical': 'medicalReason',
            'dripicons-return': 'flagReason',
            'dripicons-gaming': 'gamingReason',
            'dripicons-suitcase': 'suitcaseReason',
            'dripicons-time-reverse': 'crossReason',
            'dripicons-media-loop': 'vidabopiz',
            'dripicons-hourglass': 'mymoneyReason',
            'dripicons-store': 'todoReason',
            'dripicons-home': 'remoteWork',
            'dripicons-jewel': 'additionalHoursCheck',
            'dripicons-pulse': 'medicalReasonLikar',
            'work': None
        }
        reason = reason_dict[get_reason]
    except:
        reason = None


    try:
        calendar_info = {
            'id': get_work.id,
            'user_id': user_id,
            'date': date,
            'plan_work': get_work.work_time,
            'fact_work': get_work.work_fact,
            'comments': [],
            'abs_reason': reason,
            'car': True if get_user_car else False,
            'color_status': get_work.work_status
        }
    except:
        calendar_info = {
            'id': None,
            'user_id': None,
            'date': None,
            'plan_work': None,
            'fact_work': None,
            'car': True if get_user_car else False,
            'comments': [],
            'abs_reason': None,
            'color_status': 1
        }

    try:
        get_comment_list = work_comments.query.filter_by(records_id=get_work.id).all()
    except:
        get_comment_list = None

    if get_comment_list:
        for coment in get_comment_list:
            if len(str(coment.comment))>0:
                get_user = users.query.filter_by(id=coment.user_add_comment).first()
                day_info = {
                    'id_comment': coment.id,
                    'user_name': get_user.user_fullname if get_user else 'Не знайдено',
                    'comment': coment.comment,
                    'dt_event': coment.dt_event
                }

                calendar_info['comments'].append(day_info)
        print(calendar_info)
    return jsonify(calendar_info)


@app.route('/delete-comment', methods=['POST'])
def delete_comment():
    try:
        comment_to_delete = request.form.get('commentId')  # Отримуємо текст коментаря з запиту
        get_comment_delete = work_comments.query.filter_by(id=comment_to_delete).first()

        if 'л.' in get_comment_delete.comment:
            user_id = get_comment_delete.user_id
            fuel_data.query.filter_by(comments=get_comment_delete.comment, user_id=user_id).delete()
            work_comments.query.filter_by(id=comment_to_delete).delete()

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        # Якщо виникла помилка під час видалення, поверніть відповідь з помилкою
        print(e)
        return jsonify({'success': False, 'error': str(e)})


@app.route('/profile-<int:profile_id>')
@login_required
def user_profile_page(profile_id):
    user = current_user
    user_id = user.id
    year_now = int(request.args.get('year', datetime.now().year))

    # Отримання поточного користувача
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    last_day_of_last_year = date(year_now, 1, 1) - timedelta(days=1)
    used_days_before = calendar_work.query.filter(
        calendar_work.reason.in_(['dripicons-card', 'vacation']),
        calendar_work.user_id == profile_id,
        calendar_work.today_date <= last_day_of_last_year
    ).count()

    get_before_vacation_days_sum = db.session.query(
        func.sum(vacation.count_days)
    ).filter(
        vacation.years < year_now, vacation.user_id == profile_id
    ).scalar() or 0

    get_before_canceled_days = (
        vacations_canceled.query
        .with_entities(func.coalesce(func.sum(vacations_canceled.count_days), 0))
        .filter(and_(
            vacations_canceled.user_id == profile_id,
            vacations_canceled.year < year_now
        ))
        .scalar()
    )


    available_from_previous_years = get_before_vacation_days_sum - used_days_before - get_before_canceled_days

    get_count_canceled_days_this_year = vacations_canceled.query.filter_by(user_id=profile_id, year=year_now).first()
    count_canceled_days_this_year = 0
    if get_count_canceled_days_this_year:
        count_canceled_days_this_year = get_count_canceled_days_this_year.count_days

    # Перший день поточного року (1 січня)
    first_day_of_current_year = datetime(year_now, 1, 1)

    # Останній день поточного року (31 грудня)
    last_day_of_current_year = datetime(year_now, 12, 31, 23, 59, 59)
    used_vacation_in_this_year = calendar_work.query.filter(
        calendar_work.reason == 'vacation',
        calendar_work.user_id == profile_id,
        calendar_work.today_date >= first_day_of_current_year,
        calendar_work.today_date <= last_day_of_current_year
    ).count()

    used_compensation_in_this_year = calendar_work.query.filter(
        calendar_work.reason == 'dripicons-card',
        calendar_work.user_id == profile_id,
        calendar_work.today_date >= first_day_of_current_year,
        calendar_work.today_date <= last_day_of_current_year
    ).count()

    get_count_days_vacation_this_days = vacation.query.filter_by(user_id=profile_id, years=year_now).first()
    count_vacation_days_in_this_year = 0
    if get_count_days_vacation_this_days:
        count_vacation_days_in_this_year = get_count_days_vacation_this_days.count_days

    diff_vacation_this_year = (count_vacation_days_in_this_year + available_from_previous_years ) - (used_vacation_in_this_year + used_compensation_in_this_year) - count_canceled_days_this_year
    total_vacations = available_from_previous_years + diff_vacation_this_year

    # Перший день наступного року (1 січня наступного року)
    first_day_of_next_year = datetime(year_now + 1, 1, 1)

    # Останній день наступного року (31 грудня наступного року)
    last_day_of_next_year = datetime(year_now + 1, 12, 31, 23, 59, 59)

    # Фільтрація по датах для наступного року
    used_vacation_in_next_year = calendar_work.query.filter(
        calendar_work.reason == 'vacation',
        calendar_work.user_id == profile_id,
        calendar_work.today_date >= first_day_of_next_year,
        calendar_work.today_date <= last_day_of_next_year
    ).count()

    next_year = int(datetime.now().year) + 1
    get_count_vacation_days_next_year = vacation.query.filter_by(user_id=profile_id, years=next_year).first()
    count_vacation_days_next_year = 0
    if get_count_vacation_days_next_year:
        count_vacation_days_next_year = get_count_vacation_days_next_year.count_days

    diff_vacation_next_year =  (diff_vacation_this_year) - used_vacation_in_next_year

    # Генерація списку років (від поточного до -10 років)
    years_list = list(range(2023, datetime.now().year + 6))

    # Список керівників
    leaders_list = [
        {'head_id': head.head_id, 'head_name': users.query.get(head.head_id).user_fullname}
        for head in user_head.query.filter_by(user_id=profile_id).all()
    ]

    # Інформація про профіль
    profile_class = tm_users.get_users.Users(profile_id)
    profile_info = profile_class.get_user_info()
    departments_list = tm_depart.get_departament.Departaments().get_departaments_list()
    permission = profile_class.get_premission(profile_id)
    users_list = profile_class.get_all_users()

    vacation_list = profile_class.get_all_vacations_year_info()
    print(vacation_list)

    current_year_vacation = calendar_work.query.filter(
        calendar_work.reason == 'vacation',
        calendar_work.user_id == profile_id,
        calendar_work.today_date.between(f'{year_now}-01-01', f'{year_now}-12-31')
    )
    # Отримання історії відпусток
    records = current_year_vacation.order_by(calendar_work.today_date).all()
    sequences = find_sequences(records)

    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    avto_cls = tm_users.get_users.UserAuto(profile_id)
    avto_info = avto_cls.get_user_car_info()


    return render_template(
        'profile/profile.html',
        user_info=user_info,
        profile_info=profile_info,
        departments=departments_list,
        user_id=profile_id,
        count_day_vacation=count_vacation_days_in_this_year,
        vacation_this_year=used_vacation_in_this_year,
        diff_vacation= diff_vacation_this_year,
        diff_vacation_next_year=diff_vacation_next_year,
        years_list=years_list,
        list_vacation=sequences,
        department_access=permission,
        check_access=check_access,
        users_list=users_list,
        year_now=year_now,
        month_now=datetime.now().month,
        vacation_before=available_from_previous_years,
        leaders_list=leaders_list,
        vacation_list=vacation_list,
        vacation_report_access=vacation_report_access,
        get_used_money=used_compensation_in_this_year,
        count_vacation_canceled_days=count_canceled_days_this_year,
        car_info=avto_info
    )


@app.route('/update-access-head', methods=['POST'])
@login_required
def update_access_head():
    # Отримуємо дані з форми
    selected_head_id = request.form.get('access_head')
    user_id = request.form.get('user_id')
    add_user = user_head(user_id=user_id, head_id=selected_head_id)

    db.session.add(add_user)
    db.session.commit()
    # Після обробки, перенаправляємо користувача на головну сторінку або іншу відповідну сторінку
    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/update-access-rights', methods=['POST'])
def update_access_rights():
    user_id = request.form.get('user_id')
    users_departament.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    for department in departaments.query.all():
        # Ініціалізація прав доступу
        access_level = 0

        # Отримуємо значення чекбоксів
        read = request.form.get(f'read_{department.id}') == 'on'
        edit = request.form.get(f'edit_{department.id}') == 'on'

        # Встановлення числових значень для прав доступу
        if read:
            access_level += 4  # Додавання права на читання
        if edit:
            access_level += 2  # Додавання права на редагування

        if access_level != 0:
            # Оновлення або створення нового запису в таблиці users_departament
            user_department_access = users_departament.query.filter_by(user_id=user_id, dep_id=department.id,
                                                                       access_level=access_level).first()
            if user_department_access:
                users_departament.query.filter_by(user_id=user_id,
                                                  dep_id=department.id).update(dict(access_level=access_level))
            else:
                new_access = users_departament(user_id=user_id, dep_id=department.id, access_level=access_level)
                db.session.add(new_access)

        db.session.commit()
    # Після обробки перенаправте користувача на відповідну сторінку
    return redirect(url_for('user_profile_page', profile_id=user_id))

@app.route('/set-vacation-days', methods=['POST'])
@login_required
def set_vacation_days():
    vacation_year = request.form.get('vacation_year')
    vacation_days = request.form.get('vacation_days')  # Отримуємо список дат
    user_id = request.form.get('user_id')

    # Логіка для обробки кожної відпустки
    vacation.query.filter_by(user_id=user_id, years=vacation_year).delete()
    db.session.commit()
    add_new_vacation_days = vacation(user_id=user_id, count_days=vacation_days, years=vacation_year)
    db.session.add(add_new_vacation_days)
    db.session.commit()

    # Перенаправлення користувача на іншу сторінку після обробки
    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/set-canceled-vacation-days', methods=['POST'])
@login_required
def set_canceled_vacation_days():
    print(request.form)
    canceled_year = request.form.get('canceled_year')
    canceled_days = request.form.get('canceled_days')  # Get the number of canceled days
    user_id = request.form.get('user_id')

    # Check for missing values
    if not canceled_year or not canceled_days:
        # If data is missing, show an error or handle the situation
        return "Помилка: відсутні необхідні дані", 400

    # Convert the values to integers, if they are valid
    try:
        canceled_days = int(canceled_days)
        canceled_year = int(canceled_year)
    except ValueError:
        return "Помилка: некоректне значення для року або кількості днів", 400

    # Check if the number of canceled days is valid (greater than 0)
    if canceled_days < 0:
        return "Помилка: кількість днів повинна бути більшою за 0", 400

    # Logic for processing vacation days
    # First, delete any existing records for this user and year
    vacations_canceled.query.filter_by(user_id=user_id, year=canceled_year).delete()
    db.session.commit()

    # Add a new canceled vacation day entry
    add_new_canceled_days = vacations_canceled(user_id=user_id, count_days=canceled_days, year=canceled_year)
    db.session.add(add_new_canceled_days)
    db.session.commit()

    # Redirect the user after processing
    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/set-vacation-period', methods=['POST'])
@login_required
def set_vacation_period():
    vacation_periods = request.form.getlist('vacation_start[]')
    user_id = request.form.get('user_id')

    for period in vacation_periods:
        if period:  # Перевіряємо, чи поле не пусте
            start_date_str, end_date_str = period.split(' - ')
            start_date = datetime.strptime(start_date_str, '%m/%d/%Y').date()
            end_date = datetime.strptime(end_date_str, '%m/%d/%Y').date()

            # Знаходимо всі записи, які будуть замінені на відпустку
            records_to_backup = calendar_work.query.filter(
                and_(
                    calendar_work.today_date >= start_date,
                    calendar_work.today_date <= end_date,
                    calendar_work.user_id == user_id
                )
            ).all()

            # Зберігаємо дані в тимчасову таблицю
            for record in records_to_backup:
                temp_record = calendar_work_temp(
                    original_id=record.id,
                    today_date=record.today_date,
                    user_id=record.user_id,
                    work_time=record.work_time,
                    work_status=record.work_status,
                    work_fact=record.work_fact,
                    reason=record.reason
                )
                db.session.add(temp_record)

            # Оновлюємо записи на 'vacation'
            calendar_work.query.filter(
                and_(
                    calendar_work.today_date >= start_date,
                    calendar_work.today_date <= end_date,
                    calendar_work.user_id == user_id
                )
            ).update({'reason': 'vacation'})

            db.session.commit()

    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/set-work-schedule', methods=['POST'])
@login_required
def set_work_schedule():
    hours_plan = request.form.get('hours_plan')
    working_days = request.form.get('working_days')
    off_days = request.form.get('off_days')
    user_id = request.form.get('user_id')
    graphic_start = request.form.get('graphic_start')
    start_date_str, end_date_str = graphic_start.split(' - ')

    # Перетворення рядків у об'єкти datetime
    start_date = datetime.strptime(start_date_str, '%m/%d/%Y')
    end_date = datetime.strptime(end_date_str, '%m/%d/%Y')

    days_option = request.form.get('days_option')

    monday_to_friday = 'monday_to_friday' in request.form
    calendar_work.query.filter(and_(calendar_work.today_date>=start_date, calendar_work.today_date<=end_date,
                                    calendar_work.user_id==user_id)).delete()
    db.session.commit()

    days_of_week = request.form.getlist('days_of_week[]')
    if working_days and off_days:
        current_day = 0  # Лічильник для контролю чергування робочих та вихідних днів
        while start_date <= end_date:
            if current_day % (int(working_days) + int(off_days)) < int(working_days):
                # Створення запису в базі даних для робочого дня
                new_entry = calendar_work(
                    today_date=start_date,
                    user_id=user_id,
                    work_time=hours_plan,
                    work_status=1,
                    work_fact=hours_plan,
                    reason='work'
                )
                db.session.add(new_entry)

            start_date += timedelta(days=1)
            current_day += 1

        db.session.commit()

        # Перенаправлення користувача на іншу сторінку після обробки
        return redirect(url_for('user_profile_page', profile_id=user_id))

    elif monday_to_friday:
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:  # 0-4 для понеділка-п'ятниці
                new_entry = calendar_work(
                    today_date=current_date,
                    user_id=user_id,
                    work_time=hours_plan,
                    work_status=1,
                    work_fact=hours_plan,
                    reason='work'
                )
                db.session.add(new_entry)
            current_date += timedelta(days=1)

        db.session.commit()

        return redirect(url_for('user_profile_page', profile_id=user_id))

    else:
        cycle=[]
        current_date = start_date
        workdays_cycle = [2, 3, 2, 2, 3, 2]  # Послідовність робочих та вихідних днів

        while current_date <= end_date:
            for index, days in enumerate(workdays_cycle):
                # Перевіряємо, чи є індекс парним
                if index % 2 == 0:
                    # Додаємо до списку робочі дні
                    for _ in range(days):
                        cycle.append(current_date)  # Додаємо поточну дату як робочий день
                        current_date += timedelta(days=1)  # Переходимо до наступної дати
                else:
                    # Пропускаємо вихідні дні
                    current_date += timedelta(days=days)
        print(cycle)
        for info in cycle:
            new_entry = calendar_work(
                today_date=info,
                user_id=user_id,
                work_time=hours_plan,
                work_status=1,
                work_fact=hours_plan,
                reason='work'
            )
            db.session.add(new_entry)

    db.session.commit()

    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    user_id = request.form.get('user_id')
    file = request.files['avatar']

    print(f"Оригінальне ім'я файлу: {file.filename}")  # Додайте цей рядок для відладки

    if file and allowed_file(file.filename):
        file_name = 'avatar_' + str(user_id) + '_' + '.png'
        new_avatar = os.path.join("static/upload", file_name)  # Змінено формування шляху

        print(f"Безпечне ім'я файлу: {file_name}")  # Ще один рядок для відладки
        print(f"Шлях до файлу: upload/{file_name}")  # І ще один

        file.save(new_avatar)


        users.query.filter_by(id=user_id).update(dict(user_avatar=new_avatar))
        db.session.commit()

        return jsonify(success=True, newAvatarUrl=f'static/upload/{file_name}')


@app.route('/delete-vacation', methods=['DELETE'])
@login_required
def delete_vacation():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    user_id = request.args.get('user_id')

    # Конвертуємо дати
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # Знаходимо всі записи відпустки
    vacation_records = calendar_work.query.filter(
        and_(
            calendar_work.today_date >= start_date,
            calendar_work.today_date <= end_date,
            calendar_work.reason == 'vacation',
            calendar_work.user_id == user_id
        )
    ).all()

    # Для кожного запису шукаємо відповідний запис у temp таблиці
    for vacation_record in vacation_records:
        # Шукаємо збережені дані з temp
        temp_record = calendar_work_temp.query.filter(
            and_(
                calendar_work_temp.original_id == vacation_record.id,
                calendar_work_temp.user_id == user_id
            )
        ).first()

        if temp_record:
            # Відновлюємо дані з temp таблиці
            vacation_record.work_time = temp_record.work_time
            vacation_record.work_status = temp_record.work_status
            vacation_record.work_fact = temp_record.work_fact
            vacation_record.reason = temp_record.reason

            # Видаляємо temp запис
            db.session.delete(temp_record)
        else:
            # Якщо немає backup, просто видаляємо запис
            db.session.delete(vacation_record)

    db.session.commit()

    return jsonify({'success': True})


@app.route('/update-vacation', methods=['POST'])
def update_vacation():
    vacation_id = request.form.get('vacationId')
    user_id = request.form.get('userId')
    start_date = request.form.get('startDate')
    end_date = request.form.get('endDate')
    original_start_date = request.form.get('originalStartDate')
    original_end_date = request.form.get('originalEndDate')

    # Конвертація дат з рядків у об'єкти datetime
    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    original_start_date = datetime.strptime(original_start_date, '%Y-%m-%d').date()
    original_end_date = datetime.strptime(original_end_date, '%Y-%m-%d').date()

    print('--- --- --- --- --- --- ---')
    print(start_date, end_date)
    print(original_start_date, original_end_date)
    print('--- '*7)

    calendar_work.query.filter(and_(calendar_work.today_date >= original_start_date,
                                    calendar_work.today_date <= original_end_date,
                                    calendar_work.user_id == user_id)).update(dict(reason='work'))
    calendar_work.query.filter(and_(calendar_work.today_date >= start_date, calendar_work.today_date <= end_date,
                                    calendar_work.user_id == user_id)).update(dict(reason='dripicons-flag'))
    db.session.commit()
    """calendar_work.query.filter(
        calendar_work.user_id == user_id,
        calendar_work.today_date >= original_start_date,
        calendar_work.today_date <= original_end_date,
        calendar_work.reason == 'dripicons-flag'
    ).delete()
    db.session.commit()

    if (end_date - start_date).days > 1:
        current_date = start_date
        while current_date <= end_date:
            calendar_work.query.filter_by(today_date=current_date, user_id=user_id).delete()
            new_entry = calendar_work(
                today_date=current_date,
                user_id=user_id,
                work_time=0,
                work_status=1,
                work_fact=0,
                reason='dripicons-flag'
            )
            db.session.add(new_entry)
            current_date += timedelta(days=1)

        db.session.commit()"""

    return redirect(url_for('user_profile_page', profile_id=user_id))


@app.route('/api/mark-as-working', methods=['POST'])
def mark_as_working():
    data = request.get_json()
    print('Отримані дані:', data)

    user_id = data.get('userId')
    date = data.get('date')
    own_car = data.get('ownCar') == '1'  # Перевіряємо '1' замість 'on'
    liters = data.get('liters')
    extra_comment = data.get('extraComment')

    print('-------------', own_car)

    if own_car:  # Використовуємо булеве значення
        try:
            get_fuel_limits = user_car.query.filter_by(user_id=user_id).order_by(user_car.id.desc()).first()
            if get_fuel_limits:
                liters = (get_fuel_limits.fuel_limit / 100) * get_fuel_limits.distance

            print('user_id:', user_id)
            print('date:', date)
            print('literssssss', liters)
            if liters:
                date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                date = date_obj.strftime('%Y-%m-%d')  # Тільки дата

                avto_cls = tm_users.get_users.UserAuto(user_id)
                get_user_car_info = avto_cls.get_user_car_info()
                print(get_user_car_info)
                avto_cls.add_fuel_deff(liters, extra_comment, get_user_car_info, date)
        except Exception as e:
            print(e)

    if None in (user_id, date):
        return jsonify({'error': 'Деякі дані не отримано'}), 400

    # Обробка дати
    try:
        date_only = date.split(' ')[0]
        date_obj = datetime.strptime(date_only, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Невірний формат дати'}), 400

    # Оновлення запису
    record = calendar_work.query.filter_by(user_id=user_id, today_date=date_obj).first()
    if not record:
        return jsonify({'error': 'Запис не знайдено'}), 404

    record.work_status = 2
    record.reason = 'work'
    # record.liters = liters  # Оновлене поле (розкоментуйте, якщо потрібно)
    # record.extra_comment = extra_comment  # Оновлене поле (розкоментуйте, якщо потрібно)

    db.session.commit()
    return jsonify({'message': 'Дані успішно оновлено'}), 200


@app.route('/api/mark-as-not-working', methods=['POST'])
def mark_as_not_working():
    try:
        data = request.json
        user_id = data.get('userId')  # Отримуємо userId
        date = data.get('date')       # Отримуємо дату, наприклад "2025-02-25 15:30:00"

        if not user_id or not date:
            return jsonify({'error': 'Відсутній userId або date'}), 400

        # Перетворюємо рядок дати у об'єкт datetime і беремо тільки дату
        date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').date()  # Отримуємо об'єкт date: 2025-02-25

        # Видаляємо записи з fuel_data для цього user_id і date_refuel
        fuel_data.query.filter_by(user_id=user_id, date_refuel=date_obj).delete()
        db.session.commit()

        # Видаляємо записи з calendar_work для цього user_id і today_date
        calendar_work.query.filter_by(user_id=user_id, today_date=date_obj).delete()
        db.session.commit()

        return jsonify({'message': 'Дані успішно видалено'}), 200

    except ValueError as e:
        # Помилка парсингу дати
        return jsonify({'error': f'Неправильний формат дати: {str(e)}'}), 400
    except Exception as e:
        # Інші помилки
        return jsonify({'error': f'Виникла помилка: {str(e)}'}), 500



@app.route('/update-user-status-<int:user_id>')
@login_required
def update_user_status(user_id):
    users.query.filter_by(id=user_id).update(dict(display=1))
    db.session.commit()
    return redirect(url_for('user_profile_page', profile_id=user_id))


def add_custom_header(canvas, doc, user_name, department, current_year, current_date, fop_subscribe, stage, user_age,
                      user_phone):
    canvas.saveState()
    width, height = landscape(A4)

    # Встановлення шрифту
    canvas.setFont('DejaVuSerif', 10)

    # Відступ зверху
    top_margin = inch * 0.5
    line_height = 12  # Приблизна висота рядка в пікселях

    # Додавання інформації користувача в лівий верхній кут
    user_info_lines = [f"ПІБ: {user_name}", f"Відділ: {department}", f"Оформлений на: {fop_subscribe}",
                       f"Стаж: {stage}", f"Вік: {user_age}", f"Номер телефону: {user_phone}"]
    for i, line in enumerate(user_info_lines):
        canvas.drawString(inch * 0.5, height - top_margin - (i * line_height), line)

    # Додавання поточного року та дати формування в правий верхній кут
    date_info_lines = [f"Рік звітності: {current_year}", f"Сформовано: {current_date}"]
    for i, line in enumerate(date_info_lines):
        # Для правого вирівнювання ми використовуємо drawRightString
        canvas.drawRightString(width - inch * 0.5, height - top_margin - (i * line_height), line)

    canvas.restoreState()


def get_calendar_vacation_data(user_id, year):
    records = db.session.query(calendar_work).filter(and_(calendar_work.reason == 'vacation',
                                                          calendar_work.user_id == user_id,
                                                          calendar_work.today_date.between(f"{year}-01-01",
                                                                                           f"{year}-12-31"))).order_by(
        calendar_work.today_date).all()

    sequences = find_sequences(records)
    after_now = []
    before_now = []

    for dt_records in sequences:
        new_dt = dt_records['end_date']
        if new_dt <= datetime.now().date():
            before_now.append(dt_records)  # Дати до сьогодні
        else:
            after_now.append(dt_records)  # Дати після сьогодні

    after_now_formatted = ["{} до {}".format(dt['start_date'].strftime('%d-%m-%Y'), dt['end_date'].strftime('%d-%m-%Y'))
                           for dt in after_now]
    before_now_formatted = [
        "{} до {}".format(dt['start_date'].strftime('%d-%m-%Y'), dt['end_date'].strftime('%d-%m-%Y')) for dt in
        before_now]

    compensation_records = db.session.query(calendar_work).filter(
        and_(
            calendar_work.reason == 'dripicons-card',
            calendar_work.today_date.between(f"{year}-01-01", f"{year}-12-31"),
            calendar_work.user_id == user_id
        )
    ).order_by(calendar_work.today_date).all()

    compensation_date = ['{}'.format(record.today_date.strftime('%d-%m-%Y')) for record in compensation_records]

    count_canceled_days = [vacations_canceled.query.with_entities(
        vacations_canceled.count_days
    ).filter_by(user_id=user_id, year=year).scalar() or 0]

    # Вирівнювання списків за довжиною, додавання пустих строк, якщо потрібно
    max_length = max(len(after_now_formatted), len(before_now_formatted), len(compensation_date), len(count_canceled_days))
    after_now_formatted += [""] * (max_length - len(after_now_formatted))
    before_now_formatted += [""] * (max_length - len(before_now_formatted))
    compensation_only = [""] * (max_length - len(compensation_date)) + compensation_date
    canceled_days_column = [""] * (max_length - len(count_canceled_days)) + count_canceled_days

    # Створення колонки "Анульовано днів" з одним значенням у верхньому рядку
    #canceled_days_column = [count_canceled_days] + [""] * (max_length - 1)

    # Створення даних для таблиці
    table_data = [["Минулі відпустки", "Майбутні відпустки", "Компенсовані", "Анульовано днів"]] + list(
        zip(before_now_formatted, after_now_formatted, compensation_only, canceled_days_column)
    )

    return table_data


@app.route('/report-<int:user_id>-<int:year>')
def generate_pdf(user_id, year):
    from dateutil.relativedelta import relativedelta
    user_info = users.query.filter_by(id=user_id).first()
    user_name = user_info.user_fullname
    join_delta = relativedelta(datetime.now(), user_info.join_date)
    join_years = join_delta.years
    join_month = join_delta.months
    join_days = join_delta.days
    stage = f"{join_years} роки {join_month} місяців {join_days} днів"

    # Обчислити різницю у роках і днях для age_difference
    age_delta = relativedelta(datetime.now(), user_info.birthdate)
    age_years = age_delta.years
    user_phone = f"{user_info.phone_num_one} ; {user_info.phone_num_two}"
    department = departaments.query.filter_by(id=user_info.user_departament).first().dep_name
    fop_subscribe = company_list.query.filter_by(id=user_info.company).first().company_name
    current_year = year
    current_date = datetime.now().strftime("%d-%m-%Y")

    pdfmetrics.registerFont(TTFont("DejaVuSerif", "static/fonts/DejaVuSerif.ttf"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=inch + 50, bottomMargin=inch, leftMargin=inch,
                            rightMargin=inch)
    elements = []

    months = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
              "Жовтень", "Листопад", "Грудень"]
    reasons = ["Додатково вийшов", "Відгули", "Відпустка", "Хворіє", "Відрядження", "Хворіє з лікарняним",
               "Нез'ясовані причини", "Відпросився", "Віддаленна робота", 'План годин', 'Факт годин',
               'Різниця годин']
    headers = ["Причини", "Рік"] + months

    # Виклик функції для отримання даних
    calendar_data = tm_users.get_users.get_calendar_data(user_id, reasons, year)
    vacation_data = get_calendar_vacation_data(user_id, year)
    vacation_table_data = vacation_data  # Використовуйте функцію, яка повертає table_data
    print(vacation_table_data)
    vacation_table = Table(vacation_table_data, colWidths=[2.5 * inch, 2.5 * inch], hAlign='CENTER')
    # Підготовка стилю для vacation_table
    vacation_table_style = TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), "DejaVuSerif"),
        # Ви можете додати інші стилі шрифту тут, якщо потрібно
    ])

    # Застосування стилю до vacation_table
    vacation_table.setStyle(vacation_table_style)
    table_data = [headers] + calendar_data
    table = Table(table_data, colWidths=[116, 60] + [52] * 12, repeatRows=1)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), "DejaVuSerif"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, inch * 0.5))  # Додавання простору перед таблицею, якщо потрібно
    elements.append(vacation_table)

    doc.build(elements,
              onFirstPage=lambda canvas, doc: add_custom_header(canvas, doc, user_name, department, current_year,
                                                    current_date, fop_subscribe, stage, age_years, user_phone),
              onLaterPages=lambda canvas, doc: add_custom_header(canvas, doc, user_name, department, current_year,
                                                 current_date, fop_subscribe, stage, age_years, user_phone))

    buffer.seek(0)
    response = make_response(buffer.getvalue())
    buffer.close()
    response.mimetype = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
    return response


@app.route('/vacation-report')
def generate_vacation_report_pdf():
    user = current_user
    user_id = user.id

    # Додати шрифт для підтримки українських літер
    pdfmetrics.registerFont(TTFont("DejaVuSerif", "static/fonts/DejaVuSerif.ttf"))

    year = datetime.now().year
    # Отримуємо дані про співробітників та їх відпустки
    employees = tm_users.get_users.get_employees_data(year, user_id)
    vacation_data = []

    # Формуємо список даних для таблиці
    for employee in employees:
        vacation_data.append({
            'department': employee['department'],
            'name': employee['name'],
            'vacation_taken': employee['vacation_taken'],
            'vacation_compensation': employee['vacation_compensation'],
            'vacation_left': employee['vacation_left'],
            'color': employee['color'],
        })

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30, bottomMargin=inch, leftMargin=inch, rightMargin=inch)
    elements = []

    date_formatted_pdf = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

    # Створюємо заголовок
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontName = "DejaVuSerif"  # Вказуємо шрифт для заголовка
    title = Paragraph(f"Звіт по відпустках на {date_formatted_pdf}", title_style)
    elements.append(title)

    # Створюємо таблицю
    table_data = [
        ["#", "Відділ", "ПІБ", "Відпустка\nвідгуляна", "Компенсація\nза відпустку", "Відпустка\nзалишилася"]
    ]  # Заголовки таблиці

    row_colors = []  # Список для кольорів рядків
    index = 1
    for employee in vacation_data:
        table_data.append([
            index,
            employee['department'],
            employee['name'],
            employee['vacation_taken'],
            employee['vacation_compensation'],
            employee['vacation_left'],
        ])
        row_colors.append(employee['color'])
        index += 1

    table = Table(table_data, colWidths=[0.5 * inch, 1.7 * inch, 2.3 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch], hAlign='CENTER')

    # Стилі для таблиці
    table_styles = [
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), "DejaVuSerif"),
    ]

    # Застосовуємо кольори до рядків
    # Застосовуємо кольори тільки до стовпця "ПІБ" (індекс 1 у таблиці)
    for i, color in enumerate(row_colors):
        if color:  # Якщо колір вказано
            table_styles.append(('BACKGROUND', (2, i + 1), (2, i + 1), colors.HexColor(color)))
        else:  # Якщо колір не вказано, залишаємо білий фон
            table_styles.append(('BACKGROUND', (2, i + 1), (2, i + 1), colors.white))

    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    # Функція для додавання номера сторінки
    def add_page_number(canvas, doc):
        page_number = canvas.getPageNumber()
        text = f"Сторінка {page_number}"
        canvas.setFont("DejaVuSerif", 10)  # Вказуємо шрифт для номера сторінки
        canvas.drawString(500, 20, text)  # Встановлюємо позицію тексту для номера сторінки

    # Створюємо PDF
    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)

    buffer.seek(0)
    response = make_response(buffer.getvalue())
    buffer.close()
    response.mimetype = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=vacation_report.pdf'
    return response


# Функція для генерації випадкового посилання
def generate_random_link(length=20):
    characters = string.ascii_letters + string.digits
    random_link = ''.join(random.choice(characters) for i in range(length))
    return random_link

# Функція для надсилання посилання на електронну пошту
def send_email(receiver_email, link):
    sender_email = "leshashupenko@gmail.com"
    password = "jivl tpaf gbtg mfiz"

    message = MIMEText(f"Click the link to reset your password: https://tabel.scania.dp.ua/recovery-{link}")
    message['Subject'] = 'Password Reset Link'
    message['From'] = sender_email
    message['To'] = sender_email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        print('send mail')

# Функція для запису посилання в базу даних
def save_link_to_database(user_id, link):
    add_secret = resetpassword(user_id=user_id, secret_key=link, end_dt=datetime.now() + timedelta(hours=1))
    db.session.add(add_secret)
    db.session.commit()

@app.route('/repass-<int:user_id>')
@login_required
def update_user_pass(user_id):
    get_user_info = users.query.filter_by(id=user_id).first()
    # Генеруємо випадкове посилання
    random_link = generate_random_link()

    # Вказуємо електронну адресу отримувача
    receiver_email = get_user_info.user_email

    # Надсилаємо посилання на електронну пошту
    send_email(receiver_email, random_link)

    # Записуємо посилання в базу даних разом з електронною адресою отримувача
    save_link_to_database(user_id, random_link)
    flash(f'Посилання для скидання паролю відправлено на {receiver_email}')
    return redirect(url_for('user_profile_page', profile_id=user_id))



@app.route('/recovery-<string:secret_key>', methods=['GET', 'POST'])
def recovery_user_pass(secret_key):
    print(secret_key)
    if request.method == 'POST':
        new_pass = request.form['newpass']
        get_user_id = resetpassword.query.filter(and_(resetpassword.secret_key==secret_key)).first()
        if get_user_id:
            user_id = get_user_id.user_id
            hash_pass = generate_password_hash(new_pass)
            users.query.filter_by(id=user_id).update(dict(user_pass=hash_pass))
            resetpassword.query.filter(and_(resetpassword.secret_key == secret_key)).delete()
            db.session.commit()
            return redirect(url_for('logout'))
        else:
            return jsonify({'error': 'timeout'})
    return render_template('users/recovery.html', secret_key=secret_key)


# Маршрут для обробки POST-запиту з даними порядку сортування
@app.route('/save-position-departaments', methods=['POST'])
def save_order():
    if request.method == 'POST':
        # Отримання даних порядку сортування з запиту
        departament_id = request.form.getlist('departament_id')
        order = request.form.getlist('order')
        #order_data = request.form.getlist('order')

        # Перетворення значень порядку сортування на цілі числа
        order = [int(o) for o in order]

        # Збірка пар (departament_id, order)
        data = zip(departament_id, order)

        # Оновлення бази даних
        for dep_id, order_value in data:
            departaments.query.filter_by(id=dep_id).update({'sort_num': order_value})
            db.session.commit()
        # Повертаємо успішну відповідь
        return redirect(url_for('users_departament_list_page'))
    else:
        # Якщо надійшов GET-запит на цей маршрут, можна зробити редірект на головну сторінку або відправити повідомлення про помилку
        return 'Метод дозволено тільки POST'



@app.route('/set-fuel-limit', methods=['POST'])
def set_fuel_limit():
    user_id = request.form['user_id']

    # Логіка для збереження даних в базі (потрібно адаптувати відповідно до вашої моделі)
    avto_cls = tm_users.get_users.UserAuto(user_id)
    avto_cls.add_user_fuel_month_limit(fuel_limit)
    # Перенаправлення на сторінку профілю
    return redirect(url_for('user_profile_page', profile_id=user_id))


# Обробка запиту для зміни машини
@app.route('/change-car', methods=['POST'])
def change_car():
    user_id = request.form['user_id']
    car_brand = request.form['car_brand']
    fuel_type = request.form['fuel_type']
    fuel_consumption = request.form['fuel_consumption']
    distance = request.form['distance']

    # Логіка для зміни машини в базі даних
    avto_cls = tm_users.get_users.UserAuto(user_id)

    get_user_car = avto_cls.check_user_avto()
    if get_user_car:
        avto_cls.update_user_avto(car_brand, fuel_consumption, fuel_type, distance)
    else:
        avto_cls.insert_user_avto(car_brand, fuel_consumption, fuel_type, distance)

    # Перенаправлення на сторінку профілю
    return redirect(url_for('user_profile_page', profile_id=user_id))



# Приймати POST-запити на URL '/api/delete-head'
@app.route('/api/delete-head', methods=['POST'])
def delete_head():
    # Отримати дані з запиту
    requestData = request.json
    head_id = requestData.get('head_id')
    profile_id = requestData.get('profile_id')
    print(profile_id, head_id)
    user_head.query.filter_by(user_id=profile_id, head_id=head_id).delete()
    db.session.commit()

    # Повернути підтвердження успішного видалення
    return jsonify({'message': 'Запис успішно видалено'})


@app.route("/api/save_car_users", methods=["POST"])
def api_save_car_data():

    data = request.json  # Получаем JSON с фронтенда

    # Группируем данные по пользователям
    users_data = {}
    for key, value in data.items():
        user_id = key.split('[')[-1].split(']')[0]  # Извлекаем user_id из ключа
        if user_id not in users_data:
            users_data[user_id] = {}
        field_name = key.split('[')[0]  # Получаем имя поля (например, 'km')
        users_data[user_id][field_name] = value

    print("Grouped data:", users_data)

    # Теперь проходим по собранным данным
    for user_id, user_info in users_data.items():
        car_brand = user_info.get('car_brand', '')
        fuel_usage = user_info.get('fuel_usage', 0)
        monthly_norm = user_info.get('monthly_norm', 0)
        fuel_type = user_info.get('fuel_type', '')
        compensation_type = user_info.get('compensation_type', 'card')
        km = user_info.get('km', 0)
        transportation = user_info.get('transportation', 'false').lower() == 'on'

        # ИСПРАВЛЕНИЕ: правильная обработка массива карт
        user_cards = user_info.get('fuel_card', [])
        print("user_cards:", user_cards)
        if not isinstance(user_cards, list):
            user_cards = []

        print(f"User {user_id}: cards = {user_cards}")

        if str(car_brand) != '':
            user_car_cls = tm_users.get_users.UserAuto(user_id)
            check_in_db = user_car.query.filter_by(user_id=int(user_id)).first()
            print('in db', check_in_db)

            if check_in_db:
                # ИСПРАВЛЕНИЕ: передаем user_cards вместо user_card
                user_car_cls.update_user_avto(car_brand, fuel_usage, fuel_type, km, compensation_type, user_cards)
                user_car_cls.add_user_fuel_month_limit(monthly_norm)
            else:
                # ИСПРАВЛЕНИЕ: также для insert метода, если он принимает карты
                user_car_cls.insert_user_avto(car_brand, fuel_usage, fuel_type, km, compensation_type, user_cards)
                user_car_cls.add_user_fuel_month_limit(monthly_norm)

    return jsonify({"success": True})


@app.route('/api/save_car_okko_cards', methods=['POST'])
def save_car_okko_cards():
    try:
        data = request.get_json()
        car_id = data.get('car_id')
        car_cards = data.get('okko_cards', [])

        print("car_cards:", car_cards)
        if not isinstance(car_cards, list):
            car_cards = []

        print(f"Car {car_id}: cards = {car_cards}")

        if not car_id:
            return jsonify({'success': False, 'error': 'ID автомобіля не вказано'})

        # Спочатку відв'язуємо всі карти від цього автомобіля
        fuel_okko_cards.query.filter_by(car_id=car_id).update({'car_id': None})

        # Потім прив'язуємо обрані карти до автомобіля
        if isinstance(car_cards, list) and car_cards:
            for card_id in car_cards:
                if card_id:  # Перевіряємо що card_id не пустий
                    fuel_okko_cards.query.filter_by(id=int(card_id)).update({'car_id': car_id})

        db.session.commit()
        return jsonify({'success': True, 'message': 'Карти OKKO успішно збережені'})

    except Exception as e:
        db.session.rollback()
        print(f"Помилка при збереженні карт OKKO для автомобіля: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        db.session.close()

@app.route('/api/save-fuel-data', methods=['POST'])
def save_fuel_data():
    try:
        data = request.json
        print(data)
        refuel_data = data.get("fuelData", [])
        selected_month = data.get("month")
        selected_year = data.get("year")

        print(refuel_data)
        # Логіка збереження даних у базу
        for entry in refuel_data:
            driver_id = entry.get("driver_id")
            refueled = entry.get("refueled")
            print(driver_id, refueled)

            user_cls = tm_users.get_users.UserAuto(11).update_user_fuel_used_data(driver_id, refueled, selected_month, selected_year)
            # Тут можна оновити базу даних відповідно до driver_id і нового значення refueled

        return jsonify({"success": True, "message": "Дані збережено"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/remove_car/<int:user_id>", methods=["POST"])
def remove_car(user_id):
    # Тут має бути логіка обнулення даних у базі
    user_car.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/update_transportation/<int:user_id>', methods=['POST'])
@login_required
def update_transportation(user_id):
    try:
        data = request.json
        transportation = data.get('transportation', 'off').lower()
        print(data)
        if transportation == 'on':
            users.query.filter_by(id=user_id).update(dict(transportation=1))
            message = f"Розвозка для користувача {user_id} оновлено на включено"
        else:
            users.query.filter_by(id=user_id).update(dict(transportation=0))
            message = f"Розвозка для користувача {user_id} оновлено на вимкнено"

        db.session.commit()
        return jsonify({"success": True, "message": message})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/save-technoforum-data', methods=['POST'])
@login_required
def save_technoforum_data():
    data = request.get_json()
    technoforum_data = data.get('technoforumData')
    month = data.get('month')
    year = data.get('year')

    if not technoforum_data:
        return jsonify({"error": "No data provided"}), 400

    for record in technoforum_data:
        user_id = record['driver_id']
        refuel = float(record['refuel']) if record['refuel'] else 0.0
        total_fuel_usage = float(record['total_fuel_usage']) if record['total_fuel_usage'] else 0.0
        additional_fuel_usage = float(record['additional_fuel_usage']) if record['additional_fuel_usage'] else 0.0
        travel_days = int(record['travel_days']) if record['travel_days'] else 0
        created_at = datetime.strptime(f"{year}-{month}-01", "%Y-%m-%d").date()

        existing_record = fuel_technoforum.query.filter_by(
            user_id=user_id,
            created_at=created_at
        ).first()

        if existing_record:
            existing_record.refuel = refuel
            existing_record.total_fuel_usage = total_fuel_usage
            existing_record.additional_fuel_usage = additional_fuel_usage
            existing_record.travel_days = travel_days
        else:
            new_record = fuel_technoforum(
                user_id=user_id,
                created_at=created_at,
                refuel=refuel,
                cost=0.0,
                comment="",
                total_fuel_usage=total_fuel_usage,
                additional_fuel_usage=additional_fuel_usage,
                travel_days=travel_days
            )
            db.session.add(new_record)

    db.session.commit()
    return jsonify({"message": "Дані Технофоруму успішно збережено"}), 200


def get_avg_fuel_prices_string(selected_date=None):
    from datetime import date, timedelta

    if date.today().month == selected_date.month:
        selected_date = None

    # Якщо дату не передано, використовуємо поточну
    if selected_date is None:
        selected_date = date.today()

    # Визначаємо період: останні 5 днів від вибраної дати
    price_period_end = selected_date  # ВИПРАВЛЕНО: було date.today()
    price_period_start = selected_date - timedelta(days=4)  # 5 днів включно

    # Отримуємо ціни за період для дебагу
    prices_query = fuel_price.query.filter(
        fuel_price.created_at.between(price_period_start, price_period_end)
    ).all()

    # Друкуємо всі записи для перевірки
    print(f"Період (останні 5 днів): {price_period_start} - {price_period_end}")
    print(f"Знайдено записів: {len(prices_query)}")
    for price_record in prices_query:
        print(f"Тип: {price_record.fuel_type}, Ціна: {price_record.price}, Дата: {price_record.created_at}")

    # Отримуємо середні ціни за останні 5 днів
    # func.avg() автоматично рахує (сума цін / кількість записів)
    avg_price = db.session.query(
        fuel_price.fuel_type,
        func.avg(fuel_price.price).label("average_price")
    ).filter(
        fuel_price.created_at.between(price_period_start, price_period_end)
    ).group_by(fuel_price.fuel_type).all()

    # Друкуємо середні ціни для перевірки
    print("Середні ціни за типами палива (останні 5 днів):")
    for fuel, price in avg_price:
        print(f"Тип: {fuel}, Середня ціна: {round(price, 2)}")

    # Якщо немає даних, повертаємо повідомлення
    if not avg_price:
        return "<p>Немає даних про ціни палива</p>"

    # Формуємо HTML-таблицю
    table_rows = "".join(
        f"<tr><td>{fuel}</td><td>{round(price, 2)}</td></tr>"
        for fuel, price in avg_price
    )

    return f"""
    <p>Середня ціна топлива:</p>
    <table style="border-collapse: collapse; text-align: left;">
        <tr><th>Тип пального</th><th>Ціна</th></tr>
        {table_rows}
    </table>
    """



# Маршрут для відображення сторінки з посилками "Нової Пошти"
@app.route('/nova-poshta-parcels', methods=['GET'])
@login_required
def nova_poshta_parcels_page():
    import nova_api
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    # Ініціалізація та оновлення даних Нової Пошти
    api_key = 'f9221a240ee17368322adae7f5420503'  # Ваш API-ключ
    tracker = nova_api.NovaPoshtaTracker(api_key)
    tracker.update_parcels()  # Оновлюємо дані при кожному заході на сторінку
    tracker.close()  # Закриваємо клієнта після використання

    # Визначаємо порядок статусів як позиційні аргументи для case
    status_order = case(
        (nova_poshta_parcels.nova_poshta_status == "Прибув у відділення", 1),
        (nova_poshta_parcels.nova_poshta_status == "В дорозі", 2),
        (nova_poshta_parcels.nova_poshta_status == "Готується до відправлення", 3),
        else_=4
    ).label("status_order")

    # Отримуємо всі посилки, крім тих, що мають статус "Отримано"
    parcels = nova_poshta_parcels.query.filter(
        nova_poshta_parcels.nova_poshta_status != "Отримано"
    ).order_by(status_order, nova_poshta_parcels.created_at).all()

    # Перевіряємо права доступу
    user_departament_access = users_departament.query.filter_by(user_id=user_id, access_level=6).first()
    vacation_report_access = False
    if user_departament_access is not None or user_id == 11:
        vacation_report_access = True

    return render_template(
        'nova_poshta/parcels.html',
        user_info=user_info,
        parcels=parcels,
        vacation_report_access=vacation_report_access
    )

@app.route('/api/nova-poshta-parcels/copy-arrived', methods=['GET'])
@login_required
def copy_arrived_parcels():
    parcels = nova_poshta_parcels.query.filter(
        nova_poshta_parcels.nova_poshta_status == "Прибув у відділення",
        ~nova_poshta_parcels.recipient_address.ilike('%Поштомат%')  # Виключаємо адреси з "Поштомат"
    ).all()
    tracking_numbers = [parcel.tracking_number for parcel in parcels]
    return jsonify({'tracking_numbers': '\n'.join(tracking_numbers)})

# API для збереження коментарів
# API для збереження коментарів (оновлено для масиву)
@app.route('/api/nova-poshta-parcels/save-comment', methods=['POST'])
@login_required
def save_parcel_comment():
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Data must be a list of objects with tracking_number and comment'}), 400

    for item in data:
        if 'tracking_number' not in item or 'comment' not in item:
            return jsonify({'error': f'Missing tracking_number or comment in item: {item}'}), 400

        tracking_number = item['tracking_number']
        comment = item['comment']

        parcel = nova_poshta_parcels.query.filter_by(tracking_number=tracking_number).first()
        if not parcel:
            print(f"Parcel not found: {tracking_number}")
            continue  # Пропускаємо, якщо запис не знайдено

        parcel.comment = comment
        parcel.updated_at = datetime.now()
        db.session.commit()

    return jsonify({'message': 'Коментарі успішно збережено!'}), 200

import re
# Кастомний фільтр для regex_replace
@app.template_filter('regex_replace')
def regex_replace(s, find, replace):
    if s:
        return re.sub(find, replace, s)
    return s


@app.route('/bank-transactions', methods=['GET'])
@login_required
def transactions_list():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    no_limit_user = [72, 73, 78]

    page = request.args.get('page', 1, type=int)
    per_page = 20
    start_date = request.args.get('start_date', default=None, type=str)
    end_date = request.args.get('end_date', default=None, type=str)

    start_date = start_date.strip() if start_date and start_date.strip() else None
    end_date = end_date.strip() if end_date and end_date.strip() else None

    today = date.today()
    if not start_date:
        start_date = today.strftime('%Y-%m-%d')
    if not end_date:
        end_date = today.strftime('%Y-%m-%d')

    if user_id not in no_limit_user:
        base_query = transactions.query.filter(
            and_(
                transactions.credit != 0,
                not_(transactions.receiver_correspondent.in_(EXCLUDED_RECEIVER_CORRESPONDENTS))
            )
        )
    else:
        base_query = transactions.query.filter(transactions.credit != 0)

    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)
    except ValueError:
        start_date = today.strftime('%Y-%m-%d')
        start_date_obj = datetime.combine(today, datetime.min.time())
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)

    try:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)
    except ValueError:
        end_date = today.strftime('%Y-%m-%d')
        end_date_obj = datetime.combine(today, datetime.max.time())
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)

    transactions_query = base_query.order_by(desc(transactions.operation_date))

    # Якщо період задано, повертаємо всі транзакції без пагінації
    if start_date != today.strftime('%Y-%m-%d') or end_date != today.strftime('%Y-%m-%d'):
        transactions_list = [transaction.to_dict() for transaction in transactions_query.all()]
        return render_template(
            'bank/transactions_list.html',
            transactions=transactions_list,
            user_info=user_info,
            start_date=start_date,
            end_date=end_date,
            pagination=None
        )

    # За замовчуванням (сьогодні) застосовуємо пагінацію
    paginated_transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    transactions_list = [transaction.to_dict() for transaction in paginated_transactions.items]

    return render_template(
        'bank/transactions_list.html',
        transactions=transactions_list,
        pagination=paginated_transactions,
        user_info=user_info,
        start_date=start_date,
        end_date=end_date
    )


@app.route('/api/bank-transactions', methods=['GET'])
@login_required
def transactions_api():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)

    no_limit_user = [72, 73, 78]

    if current_user.id not in no_limit_user:
        base_query = transactions.query.filter(
            and_(
                transactions.credit != 0,
                not_(transactions.receiver_correspondent.in_(EXCLUDED_RECEIVER_CORRESPONDENTS))
            )
        )
    else:
        base_query = transactions.query.filter(transactions.credit != 0)

    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            base_query = base_query.filter(transactions.operation_date >= start_date_obj)
        except ValueError:
            pass
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
            base_query = base_query.filter(transactions.operation_date <= end_date_obj)
        except ValueError:
            pass

    transactions_query = base_query.order_by(desc(transactions.operation_date))

    # Для API повертаємо всі транзакції без пагінації, якщо задано період
    if start_date or end_date:
        transactions_list = [transaction.to_dict() for transaction in transactions_query.all()]
        return jsonify({
            'transactions': transactions_list,
            'pagination': None
        })

    # Без періоду повертаємо пагіновані дані
    paginated_transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    transactions_list = [transaction.to_dict() for transaction in paginated_transactions.items]

    pages = []
    for page_num in paginated_transactions.iter_pages():
        if page_num:
            pages.append(page_num)
        else:
            pages.append(None)

    return jsonify({
        'transactions': transactions_list,
        'pagination': {
            'page': paginated_transactions.page,
            'per_page': per_page,
            'has_prev': paginated_transactions.has_prev,
            'has_next': paginated_transactions.has_next,
            'prev_num': paginated_transactions.prev_num,
            'next_num': paginated_transactions.next_num,
            'pages': pages,
            'total': paginated_transactions.total
        }
    })


@app.route('/api/bank-transactions/search', methods=['GET'])
@login_required
def transactions_search():
    query = request.args.get('query', '').strip()
    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    no_limit_user = [72, 73, 78]

    if len(query) < 3 and not (start_date or end_date):
        return jsonify({'transactions': []})

    if current_user.id not in no_limit_user:
        base_query = transactions.query.filter(
            and_(
                transactions.credit != 0,
                not_(transactions.receiver_correspondent.in_(EXCLUDED_RECEIVER_CORRESPONDENTS))
            )
        )
    else:
        base_query = transactions.query.filter(transactions.credit != 0)

    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            base_query = base_query.filter(transactions.operation_date >= start_date_obj)
        except ValueError:
            pass
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
            base_query = base_query.filter(transactions.operation_date <= end_date_obj)
        except ValueError:
            pass

    if query:
        search_pattern = f'%{query}%'
        base_query = base_query.filter(
            or_(
                transactions.edrpou_sender.ilike(search_pattern),
                transactions.sender_nbu_code.ilike(search_pattern),
                transactions.sender_account.ilike(search_pattern),
                transactions.currency.ilike(search_pattern),
                func.date_format(transactions.operation_date, '%Y-%m-%d %H:%i:%s').ilike(search_pattern),
                transactions.operation_code.ilike(search_pattern),
                transactions.receiver_nbu_code.ilike(search_pattern),
                transactions.receiver_name.ilike(search_pattern),
                transactions.receiver_account.ilike(search_pattern),
                transactions.receiver_edrpou.ilike(search_pattern),
                transactions.receiver_correspondent.ilike(search_pattern),
                transactions.document_number.ilike(search_pattern),
                func.date_format(transactions.document_date, '%Y-%m-%d').ilike(search_pattern),
                transactions.payment_purpose.ilike(search_pattern),
                func.cast(transactions.debit, db.String).ilike(search_pattern),
                func.cast(transactions.credit, db.String).ilike(search_pattern),
                func.cast(transactions.uah_coverage, db.String).ilike(search_pattern)
            )
        )

    transactions_query = base_query.order_by(desc(transactions.operation_date))
    transactions_list = [transaction.to_dict() for transaction in transactions_query.all()]

    return jsonify({'transactions': transactions_list})


@app.route('/bank-expenses', methods=['GET'])
@login_required
def expenses_list():
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    page = request.args.get('page', 1, type=int)
    per_page = 20
    # Отримуємо параметри, обробляємо порожні рядки
    start_date = request.args.get('start_date', default=None, type=str)
    end_date = request.args.get('end_date', default=None, type=str)

    # Якщо параметри порожні або не передані, встановлюємо сьогоднішню дату
    today = date.today()  # 2025-05-20
    start_date = start_date.strip() if start_date and start_date.strip() else today.strftime('%Y-%m-%d')
    end_date = end_date.strip() if end_date and end_date.strip() else today.strftime('%Y-%m-%d')

    logger.debug(f"Raw input: start_date={request.args.get('start_date')}, end_date={request.args.get('end_date')}")
    logger.debug(f"Processed: start_date={start_date}, end_date={end_date}, page={page}")

    base_query = transactions.query.filter(
        and_(
            transactions.debit != 0
        )
    )

    # Застосовуємо фільтри дат
    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)
        logger.debug(f"Applied start_date filter: {start_date}")
    except ValueError as e:
        logger.error(f"Invalid start_date format: {start_date}, error: {e}")
        start_date = today.strftime('%Y-%m-%d')
        start_date_obj = datetime.combine(today, datetime.min.time())
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)

    try:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)
        logger.debug(f"Applied end_date filter: {end_date}")
    except ValueError as e:
        logger.error(f"Invalid end_date format: {end_date}, error: {e}")
        end_date = today.strftime('%Y-%m-%d')
        end_date_obj = datetime.combine(today, datetime.max.time())
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)

    transactions_query = base_query.order_by(desc(transactions.operation_date))

    # Логування для діагностики
    sample_transactions = transactions_query.limit(5).all()
    logger.debug(
        f"Sample transactions: {[{'id': t.id, 'debit': t.debit, 'operation_date': t.operation_date.isoformat()} for t in sample_transactions]}"
    )

    # Пагінація
    paginated_transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    transactions_list = [transaction.to_dict() for transaction in paginated_transactions.items]
    logger.debug(f"Returning {len(transactions_list)} transactions for page {page}")

    return render_template(
        'bank/expenses_list.html',
        transactions=transactions_list,
        pagination=paginated_transactions,
        user_info=user_info,
        start_date=start_date,
        end_date=end_date
    )


@app.route('/api/bank-expenses', methods=['GET'])
@login_required
def expenses_api():
    start_date = request.args.get('start_date', default=None, type=str)
    end_date = request.args.get('end_date', default=None, type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 2000000

    start_date = start_date.strip() if start_date and start_date.strip() else None
    end_date = end_date.strip() if end_date and end_date.strip() else None

    logger.debug(f"API expenses requested: start_date={start_date}, end_date={end_date}, page={page}")

    today = date.today()
    if not start_date:
        start_date = today.strftime('%Y-%m-%d')
    if not end_date:
        end_date = today.strftime('%Y-%m-%d')

    base_query = transactions.query.filter(
        and_(
            transactions.debit != 0
        )
    )

    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)
        logger.debug(f"Applied start_date filter: {start_date}")
    except ValueError as e:
        logger.error(f"Invalid start_date format: {start_date}, error: {e}")
        start_date = today.strftime('%Y-%m-%d')
        start_date_obj = datetime.combine(today, datetime.min.time())
        base_query = base_query.filter(transactions.operation_date >= start_date_obj)

    try:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)
        logger.debug(f"Applied end_date filter: {end_date}")
    except ValueError as e:
        logger.error(f"Invalid end_date format: {end_date}, error: {e}")
        end_date = today.strftime('%Y-%m-%d')
        end_date_obj = datetime.combine(today, datetime.max.time())
        base_query = base_query.filter(transactions.operation_date <= end_date_obj)

    transactions_query = base_query.order_by(desc(transactions.operation_date))

    # Логування зразка транзакцій
    sample_transactions = transactions_query.limit(5).all()
    logger.debug(
        f"Sample transactions: {[{'id': t.id, 'debit': t.debit, 'operation_date': t.operation_date.isoformat()} for t in sample_transactions]}"
    )

    paginated_transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    transactions_list = [transaction.to_dict() for transaction in paginated_transactions.items]
    logger.debug(f"Returning {len(transactions_list)} transactions for page {page}")

    return jsonify({
        'transactions': transactions_list,
        'pagination': {
            'page': paginated_transactions.page,
            'pages': paginated_transactions.pages,
            'total': paginated_transactions.total,
            'per_page': paginated_transactions.per_page
        },
        'start_date': start_date,
        'end_date': end_date
    })


@app.route('/api/bank-expenses/search', methods=['GET'])
@login_required
def expenses_search():
    query = request.args.get('query', '').strip()
    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)

    logger.debug(f"Search requested: query={query}, start_date={start_date}, end_date={end_date}")

    if len(query) < 3 and not (start_date or end_date):
        logger.debug("No valid search criteria provided")
        return jsonify({'transactions': []})

    base_query = transactions.query.filter(
        and_(
            transactions.debit != 0
        )
    )

    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            base_query = base_query.filter(transactions.operation_date >= start_date_obj)
            logger.debug(f"Applied start_date filter: {start_date}")
        except ValueError as e:
            logger.error(f"Invalid start_date format: {start_date}, error: {e}")
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
            base_query = base_query.filter(transactions.operation_date <= end_date_obj)
            logger.debug(f"Applied end_date filter: {end_date}")
        except ValueError as e:
            logger.error(f"Invalid end_date format: {end_date}, error: {e}")

    if query:
        search_pattern = f'%{query}%'
        base_query = base_query.filter(
            or_(
                transactions.edrpou_sender.ilike(search_pattern),
                transactions.sender_nbu_code.ilike(search_pattern),
                transactions.sender_account.ilike(search_pattern),
                transactions.currency.ilike(search_pattern),
                transactions.operation_date.ilike(search_pattern),
                transactions.operation_code.ilike(search_pattern),
                transactions.receiver_nbu_code.ilike(search_pattern),
                transactions.receiver_name.ilike(search_pattern),
                transactions.receiver_account.ilike(search_pattern),
                transactions.receiver_edrpou.ilike(search_pattern),
                transactions.receiver_correspondent.ilike(search_pattern),
                transactions.document_number.ilike(search_pattern),
                transactions.document_date.ilike(search_pattern),
                func.cast(transactions.debit, db.String).ilike(search_pattern),
                func.cast(transactions.credit, db.String).ilike(search_pattern),
                func.cast(transactions.uah_coverage, db.String).ilike(search_pattern)
            )
        )
        logger.debug(f"Applied search query: {query}")

    transactions_query = base_query.order_by(desc(transactions.operation_date))
    transactions_list = [transaction.to_dict() for transaction in transactions_query.all()]
    logger.debug(f"Search returned {len(transactions_list)} transactions: {transactions_list[:2]}")

    return jsonify({
        'transactions': transactions_list
    })


@app.route('/api/bank-expenses/<int:id>', methods=['GET'])
@app.route('/api/bank-transactions/<int:id>', methods=['GET'])
@login_required
def transaction_details(id):
    no_limit_user = [72, 73, 78]
    transaction = transactions.query.get_or_404(id)

    # Визначаємо, який маршрут викликано
    is_expense = request.path.startswith('/api/bank-expenses')

    # Умови для витрат (debit != 0) або надходжень (credit != 0)
    if is_expense:
        if transaction.debit == 0:
            logger.debug(f"Expense transaction {id} not found or invalid")
            return jsonify({'error': 'Transaction not found'}), 404
    else:  # /api/bank-transactions
        if current_user.id not in no_limit_user:
            if transaction.credit == 0 or transaction.receiver_correspondent in EXCLUDED_RECEIVER_CORRESPONDENTS:
                logger.debug(f"Transaction {id} not found or invalid")
                return jsonify({'error': 'Transaction not found'}), 404
        else:
            if transaction.credit == 0 or transaction.receiver_correspondent:
                logger.debug(f"Transaction {id} not found or invalid")
                return jsonify({'error': 'Transaction not found'}), 404

    logger.debug(f"Returning details for transaction {id}")
    return jsonify(transaction.to_dict())


@app.route('/add_exclusion', methods=['POST'])
@login_required
def add_exclusion():
    data = request.get_json()
    type = data.get('type')
    company_name = data.get('company_name')

    if type not in ['scania', 'tf'] or not company_name:
        return jsonify({'success': False, 'message': 'Невірні дані'}), 400

    exclusion = telegram_exclusions(type=type, company_name=company_name)
    db.session.add(exclusion)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/delete_exclusion', methods=['POST'])
@login_required
def delete_exclusion():
    data = request.get_json()
    type = data.get('type')
    id = data.get('id')

    if type not in ['scania', 'tf'] or not id:
        return jsonify({'success': False, 'message': 'Невірні дані'}), 400

    exclusion = telegram_exclusions.query.filter_by(id=id, type=type).first()
    if exclusion:
        db.session.delete(exclusion)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Виключення не знайдено'}), 404

@app.route('/get_exclusions', methods=['GET'])
def get_exclusions():
    type = request.args.get('type')
    if type not in ['scania', 'tf']:
        return jsonify({'success': False, 'message': 'Невірний тип'}), 400

    exclusions = telegram_exclusions.query.filter_by(type=type).all()
    return jsonify({
        'success': True,
        'exclusions': [{'id': e.id, 'company_name': e.company_name} for e in exclusions]
    })



@app.route('/api/get-transaction-details/<int:transaction_id>', methods=['GET'])
@login_required
def get_transaction_details(transaction_id):
    try:
        transaction = fuel_okko_transactions.query.get(transaction_id)

        if not transaction:
            return jsonify({'error': 'Транзакція не знайдена'}), 404

        # Формуємо детальну інформацію про транзакцію
        # Конвертуємо копійки в гривні (ділимо на 100) і мілілітри в літри (ділимо на 1000)
        transaction_details = {
            'id': transaction.id,
            'trans_id': transaction.trans_id,
            'card_num': transaction.card_num,
            'trans_date': transaction.trans_date.strftime('%d.%m.%Y %H:%M') if transaction.trans_date else '',
            'azs_name': transaction.azs_name or '',
            'addr_name': transaction.addr_name or '',
            'fuel_volume': round(transaction.fuel_volume / 1000, 1) if transaction.fuel_volume else 0,  # мілілітри -> літри
            'fuel_price': round(transaction.fuel_price / 100, 2) if transaction.fuel_price else 0,  # копійки -> гривні
            'amnt_trans': round(transaction.amnt_trans / 100, 2) - round(transaction.discount / 100, 2) if transaction.amnt_trans else 0,  # копійки -> гривні
            'product_desc': transaction.product_desc or '',
            'person_name': f"{transaction.person_first_name or ''} {transaction.person_last_name or ''}".strip()
        }

        return jsonify({'success': True, 'transaction': transaction_details})

    except Exception as e:
        print(f"Помилка при отриманні деталей транзакції: {e}")
        return jsonify({'error': 'Помилка сервера'}), 500


# API ендпоінт для отримання деталей транзакції
@app.route('/api/delete-transaction/<int:transaction_id>', methods=['DELETE'])
@login_required
def delete_transaction(transaction_id):
    """Видалення транзакції"""
    try:
        # Знаходимо транзакцію
        transaction = fuel_okko_transactions.query.filter_by(id=transaction_id).first()

        if not transaction:
            return jsonify({
                'success': False,
                'error': 'Транзакцію не знайдено'
            }), 404

        # Логуємо видалення для аудиту
        app.logger.info(
            f"Користувач {current_user.id} видаляє транзакцію {transaction_id}, картка: {transaction.card_num}, сума: {transaction.amnt_trans}")

        # Видаляємо транзакцію
        db.session.delete(transaction)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Транзакцію успішно видалено'
        })

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Помилка при видаленні транзакції {transaction_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка при видаленні транзакції: {str(e)}'
        }), 500


@app.route('/api/get-users-with-cards')
@login_required
def get_users_with_cards():
    """Отримання списку користувачів з паливними картками"""
    try:
        # Отримуємо користувачів, які мають паливні картки
        users_with_cards = db.session.query(users, fuel_okko_cards) \
            .join(fuel_okko_cards, users.id == fuel_okko_cards.user_id) \
            .filter(fuel_okko_cards.user_id.isnot(None)) \
            .order_by(users.user_fullname) \
            .all()

        # Групуємо картки по користувачах
        users_dict = {}
        for user, card in users_with_cards:
            if user.id not in users_dict:
                users_dict[user.id] = {
                    'id': user.id,
                    'name': user.user_fullname or f"Користувач {user.id}",
                    'email': user.user_email or '',
                    'cards': []
                }
            users_dict[user.id]['cards'].append(card.card_num)

        # Конвертуємо в список
        users_list = list(users_dict.values())

        return jsonify({
            'success': True,
            'users': users_list
        })

    except Exception as e:
        app.logger.error(f"Помилка при отриманні користувачів з картками: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500


@app.route('/api/reassign-transaction/<int:transaction_id>', methods=['PUT'])
@login_required
def reassign_transaction(transaction_id):
    print(transaction_id)
    """Переназначення транзакції новому користувачу"""
    try:
        data = request.get_json()
        new_user_id = data.get('new_user_id')
        print(new_user_id, data)

        if not new_user_id:
            return jsonify({
                'success': False,
                'error': 'Не вказано нового користувача'
            }), 400

        # Перевіряємо, чи існує користувач
        user = users.query.get(new_user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Користувача не знайдено'
            }), 404

        # Отримуємо першу активну картку користувача
        user_card = fuel_okko_cards.query.filter_by(user_id=new_user_id).first()
        if not user_card:
            return jsonify({
                'success': False,
                'error': 'У користувача немає паливних карток'
            }), 400

        # Знаходимо транзакцію
        transaction = fuel_okko_transactions.query.filter_by(id=transaction_id).first()
        print(transaction)
        if not transaction:
            return jsonify({
                'success': False,
                'error': 'Транзакцію не знайдено'
            }), 404

        # Зберігаємо старі дані для логування
        old_card_num = transaction.card_num
        old_person_name = f"{transaction.person_first_name or ''} {transaction.person_last_name or ''}".strip()

        # Оновлюємо номер картки в транзакції
        transaction.card_num = user_card.card_num

        # Оновлюємо ім'я водія з даних користувача
        if user.user_fullname:
            name_parts = user.user_fullname.split()
            transaction.person_first_name = name_parts[0] if len(name_parts) > 0 else None
            transaction.person_last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else None
        else:
            transaction.person_first_name = None
            transaction.person_last_name = None

        db.session.commit()

        # Логуємо переназначення для аудиту
        app.logger.info(f"Користувач {current_user.id} переназначив транзакцію {transaction_id}: "
                        f"з картки {old_card_num} ({old_person_name}) "
                        f"на картку {user_card.card_num} ({user.user_fullname})")

        return jsonify({
            'success': True,
            'message': f'Транзакцію успішно переназначено користувачу {user.user_fullname}',
            'details': {
                'old_card': old_card_num,
                'new_card': user_card.card_num,
                'new_user': user.user_fullname
            }
        })

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Помилка при переназначенні транзакції {transaction_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Помилка при переназначенні транзакції: {str(e)}'
        }), 500



# Допоміжна функція для отримання транзакцій користувача за період
def get_user_transactions(user_id, start_date, end_date):
    """Отримує транзакції користувача за вказаний період"""
    try:
        # Отримуємо картки користувача
        user_cards = fuel_okko_cards.query.filter_by(user_id=user_id).all()
        card_numbers = [card.card_num for card in user_cards]

        if not card_numbers:
            return [], 0, 0

        # Отримуємо транзакції
        transactions = fuel_okko_transactions.query.filter(
            fuel_okko_transactions.card_num.in_(card_numbers),
            fuel_okko_transactions.trans_date >= start_date,
            fuel_okko_transactions.trans_date < end_date
        ).order_by(fuel_okko_transactions.trans_date.desc()).all()

        transactions_list = []
        total_fuel = 0
        total_cost = 0

        for t in transactions:
            fuel_volume = float(t.fuel_volume / 1000) if t.fuel_volume else 0
            amount = float(t.amnt_trans / 100) if t.amnt_trans else 0

            transactions_list.append({
                'id': t.trans_id,
                'date': t.trans_date.strftime('%d.%m') if t.trans_date else '',
                'datetime': t.trans_date,
                'amount': fuel_volume,
                'price': round(amount * fuel_volume, 2),
                'azs_name': t.azs_name,
                'product_desc': t.product_desc
            })

            total_fuel += fuel_volume
            total_cost += amount

        return transactions_list, total_fuel, total_cost

    except Exception as e:
        app.logger.error(f"Помилка при отриманні транзакцій користувача {user_id}: {e}")
        return [], 0, 0


# API для отримання статистики транзакцій
@app.route('/api/transaction-stats/<int:user_id>')
@login_required
def get_transaction_stats(user_id):
    """Отримання статистики транзакцій користувача"""
    try:
        # Поточний місяць
        now = datetime.now()
        start_current = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_current = datetime(now.year + 1, 1, 1)
        else:
            end_current = datetime(now.year, now.month + 1, 1)

        current_transactions, current_fuel, current_cost = get_user_transactions(
            user_id, start_current, end_current
        )

        # Попередній місяць
        if now.month == 1:
            start_prev = datetime(now.year - 1, 12, 1)
            end_prev = datetime(now.year, 1, 1)
        else:
            start_prev = datetime(now.year, now.month - 1, 1)
            end_prev = datetime(now.year, now.month, 1)

        prev_transactions, prev_fuel, prev_cost = get_user_transactions(
            user_id, start_prev, end_prev
        )

        return jsonify({
            'success': True,
            'current_month': {
                'fuel': current_fuel,
                'cost': current_cost,
                'transactions_count': len(current_transactions)
            },
            'previous_month': {
                'fuel': prev_fuel,
                'cost': prev_cost,
                'transactions_count': len(prev_transactions)
            }
        })

    except Exception as e:
        app.logger.error(f"Помилка при отриманні статистики для користувача {user_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/save-tf-travel-days', methods=['POST'])
def save_tf_travel_days():
    """
    Збереження кількості днів поїздки для користувачів Технофоруму
    """
    try:
        data = request.json.get('data', [])

        if not data:
            return jsonify({'success': False, 'error': 'Немає даних для збереження'}), 400

        for item in data:
            user_id = item.get('user_id')
            travel_days = item.get('travel_days', 0)
            month = item.get('month')
            year = item.get('year')

            if not user_id or month is None or year is None:
                continue

            # Створюємо дату для пошуку/створення запису
            record_date = datetime(year, month, 1).date()

            # Шукаємо існуючий запис
            existing_record = fuel_technoforum.query.filter_by(
                user_id=user_id,
                created_at=record_date
            ).first()

            if existing_record:
                # Оновлюємо існуючий запис
                existing_record.travel_days = travel_days

                # Перераховуємо total_fuel_usage на основі day_norm * travel_days
                # Отримуємо day_norm для користувача
                day_norm = get_refuel_num_in_month(month, user_id)  # Викликаємо метод з класу
                if day_norm is None:
                    day_norm = 0

                existing_record.total_fuel_usage = day_norm * travel_days

                print(
                    f"Оновлено запис для користувача {user_id}: {travel_days} днів, витрати: {existing_record.total_fuel_usage}")

            else:
                # Створюємо новий запис
                day_norm = get_refuel_num_in_month(month, user_id)
                if day_norm is None:
                    day_norm = 0

                new_record = fuel_technoforum(
                    user_id=user_id,
                    created_at=record_date,
                    travel_days=travel_days,
                    total_fuel_usage=day_norm * travel_days,
                    refuel=0.0,  # Початкове значення, буде перераховано
                    cost=0.0,
                    additional_fuel_usage=0.0,
                    comment=""
                )

                db.session.add(new_record)
                print(f"Створено новий запис для користувача {user_id}: {travel_days} днів")

        # Зберігаємо всі зміни
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Успішно збережено дані для {len(data)} користувачів'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Помилка при збереженні даних ТФ: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500


@app.route('/api/manual-okko-sync', methods=['POST'])
@login_required
def manual_okko_sync():
    """
    Ручний запуск синхронізації OKKO чеків за вибраний місяць і рік
    """
    try:
        data = request.get_json() or {}
        month = int(data.get('month'))
        year = int(data.get('year'))

        if not (1 <= month <= 12):
            return jsonify({'success': False, 'error': 'Невірний місяць'}), 400
        if not (2020 <= year <= 2100):
            return jsonify({'success': False, 'error': 'Невірний рік'}), 400

        from auto import run_okko_sync
        import threading

        # Запускаємо в окремому потоці з параметрами
        def run_sync_with_params():
            try:
                run_okko_sync(month=month, year=year)  # Переконайся, що функція приймає ці параметри!
            except Exception as e:
                print(f"Помилка в потоці синхронізації: {e}")

        sync_thread = threading.Thread(target=run_sync_with_params)
        sync_thread.daemon = True
        sync_thread.start()

        month_name = [
            "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
            "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"
        ][month - 1]

        return jsonify({
            'success': True,
            'message': f'Вигрузка чеків за <strong>{month_name} {year}</strong> запущена у фоновому режимі!'
        })

    except Exception as e:
        print(f"Помилка при запуску синхронізації: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Помилка сервера: {str(e)}'
        }), 500


# Допоміжна функція для отримання норми палива
def get_refuel_num_in_month(month, user_id):
    """
    Отримує денну норму палива для користувача
    Цю функцію потрібно адаптувати під вашу логіку
    """
    try:
        # Припустимо, що у вас є метод в класі або функція
        # Замініть це на ваш реальний код отримання норми

        # Варіант 1: Якщо це метод класу
        # return YourReportClass().get_refuel_num_in_month(month, user_id)

        # Варіант 2: Якщо норма зберігається в user_car
        user_car_record = user_car.query.filter_by(user_id=user_id).first()
        if user_car_record and user_car_record.fuel_limit and user_car_record.distance:
            return user_car_record.distance * (user_car_record.fuel_limit / 100)

        return 0

    except Exception as e:
        print(f"Помилка при отриманні норми палива: {e}")
        return 0


# Повна версія Flask бекенду для автомобілів та карток OKKO

@app.route('/company-car-<int:car_id>')
@login_required
def company_car_profile(car_id):
    user = current_user
    user_id = user.id
    user_class = tm_users.get_users.Users(user_id)
    user_info = user_class.get_user_info()

    # Отримуємо автомобіль або повертаємо 404
    car = company_car.query.get_or_404(car_id)
    today = date.today()

    # Визначаємо поточний рік
    current_year = datetime.now().year

    # Отримуємо історію пробігу та заправок за поточний рік
    mileage_history = car_mileage.query.filter(
        car_mileage.car_id == car_id,
        car_mileage.date.between(f'{current_year}-01-01', f'{current_year}-12-31')
    ).order_by(car_mileage.date).all()

    # Підрахунок загального пробігу та заправленого палива за рік
    total_fuel_added = sum(record.fuel_added or 0 for record in mileage_history) if mileage_history else 0

    # Отримуємо карти OKKO з інформацією про прив'язку
    okko_card_catalog = fuel_okko_cards.query.all()
    okko_cards = []
    for card in okko_card_catalog:
        card_data = {
            'id': card.id,
            'card_num': card.card_num,
            'user_id': card.user_id,
        }
        # Додаємо car_id якщо поле існує
        if hasattr(card, 'car_id'):
            card_data['car_id'] = card.car_id
        okko_cards.append(card_data)

    # ДОДАНО: Отримуємо список користувачів для випадаючого списку
    all_users = users.query.all()
    users_list = []
    for user_item in all_users:
        users_list.append({
            'id': user_item.id,
            'name': user_item.user_fullname
        })

    # Обчислення загального пробігу за рік
    if mileage_history:
        start_mileage = mileage_history[0].mileage
        end_mileage = mileage_history[-1].mileage
        total_mileage = end_mileage - start_mileage if end_mileage >= start_mileage else 0
    else:
        total_mileage = 0

    # Якщо є записи до початку року, враховуємо їх як базовий пробіг
    prev_year_record = car_mileage.query.filter(
        car_mileage.car_id == car_id,
        car_mileage.date < f'{current_year}-01-01'
    ).order_by(desc(car_mileage.date)).first()

    if prev_year_record and mileage_history:
        start_mileage = prev_year_record.mileage
        end_mileage = mileage_history[-1].mileage
        total_mileage = end_mileage - start_mileage if end_mileage >= start_mileage else 0
    elif not mileage_history and prev_year_record:
        total_mileage = 0
    elif mileage_history and not prev_year_record and car.initial_mileage is not None:
        end_mileage = mileage_history[-1].mileage
        total_mileage = end_mileage - car.initial_mileage if end_mileage >= car.initial_mileage else 0
    elif not mileage_history and not prev_year_record and car.initial_mileage is not None:
        total_mileage = 0

    # Діагностичний вивід
    print(f"Users list: {len(users_list)} users")
    print(f"OKKO cards: {len(okko_cards)} cards")
    print(f"Car assigned_user_id: {getattr(car, 'assigned_user_id', 'N/A')}")

    return render_template('company/company_car_profile.html',
                           car=car,
                           today=today,
                           user_info=user_info,
                           mileage_history=mileage_history,
                           total_mileage=total_mileage,
                           total_fuel_added=total_fuel_added,
                           user_id=user_id,
                           okko_cards=okko_cards,
                           users_list=users_list)  # ВАЖЛИВО: додано users_list


@app.route('/company-cars/edit', methods=['POST'])
@login_required
def edit_company_car():
    try:
        data = request.get_json()
        if not data or 'car_id' not in data:
            return jsonify({'error': 'Відсутній ідентифікатор автомобіля'}), 400

        car = company_car.query.get_or_404(int(data['car_id']))
        user = current_user

        print(f"Editing car {car.id}, user: {user.id}")
        print(f"Data received: {data}")

        # Оновлення основних полів (тільки для адміна)
        if user.id == 11:  # Якщо це адмін
            car.car_number = data.get('car_number', car.car_number)
            car.car_name = data.get('car_name', car.car_name)
            car.company_name = data.get('company_name', car.company_name)
            car.fuel_type = data.get('fuel_type', car.fuel_type)
            car.fuel_norm = float(data.get('fuel_norm', car.fuel_norm)) if data.get('fuel_norm') else car.fuel_norm
            car.tank_volume = int(data['tank_volume']) if data.get('tank_volume') else car.tank_volume
            car.initial_mileage = int(data['initial_mileage']) if data.get('initial_mileage') else car.initial_mileage
            car.initial_fuel_balance = float(data['initial_fuel_balance']) if data.get(
                'initial_fuel_balance') else car.initial_fuel_balance
            car.created_at = datetime.strptime(data['created_at'], '%Y-%m-%d').date() if data.get(
                'created_at') else car.created_at

            # Обробка призначеного користувача
            assigned_user_id = data.get('assigned_user_id')
            print(f"Processing assigned_user_id: {assigned_user_id}")

            # Оновлюємо assigned_user_id якщо поле існує
            if hasattr(car, 'assigned_user_id'):
                car.assigned_user_id = int(assigned_user_id) if assigned_user_id else None
                print(f"Set car.assigned_user_id to: {car.assigned_user_id}")

            # Оновлюємо текстове поле location для сумісності
            if assigned_user_id:
                try:
                    assigned_user = users.query.get(int(assigned_user_id))
                    if assigned_user:
                        car.location = assigned_user.user_fullname
                        print(f"Set car.location to: {car.location}")
                except Exception as e:
                    print(f"Error updating location: {e}")
            else:
                car.location = "Не призначено"

            # НОВЕ: Обчислення заправок з транзакцій OKKO
            # Знаходимо користувача по location
            assigned_user = db.session.query(users.id).filter(users.user_fullname == car.location).first()
            user_ids = [assigned_user.id] if assigned_user else []

            # Отримуємо карти OKKO для користувача
            card_nums = db.session.query(fuel_okko_cards.card_num).filter(
                fuel_okko_cards.user_id.in_(user_ids)
            ).all()
            card_nums = [cnum[0] for cnum in card_nums]

            # Визначаємо період: від created_at до поточної дати (або за month/year з data)
            period_start = car.created_at
            period_end = datetime.now().date()
            if data.get('month') and data.get('year'):
                month = int(data['month'])
                year = int(data['year'])
                from calendar import monthrange
                period_start = date(year, month, 1)
                period_end = date(year, month, monthrange(year, month)[1])
                print(f"Using period from data: {period_start} to {period_end}")
            else:
                print(f"Using default period: {period_start} to {period_end}")

            period_start_str = period_start.strftime('%Y-%m-%d')
            period_end_str = period_end.strftime('%Y-%m-%d')

            # Отримуємо транзакції за період
            transactions = db.session.query(fuel_okko_transactions).filter(
                fuel_okko_transactions.card_num.in_(card_nums),
                fuel_okko_transactions.trans_date.between(period_start_str, period_end_str)
            ).all()

            total_okko_fuel = 0
            for t in transactions:
                # Розраховуємо кількість палива (аналогічно до company_fuel)
                fuel_amount = (
                    round(t.fuel_volume / 1000, 2) if t.trans_type == 774
                    else -round(t.fuel_volume / 1000, 2) if t.trans_type == 775  # повернення
                    else round(t.fuel_volume / 1000, 2)
                ) if t.fuel_volume else 0
                total_okko_fuel += fuel_amount

            # Оновлюємо поле okko_refueled (додай колонку в модель, якщо немає: db.Column(db.Float, default=0))
            if hasattr(car, 'okko_refueled'):
                car.okko_refueled = round(total_okko_fuel, 2)
                print(f"Updated okko_refueled to: {car.okko_refueled} л (from {len(transactions)} transactions)")
            else:
                print("Warning: No 'okko_refueled' field in model. Add it to company_car.")

            # Оновлюємо end_mileage, якщо передано
            if data.get('end_mileage'):
                car.end_mileage = int(data['end_mileage'])
                print(f"Updated end_mileage to: {car.end_mileage}")

            # Якщо є модель car_mileage, додаємо/оновлюємо запис
            if 'end_mileage' in locals():  # Якщо оновили пробіг
                existing_record = car_mileage.query.filter_by(car_id=car.id, date=period_end).first()
                if existing_record:
                    existing_record.mileage = car.end_mileage
                    existing_record.fuel_added = car.okko_refueled
                else:
                    new_record = car_mileage(
                        car_id=car.id,
                        date=period_end,
                        mileage=car.end_mileage,
                        fuel_added=car.okko_refueled
                    )
                    db.session.add(new_record)
                print(f"Updated/added car_mileage record for {period_end}")

        # Страховки можуть редагувати всі
        if data.get('public_insurance'):
            car.public_insurance = datetime.strptime(data['public_insurance'], '%Y-%m-%d').date()
        else:
            car.public_insurance = None

        if data.get('kasko_insurance'):
            car.kasko_insurance = datetime.strptime(data['kasko_insurance'], '%Y-%m-%d').date()
        else:
            car.kasko_insurance = None

        # Існуючі поля (якщо вони є в моделі)
        if hasattr(car, 'public_company'):
            car.public_company = data.get('public_company', car.public_company)
        if hasattr(car, 'kasko_company'):
            car.kasko_company = data.get('kasko_company', car.kasko_company)
        if hasattr(car, 'plan_to'):
            car.plan_to = datetime.strptime(data['plan_to'], '%Y-%m-%d').date() if data.get('plan_to') else car.plan_to
        if hasattr(car, 'pay_date'):
            car.pay_date = data.get('payment_date', car.pay_date)

        db.session.commit()

        print(f"Car {car.id} updated successfully, okko_refueled: {getattr(car, 'okko_refueled', 'N/A')}")

        return jsonify({'success': True})

    except ValueError as ve:
        print(f"ValueError in edit_company_car: {str(ve)}")
        return jsonify({'error': 'Невірний формат даних'}), 400
    except Exception as e:
        db.session.rollback()
        print(f"Error in edit_company_car: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Помилка при редагуванні автомобіля'}), 500



@app.route('/api/get-users', methods=['GET'])
@login_required
def get_users():
    """
    Повертає список всіх користувачів
    """
    try:
        print("Запит списку користувачів")

        users_query = users.query.all()

        users_list = []
        for user in users_query:
            users_list.append({
                'id': user.id,
                'name': user.user_fullname
            })

        print(f"Знайдено користувачів: {len(users_list)}")

        return jsonify({
            'success': True,
            'users': users_list
        })

    except Exception as e:
        print(f"Помилка отримання користувачів: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/company-car/<int:car_id>', methods=['GET'])
@login_required
def get_company_car_data(car_id):
    """
    Повертає дані автомобіля для форми редагування
    """
    try:
        print(f"Запит даних для автомобіля ID: {car_id}")

        car = company_car.query.get_or_404(car_id)
        print(f"Автомобіль знайдено: {car.car_name}")

        car_data = {
            'car_number': car.car_number,
            'car_name': car.car_name,
            'company_name': car.company_name,
            'location': car.location,
            'fuel_type': car.fuel_type,
            'fuel_norm': float(car.fuel_norm) if car.fuel_norm else 0,
            'tank_volume': car.tank_volume,
            'initial_mileage': car.initial_mileage,
            'initial_fuel_balance': float(car.initial_fuel_balance) if car.initial_fuel_balance else None,
            'created_at': car.created_at.strftime('%Y-%m-%d') if car.created_at else None,
            'public_insurance': car.public_insurance.strftime('%Y-%m-%d') if car.public_insurance else None,
            'kasko_insurance': car.kasko_insurance.strftime('%Y-%m-%d') if car.kasko_insurance else None,
        }

        # Додаємо нові поля якщо вони існують
        if hasattr(car, 'assigned_user_id'):
            car_data['assigned_user_id'] = car.assigned_user_id

        if hasattr(car, 'public_company'):
            car_data['public_company'] = car.public_company

        if hasattr(car, 'kasko_company'):
            car_data['kasko_company'] = car.kasko_company

        if hasattr(car, 'plan_to'):
            car_data['plan_to'] = car.plan_to.strftime('%Y-%m-%d') if car.plan_to else None

        if hasattr(car, 'pay_date'):
            car_data['pay_date'] = car.pay_date

        print(f"Дані підготовлено: {car_data}")

        return jsonify(car_data)

    except Exception as e:
        print(f"Помилка отримання даних автомобіля: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/save_car_okko_cards_company', methods=['POST'])
@login_required
def save_car_okko_cards_company():
    """
    Зберігає карти OKKO для автомобіля та користувача
    """
    try:
        data = request.get_json()
        car_id = data.get('car_id')
        okko_cards = data.get('okko_cards', [])
        assigned_user_id = data.get('assigned_user_id')

        print(f"Saving OKKO cards for car {car_id}: {okko_cards}, user: {assigned_user_id}")

        if not car_id:
            return jsonify({
                'success': False,
                'error': 'Не вказано ID автомобіля'
            }), 400

        # Перевіряємо, чи існує автомобіль
        car = company_car.query.get(car_id)
        if not car:
            return jsonify({
                'success': False,
                'error': 'Автомобіль не знайдено'
            }), 404

        # Визначаємо користувача для прив'язки карток
        user_to_assign = assigned_user_id

        # Якщо assigned_user_id не передано, беремо з поля location автомобіля
        if not user_to_assign and car.location:
            # Шукаємо користувача за іменем в полі location
            user_by_name = users.query.filter_by(user_fullname=car.location).first()
            if user_by_name:
                user_to_assign = user_by_name.id
                print(f"Found user by name: {user_by_name.user_fullname} (ID: {user_by_name.id})")

        # Спочатку очищаємо всі картки, що були прив'язані до цього автомобіля/користувача
        if hasattr(fuel_okko_cards, 'car_id'):
            # Якщо є поле car_id
            fuel_okko_cards.query.filter_by(car_id=car_id).update({'car_id': None, 'user_id': None})
        elif user_to_assign:
            # Якщо поля car_id немає, очищаємо по user_id
            fuel_okko_cards.query.filter_by(user_id=user_to_assign).update({'user_id': None})

        # Встановлюємо нові зв'язки
        updated_cards = 0
        for card_id in okko_cards:
            card = fuel_okko_cards.query.get(card_id)
            if card:
                if hasattr(card, 'car_id'):
                    card.car_id = car_id
                card.user_id = user_to_assign
                updated_cards += 1
                print(f"Updated card {card.card_num}: car_id={car_id}, user_id={user_to_assign}")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Успішно збережено {updated_cards} карт OKKO для автомобіля'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error saving OKKO cards: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Помилка при збереженні карт OKKO: {str(e)}'
        }), 500


@app.route('/vacation-conflicts/<int:year>', methods=['GET'])
@login_required
def vacation_conflicts(year):
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from io import BytesIO
    from datetime import datetime, timedelta
    from flask import make_response, abort
    from sqlalchemy import func

    user = current_user

    # ===================================================================
    # ПЕРЕВІРКА ПРАВ ДОСТУПУ
    # ===================================================================
    # Адмін (ID 11) - бачить все
    is_admin = user.id in [11, 78, 79, 73, 72]

    if is_admin:
        allowed_departments = [dep.id for dep in departaments.query.with_entities(departaments.id).all()]
    else:
        allowed_departments = [
            ud.dep_id for ud in users_departament.query.with_entities(users_departament.dep_id)
            .filter_by(access_level=6, user_id=user.id).all()
        ]

    # Перевіряємо, чи є користувач керівником відділу
    user_department = user.user_departament

    # Якщо не адмін і не керівник одного з відділів 29, 40, 36 - забороняємо доступ
    if not is_admin:
        # Перевіряємо чи є користувач керівником (чи має колір у get_employees_data)
        employees = tm_users.get_users.get_employees_data(year, user.id)
        is_department_head = False

        for emp in employees:
            if emp['name'] == user.user_fullname and emp.get('color'):
                is_department_head = True
                break

        """if not is_department_head or user_department not in [29, 40, 36]:
            abort(403)  # Доступ заборонено"""

    # Визначаємо які відділи перевіряти
    departments_to_check = [29, 40, 36] if is_admin else [user_department]

    # ===================================================================
    # ФУНКЦІЯ ДЛЯ ПЕРЕВІРКИ КОНФЛІКТІВ В МЕЖАХ ОДНОГО ВІДДІЛУ
    # ===================================================================
    def check_department_conflicts(dept_id):
        """Перевіряє конфлікти відпусток в межах одного відділу"""
        service_users = users.query.filter(
            users.user_departament == dept_id
        ).order_by(users.user_fullname).all()

        print("\n" + "═" * 100)
        print(f"ВІДДІЛ {dept_id}: ВСІ ПРАЦІВНИКИ")
        print("═" * 100)
        if not service_users:
            print("   Працівників не знайдено!")
        else:
            for i, u in enumerate(service_users, 1):
                print(f"   {i:2d}. {u.user_fullname} (ID: {u.id})")
            print(f"\n   ВСЬОГО у відділі: {len(service_users)} працівників")
        print("═" * 100 + "\n")

        # Перевіряємо відпустки та конфлікти
        for user_obj in service_users:
            profile_id = user_obj.id
            name = user_obj.user_fullname

            vacations = calendar_work.query.filter(
                calendar_work.user_id == profile_id,
                calendar_work.reason == 'vacation',
                calendar_work.today_date >= datetime(year, 1, 1),
                calendar_work.today_date <= datetime(year, 12, 31)
            ).order_by(calendar_work.today_date).all()

            if not vacations:
                continue

            sequences = find_sequences(vacations)

            print("\n" + "█" * 96)
            print(f"ВІДДІЛ {dept_id} → {name} (ID: {profile_id})")
            print("█" * 96)

            conflicts = 0
            for seq in sequences:
                start = seq['start_date']
                end = seq['end_date']
                print(f"\n   {start.strftime('%d.%m.%Y')} → {end.strftime('%d.%m.%Y')}")

                current = start
                while current <= end:
                    cdate = current

                    # Шукаємо інших працівників того ж відділу у відпустці
                    others = db.session.query(users).join(
                        calendar_work, users.id == calendar_work.user_id
                    ).filter(
                        users.user_departament == dept_id,
                        users.id != profile_id,
                        calendar_work.reason == 'vacation',
                        calendar_work.today_date == cdate
                    ).all()

                    if others:
                        conflicts += 1
                        names = [o.user_fullname for o in others]
                        print(f"     {cdate.strftime('%d.%m.%Y')}  КОНФЛІКТ! → {', '.join(names)}")
                    else:
                        print(f"     {cdate.strftime('%d.%m.%Y')}")

                    current += timedelta(days=1)

            print(f"\n   Днів з конфліктом: {conflicts}")
            print("█" * 96 + "\n")

    # Викликаємо перевірку для кожного відділу
    for dept_id in departments_to_check:
        check_department_conflicts(dept_id)

    # ===================================================================
    # 3. Генерація PDF з підсвіткою конфліктів та керівників
    # ===================================================================
    pdfmetrics.registerFont(TTFont("DejaVuSerif", "static/fonts/DejaVuSerif.ttf"))

    base_style = ParagraphStyle(
        name='VacationBase', fontName='DejaVuSerif', fontSize=8, leading=9.5,
        leftIndent=2, rightIndent=2, spaceBefore=0.5, spaceAfter=0.5, alignment=0
    )

    # Отримуємо співробітників (вже з врахуванням прав доступу)
    employees = tm_users.get_users.get_employees_data(year, user.id)

    # Створюємо список для формування PDF
    employees_vacation_data = []

    # Словник для відстеження першого працівника кожного відділу
    department_first_user = {}

    for employee in employees:
        user_obj = users.query.filter_by(user_fullname=employee['name']).first()
        if not user_obj:
            continue

        profile_id = user_obj.id
        dept_id = user_obj.user_departament

        vacations = calendar_work.query.filter(
            calendar_work.reason == 'vacation',
            calendar_work.user_id == profile_id,
            calendar_work.today_date >= datetime(year, 1, 1),
            calendar_work.today_date <= datetime(year, 12, 31)
        ).order_by(calendar_work.today_date).all()

        sequences = find_sequences(vacations) if vacations else []

        # Визначаємо колір: або з employee (якщо є), або для першого користувача відділу
        color = employee.get('color', None)

        if dept_id not in department_first_user:
            department_first_user[dept_id] = True
            if not color:
                color = ''  # колір для керівника можна поставити фіксований

        emp_data = {
            'employee': employee,
            'profile_id': profile_id,
            'sequences': sequences,
            'department': dept_id,
            'color': color
        }
        employees_vacation_data.append(emp_data)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    elements = []

    # Заголовок з інформацією про відділи
    if is_admin:
        title_text = f"Звіт по перетину відпусток на {year} рік<br/>(Відділи: 29, 40, 36)<br/><br/>Створено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    else:
        title_text = f"Звіт по перетину відпусток на {year} рік<br/>(Відділ: {user_department})<br/><br/>Створено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    title = Paragraph(
        title_text,
        ParagraphStyle('Title', fontName='DejaVuSerif', fontSize=14, alignment=1, spaceAfter=30, leading=20)
    )
    elements.append(title)

    data = [["№", "Відділ", "ПІБ", "Майбутні відпустки", "Викор.\nднів", "Залишок\n(попер. | поточ. | всього)"]]
    row_colors = []

    for idx, emp_data in enumerate(employees_vacation_data, 1):
        employee = emp_data['employee']
        sequences = emp_data['sequences']
        dept_id = emp_data['department']

        inner_rows = []
        inner_style = TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('LEADING', (0, 0), (-1, -1), 9.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ])

        if not sequences:
            inner_rows.append([Paragraph("—", base_style)])
        else:
            # Поточна дата для фільтрації минулих відпусток
            today = date.today()

            for seq in sequences:
                start = seq['start_date']
                end = seq['end_date']

                # Пропускаємо відпустки, які вже закінчилися
                if end < today:
                    continue

                days = (end - start).days + 1

                # Перевіряємо конфлікти ТІЛЬКИ для відділів 29, 40, 36
                overlap_names = []
                overlap_names_set = set()

                print(f"\nПеревірка для {emp_data['employee']['name']}, dept={dept_id}, відпустка {start} - {end}")

                if dept_id in [29, 40, 36]:
                    # Перевіряємо кожен день поточної відпустки
                    current_day = start
                    while current_day <= end:
                        # Шукаємо інших працівників ТОГО Ж відділу у цей день
                        others = db.session.query(users).join(
                            calendar_work, users.id == calendar_work.user_id
                        ).filter(
                            users.user_departament == dept_id,
                            users.id != emp_data['profile_id'],
                            calendar_work.reason == 'vacation',
                            calendar_work.today_date == current_day
                        ).all()

                        if others:
                            print(f"  День {current_day}: знайдено {len(others)} конфліктів")

                        for other_user in others:
                            overlap_names_set.add(other_user.user_fullname)

                        current_day += timedelta(days=1)

                    overlap_names = sorted(list(overlap_names_set))
                    if overlap_names:
                        print(f"  ВСЬОГО конфліктів: {overlap_names}")

                # Формуємо текст з інформацією про перетин
                text = f"{start.strftime('%d.%m')} – {end.strftime('%d.%m.%Y')} ({days} дн.)"
                if overlap_names:
                    text += f"<br/><font color='red'><b>Перетин:</b> {', '.join(overlap_names)}</font>"

                para = Paragraph(text, base_style)
                inner_rows.append([para])

                # Додаємо червону заливку якщо є конфлікт
                row_idx = len(inner_rows) - 1
                if overlap_names:
                    inner_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#FFC0C0"))

            # Якщо після фільтрації не залишилося майбутніх відпусток
            if not inner_rows:
                inner_rows.append([Paragraph("—", base_style)])

        inner_table = Table(inner_rows, colWidths=[None])
        inner_table.setStyle(inner_style)

        # Підрахунок використаних днів та залишків (без змін)
        profile_id = emp_data['profile_id']
        last_day_of_last_year = date(year, 1, 1) - timedelta(days=1)

        used_days_before = calendar_work.query.filter(
            calendar_work.reason.in_(['dripicons-card', 'vacation']),
            calendar_work.user_id == profile_id,
            calendar_work.today_date <= last_day_of_last_year
        ).count()

        get_before_vacation_days_sum = db.session.query(
            func.sum(vacation.count_days)
        ).filter(
            vacation.years < year,
            vacation.user_id == profile_id
        ).scalar() or 0

        get_before_canceled_days = db.session.query(
            func.coalesce(func.sum(vacations_canceled.count_days), 0)
        ).filter(
            vacations_canceled.user_id == profile_id,
            vacations_canceled.year < year
        ).scalar() or 0

        available_from_previous_years = get_before_vacation_days_sum - used_days_before - get_before_canceled_days

        used_vacation_in_this_year = calendar_work.query.filter(
            calendar_work.reason == 'vacation',
            calendar_work.user_id == profile_id,
            calendar_work.today_date >= datetime(year, 1, 1),
            calendar_work.today_date <= datetime(year, 12, 31)
        ).count()

        used_compensation_in_this_year = calendar_work.query.filter(
            calendar_work.reason == 'dripicons-card',
            calendar_work.user_id == profile_id,
            calendar_work.today_date >= datetime(year, 1, 1),
            calendar_work.today_date <= datetime(year, 12, 31)
        ).count()

        get_count_canceled_days_this_year = vacations_canceled.query.filter_by(
            user_id=profile_id,
            year=year
        ).first()
        count_canceled_days_this_year = get_count_canceled_days_this_year.count_days if get_count_canceled_days_this_year else 0

        vac_days = vacation.query.filter_by(user_id=profile_id, years=year).first()
        count_vacation_days_in_this_year = vac_days.count_days if vac_days else 0

        total_used = used_vacation_in_this_year + used_compensation_in_this_year

        diff_vacation_this_year = (
                                              count_vacation_days_in_this_year + available_from_previous_years) - total_used - count_canceled_days_this_year

        total_available = available_from_previous_years + count_vacation_days_in_this_year

        data.append([
            idx,
            employee.get('department', ''),
            employee['name'],
            inner_table,
            total_used,
            f"{available_from_previous_years} | {count_vacation_days_in_this_year} | {diff_vacation_this_year}"
        ])

        row_colors.append(emp_data.get('color'))

    # ===================================================================
    # СТВОРЕННЯ ТАБЛИЦІ З ЗАЛИВКОЮ КЕРІВНИКІВ
    # ===================================================================
    table = Table(data, colWidths=[0.4 * inch, 1.3 * inch, 1.6 * inch, None, 0.6 * inch, 1.4 * inch], repeatRows=1)

    table_styles = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSerif'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8F8")]),
    ]

    # Заливка керівників всіх відділів (стовпець "ПІБ" - індекс 2)
    for i, color in enumerate(row_colors):
        if color:
            table_styles.append(('BACKGROUND', (2, i + 1), (2, i + 1), colors.HexColor(color)))

    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    buffer.close()
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename=vacation_conflicts_{year}.pdf'
    return resp