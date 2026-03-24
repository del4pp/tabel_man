from application import app, db
import model

with app.app_context():
    db.create_all()
    print("Database tables created successfully (if they were missing).")
