import requests
from datetime import datetime, time as datetime_time
from application import db
from model import fuel_price
import time


class OkkoAPIFuelPriceScraper:
    def __init__(self, api_key=None):
        self.url = "https://ssp-online-back.okko.ua/userdata-service/fuel_prices"
        
        # Якщо API ключ не переданий, беремо з налаштувань
        if not api_key:
            from model import settings_table
            setting = settings_table.query.filter_by(key='fuel_price_api_key').first()
            api_key = setting.value if setting else None
        
        if not api_key:
            raise ValueError("API ключ не знайдено. Будь ласка, додайте його в налаштуваннях.")
        
        self.headers = {
            'accept': 'application/json',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'uk',
            'authorization': f'Bearer {api_key}',
            'dnt': '1',
            'origin': 'https://ssp-online.okko.ua',
            'referer': 'https://ssp-online.okko.ua/erp',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'x-app-version': '1758636590538',
            'x-rt': '1759232753838',
        }
        # Мапінг кодів OKKO на наші типи палива
        self.fuel_mapping = {
            "A-95": "Бензин",
            "DP": "Дизель",
            "SPBT": "Газ"
        }

        # Зберігаємо API ключ для подальшого використання
        self.api_key = api_key

    def get_current_api_key(self):
        """
        Отримання поточного API ключа з налаштувань бази даних

        Returns:
            str or None: API ключ або None, якщо не знайдено
        """
        from model import settings_table
        setting = settings_table.query.filter_by(key='fuel_price_api_key').first()
        return setting.value if setting else None

    def update_headers(self, api_key=None):
        """
        Оновлення HTTP заголовків з новим API ключем

        Args:
            api_key (str, optional): Новий API ключ. Якщо не вказано, береться з налаштувань
        """
        if api_key is None:
            api_key = self.get_current_api_key()

        if not api_key:
            raise ValueError("API ключ не знайдено. Будь ласка, додайте його в налаштуваннях.")

        self.api_key = api_key
        self.headers['authorization'] = f'Bearer {api_key}'
        print(f"🔄 Заголовки оновлено з новим API ключем")

    def test_api_key(self):
        """
        Тестування валідності API ключа через тестовий запит до OKKO API

        Returns:
            bool: True якщо ключ валідний, False в іншому випадку
        """
        try:
            print("🔍 Тестування API ключа...")
            response = requests.get(self.url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                print("✅ API ключ валідний")
                return True
            elif response.status_code == 401:
                print("❌ API ключ невалідний (401 Unauthorized)")
                return False
            else:
                print(f"⚠️  Неочікуваний статус відповіді: {response.status_code}")
                return False
        except requests.RequestException as e:
            print(f"❌ Помилка при тестуванні API ключа: {e}")
            return False

    def get_api_key_info(self):
        """
        Отримання інформації про поточний стан API ключа

        Returns:
            dict: Інформація про API ключ з полями:
                - current_key_masked: Маскований ключ для відображення
                - key_exists: Чи існує ключ у налаштуваннях
                - headers_updated: Чи синхронізовані заголовки з поточним ключем
        """
        current_key = self.get_current_api_key()
        masked_key = current_key[:10] + "..." if current_key else "не встановлено"

        return {
            'current_key_masked': masked_key,
            'key_exists': bool(current_key),
            'headers_updated': hasattr(self, 'api_key') and self.api_key == current_key
        }

    def fetch_prices(self):
        """Отримання цін з API OKKO"""
        try:
            print(f"Запит до OKKO API: {self.url}")
            response = requests.get(self.url, headers=self.headers)
            response.raise_for_status()
            print(f"Статус відповіді: {response.status_code}")
            return response.json()
        except requests.RequestException as e:
            print(f"Помилка при отриманні даних з API: {e}")
            return None

    def parse_prices(self, api_data):
        """Обробка даних з API та підготовка для БД"""
        if not api_data:
            print("Дані з API відсутні")
            return []

        current_date = datetime.now().date()
        data = []

        for item in api_data:
            fuel_name = item.get('name')
            price = item.get('price')

            if fuel_name in self.fuel_mapping and price:
                fuel_type = self.fuel_mapping[fuel_name]
                data.append({
                    'created_at': current_date,
                    'fuel_type': fuel_type,
                    'price': float(price),
                    'original_name': fuel_name,
                    'code': item.get('code')
                })
                print(f"Знайдено: {fuel_name} ({fuel_type}) - {price} грн")

        print(f"\nВсього знайдено релевантних цін: {len(data)}")
        return data

    def save_to_db(self, data):
        """Збереження даних у базу даних"""
        if not data:
            print("Дані для збереження відсутні")
            return

        try:
            saved_count = 0
            updated_count = 0

            for item in data:
                # Перевіряємо чи є вже запис для цього типу палива на сьогодні
                existing_record = fuel_price.query.filter_by(
                    created_at=item['created_at'],
                    fuel_type=item['fuel_type']
                ).first()

                if existing_record:
                    # Оновлюємо ціну якщо вона відрізняється
                    if existing_record.price != item['price']:
                        existing_record.price = item['price']
                        updated_count += 1
                        print(f"✓ Оновлено ціну для {item['fuel_type']} ({item['original_name']}): "
                              f"{existing_record.price} → {item['price']} грн на дату {item['created_at']}")
                    else:
                        print(
                            f"- Ціна для {item['fuel_type']} ({item['original_name']}) не змінилася: {item['price']} грн")
                else:
                    # Додаємо новий запис
                    new_record = fuel_price(
                        created_at=item['created_at'],
                        fuel_type=item['fuel_type'],
                        price=item['price']
                    )
                    db.session.add(new_record)
                    saved_count += 1
                    print(f"✓ Додано новий запис для {item['fuel_type']} ({item['original_name']}): "
                          f"{item['price']} грн на дату {item['created_at']}")

            db.session.commit()
            print(f"\n{'=' * 60}")
            print(f"Дані успішно збережено в БД")
            print(f"Нових записів: {saved_count}")
            print(f"Оновлених записів: {updated_count}")
            print(f"{'=' * 60}\n")
        except Exception as e:
            print(f"✗ Помилка при збереженні в БД: {e}")
            db.session.rollback()

    def run(self):
        """Запуск парсингу цін"""
        print(f"\n{'=' * 60}")
        print(f"Парсинг цін з OKKO API о {datetime.now()}")
        print(f"{'=' * 60}\n")

        # Перевіряємо та оновлюємо API ключ перед запитом
        current_key = self.get_current_api_key()
        if not current_key:
            print("❌ API ключ не знайдено в налаштуваннях")
            return []

        if current_key != self.api_key:
            print("🔄 API ключ змінився, оновлюємо заголовки...")
            self.update_headers(current_key)

        api_data = self.fetch_prices()

        if api_data:
            print(f"\nОтримано {len(api_data)} позицій палива з API\n")
            data = self.parse_prices(api_data)
            if data:
                self.save_to_db(data)
                return data

        print("Не вдалося отримати дані")
        return []


def run_scraper_with_context():
    """Запуск парсера в контексті Flask"""
    from application import app
    with app.app_context():
        scraper = OkkoAPIFuelPriceScraper()

        # Спочатку тестуємо API ключ
        if not scraper.test_api_key():
            print("❌ Неможливо продовжити через проблеми з API ключем")
            return

        results = scraper.run()
        if results:
            print("\nПідсумок отриманих цін:")
            for item in results:
                print(f"  • {item['fuel_type']} ({item['original_name']}): {item['price']} грн")
        else:
            print("Результатів немає")


def run_scheduler():
    """Запуск планувальника без бібліотеки schedule"""
    from application import app

    print("Планувальник налаштовано для запуску щодня о 08:00")
    print("Для одноразового тестування викличте: run_scraper_with_context()\n")

    target_time = datetime_time(8, 0)  # 08:00

    while True:
        now = datetime.now()
        current_time = now.time()

        # Перевіряємо чи настав час запуску (08:00)
        if current_time.hour == target_time.hour and current_time.minute == target_time.minute:
            print(f"\n⏰ Настав час запуску: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            with app.app_context():
                scraper = OkkoAPIFuelPriceScraper()

                # Тестуємо API ключ перед запуском
                if scraper.test_api_key():
                    scraper.run()
                else:
                    print("❌ Пропускаємо запуск через проблеми з API ключем")

            # Чекаємо 60 секунд щоб не запускати двічі в одну хвилину
            time.sleep(60)

        # Перевірка кожні 30 секунд
        time.sleep(30)


if __name__ == "__main__":
    # Одноразовий запуск для тестування (розкоментуй якщо потрібно)
    run_scraper_with_context()

    # Або запусти планувальник для щоденного запуску о 08:00
    # run_scheduler()