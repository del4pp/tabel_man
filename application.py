from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://localuser_42:K7mPqR9xL2vWnT5jB8sD@46.225.170.124/tabel_odessa"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#app.config.from_object(Configuration)

# Шлях для зберігання завантажених аватарів
UPLOAD_FOLDER = 'static/upload'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.secret_key = 'fdgfh78@#5?>gfhf89dxv06k'

# Ініціалізуйте об'єкт SQLAlchemy з додатком app
db = SQLAlchemy(app)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Видаліть наступний рядок, оскільки db вже ініціалізований з додатком app
# db.init_app(app)

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
