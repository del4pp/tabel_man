from application import app, db
from reportlab.pdfbase import pdfmetrics
import view
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import OkkoAPIFuelPriceScraper
import threading
import time
from datetime import datetime

# Функція для запуску FuelPriceScraper
def run_fuel_scraper():
    print(f"Запуск парсера: {datetime.now()}")
    try:
        with app.app_context():
            print("Увійшли в контекст Flask")
            scraper = OkkoAPIFuelPriceScraper()
            results = scraper.run()
            if results:
                for item in results:
                    print(f"Дата: {item['created_at']}, Тип палива: {item['fuel_type']}, Ціна: {item['price']}")
            else:
                print("Результатів немає")
    except Exception as e:
        print(f"Помилка в run_fuel_scraper: {e}")

# Функція для запуску Flask-сервера
def run_flask():
    print("Запуск Flask-сервера...")
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)

if __name__ == "__main__":
    # Налаштування планувальника
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=run_fuel_scraper,
        trigger="cron",
        hour=8,  # Запуск щодня о 08:00
        minute=0,
        timezone="Europe/Kyiv"
    )

    # Додаємо запуск парсера чеків (транзакцій) кожні 30 хвилин
    """from auto import run_okko_sync
    scheduler.add_job(
        func=run_okko_sync,
        trigger="interval",
        minutes=30,
        next_run_time=datetime.now()  # Запустити одразу при старті
    )
    print("Планувальник налаштовано")
    scheduler.start()
    print("Планувальник запущено")"""

    # Запуск Flask у окремому потоці
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Щоб потік зупинився при завершенні програми
    flask_thread.start()

    # Утримуємо основний потік живий
    try:
        while True:
            time.sleep(1)  # Затримка для уникнення навантаження
    except KeyboardInterrupt:
        print("Зупинка програми...")
        scheduler.shutdown()
        print("Програма зупинена")