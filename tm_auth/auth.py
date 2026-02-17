from datetime import timedelta
from flask import Flask, abort, session, request, app, redirect, url_for, jsonify
from application import app, db
from model import *
import secrets
from flask_login import login_user
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, flash, session, url_for, redirect, jsonify, Response, g, make_response
from flask_login import LoginManager, login_user, current_user, login_required, logout_user


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        email = request.form.get('inputEmail')
        password = request.form.get('inputPassword')
        remember = True if request.form.get('remember') else False

        user = users.query.filter_by(user_email=email).first()
        print(email, password)
        if user and check_password_hash(user.user_pass,password):
            login_user(user, remember=remember)
            return redirect(url_for('calendar_view'))

        flash("Користувач з такими даними не знайдений")
        return redirect(url_for('logout'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')