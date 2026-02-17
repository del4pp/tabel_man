import flask
import requests
from sqlalchemy.sql.functions import count
from werkzeug.utils import redirect, secure_filename
from application import app, db
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, flash, session, url_for, redirect, jsonify, Response, g, make_response
from model import *
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from datetime import datetime, timedelta, time as dtimeonly
import hashlib, os, random, string, time
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from functools import wraps
import threading
import traceback
import logging
from math import ceil
from tm_auth import auth


class Departaments:
    def get_departaments_list(self):
        get_departaments = departaments.query.all()
        departament_list = []
        for depart in get_departaments:
            dep_leader = users.query.filter_by(user_departament=depart.id, user_access=2).first()
            if depart.dep_name != 'Адміністратори':
                departament_list.append({
                    'id': depart.id,
                    'name': depart.dep_name,
                    'dep_leader': dep_leader.user_fullname if dep_leader else 'Не вибраний',
                    'count_users': users.query.filter_by(user_departament=depart.id).count(),
                    'position': depart.sort_num
                })
        return departament_list

    def get_departaments_list_userdep(self, user_id):
        get_departaments = users_departament.query.filter_by(user_id=user_id).all()
        departament_list = []
        for depart in get_departaments:
            dep_leader = users.query.filter_by(user_departament=depart.dep_id, user_access=2).first()
            departement_info = departaments.query.filter_by(id=depart.dep_id).first()
            if departement_info.dep_name != 'Адміністратори':
                departament_list.append({
                    'id': departement_info.id,
                    'name': departement_info.dep_name,
                    'dep_leader': dep_leader.user_fullname if dep_leader else 'Не вибраний',
                    'count_users': users.query.filter_by(user_departament=depart.id).count(),
                    'position': departement_info.sort_num
                })
        return departament_list

    def get_departaments_users(self):
        get_users = users.query.all()
        user_list = []
        for user in get_users:
            if user.user_departament != 14:
                user_list.append({
                    'id': user.id,
                    'user_name': user.user_fullname,
                    'departament': user.user_departament,
                    'head': True if user_head.query.filter_by(head_id=user.id).first() else False
                })
        return user_list

    def get_departaments_users_position(self, departament_id):
        get_users = users.query.filter_by(user_departament=departament_id).order_by(users.user_num_list.asc()).all()
        user_list = []
        for user in get_users:
            if user.user_departament != 14:
                user_list.append({
                    'id': user.id,
                    'user_name': user.user_fullname,
                    'departament': user.user_departament,
                    'head': True if user_head.query.filter_by(head_id=user.id).first() else False
                })
        return user_list
