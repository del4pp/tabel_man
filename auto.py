import requests
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
from sqlalchemy.exc import IntegrityError
import application
from application import db
from model import fuel_contracts, fuel_okko_cards, fuel_okko_transactions


class OkkoAPISync:
    def __init__(self, api_keys):
        """
        api_keys: dict with company_name: api_key
        Example: {'Scania': 'key1', 'TF': 'key2'}
        """
        self.base_url = "https://gw-online.okko.ua:9443/api/erp/v2"
        self.api_keys = api_keys
        self.page_size = 100

    def set_api_key_for_company(self, company_name):
        """Sets the API key for the current company"""
        if company_name not in self.api_keys:
            print(f"API key not found for company: {company_name}")
            return False
        self.headers = {
            'accept': 'application/json',
            'X-API-KEY': self.api_keys[company_name],
        }
        return True

    def make_request(self, url, max_retries=3):
        """Виконує запит з повтором у випадку помилки"""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                print(f"Помилка запиту (спроба {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise
        return None

    def get_date_ranges_current_month(self):
        """Повертає період з 1 числа поточного місяця до сьогодні"""
        today = datetime.now().date()
        start_date = today.replace(day=1)
        end_date = today
        return [(start_date, end_date)]
    
    def get_date_ranges_for_month(self, month, year):
        """Повертає період для конкретного місяця та року"""
        from calendar import monthrange
        start_date = datetime(year, month, 1).date()
        last_day = monthrange(year, month)[1]
        end_date = datetime(year, month, last_day).date()
        return [(start_date, end_date)]

    def get_all_transactions_for_card(self, card_num, date_from, date_to):
        """Отримує всі транзакції для картки з пагінацією"""
        all_transactions = []
        offset = 0

        while True:
            url = (f"{self.base_url}/transactions?date_from={date_from}&date_to={date_to}"
                   f"&processed_in_bo=true&card_num={card_num}&size={self.page_size}&offset={offset}")

            data = self.make_request(url)

            if not data or 'items' not in data:
                break

            transactions = data['items']
            if not transactions:
                break

            all_transactions.extend(transactions)

            if len(transactions) < self.page_size:
                break

            offset += self.page_size
            time.sleep(0.3)

        return all_transactions

    def sync_transactions_for_company(self, company_name, month=None, year=None):
        """Синхронізує транзакції для конкретної компанії"""
        if month and year:
            print(f"Синхронізація транзакцій для {company_name} за {month}/{year}...")
        else:
            print(f"Синхронізація транзакцій для {company_name} з початку місяця до сьогодні...")

        if not self.set_api_key_for_company(company_name):
            print(f"Пропуск синхронізації транзакцій для {company_name}")
            return 0

        # Вибираємо діапазон дат в залежності від параметрів
        if month and year:
            date_ranges = self.get_date_ranges_for_month(month, year)
        else:
            date_ranges = self.get_date_ranges_current_month()
            
        if not date_ranges:
            print("Немає періодів для обробки")
            return 0

        company_contracts = fuel_contracts.query.filter_by(company_name=company_name).all()
        company_contract_ids = [c.contract_id for c in company_contracts]

        if not company_contract_ids:
            print(f"Немає контрактів для {company_name}")
            return 0

        cards = fuel_okko_cards.query.all()
        if not cards:
            print("Немає карток у базі даних")
            return 0

        print(f"Обробляємо {len(cards)} карток за {len(date_ranges)} періодів для {company_name}")

        company_total_new = 0

        for (date_from, date_to) in date_ranges:
            print(f"\n{company_name} - Період: {date_from} - {date_to}")
            period_new_transactions = 0

            for card in tqdm(cards, desc=f"{company_name} - Картки"):
                try:
                    transactions_data = self.get_all_transactions_for_card(
                        card.card_num, date_from, date_to
                    )

                    company_transactions = [
                        t for t in transactions_data
                        if t.get('contract_id') and str(t.get('contract_id')) in company_contract_ids
                    ]

                    for trans in company_transactions:
                        try:
                            trans_id = trans.get('trans_id')
                            if not trans_id:
                                continue

                            existing = fuel_okko_transactions.query.filter_by(
                                trans_id=int(trans_id)
                            ).first()

                            if not existing:
                                trans_date = None
                                if trans.get('trans_date'):
                                    try:
                                        trans_date = datetime.fromisoformat(
                                            trans['trans_date'].replace('T', ' ').replace('.000', '')
                                        )
                                    except ValueError:
                                        pass

                                product_desc = trans.get('product_desc')
                                fuel_volume = trans.get('volume')

                                # ✅ умова для картки 7825390000082353
                                if trans.get('card_num') == "7825390000082353" and product_desc != "Газ скраплений автомобільний":
                                    product_desc = f"{product_desc} ({fuel_volume}) -> Газ скраплений автомобільний"
                                    if fuel_volume:
                                        try:
                                            fuel_volume = float(fuel_volume) * 1.25
                                        except (TypeError, ValueError):
                                            pass

                                new_transaction = fuel_okko_transactions(
                                    trans_id=int(trans_id),
                                    amnt_trans=trans.get('amnt_trans'),
                                    card_num=trans.get('card_num'),
                                    trans_date=trans_date,
                                    contract_id=int(trans['contract_id']) if trans.get('contract_id') else None,
                                    azs_name=trans.get('azs_name'),
                                    addr_name=trans.get('addr_name'),
                                    fuel_volume=fuel_volume,
                                    fuel_price=trans.get('price'),
                                    product_desc=product_desc,
                                    person_first_name=trans.get('person_first_name'),
                                    person_last_name=trans.get('person_last_name'),
                                    trans_type=trans.get('trans_type'),
                                    discount=trans.get('amount_discount'),
                                )
                                db.session.add(new_transaction)
                                period_new_transactions += 1

                        except Exception as e:
                            print(f"Помилка при обробці транзакції {trans.get('trans_id')}: {e}")
                            continue

                except Exception as e:
                    print(f"Помилка при обробці картки {card.card_num}: {e}")
                    continue

            try:
                db.session.commit()
                print(f"{company_name} - Додано нових транзакцій: {period_new_transactions}")
                company_total_new += period_new_transactions
            except Exception as e:
                db.session.rollback()
                print(f"Помилка при збереженні транзакцій: {e}")

        print(f"\n{company_name} - Синхронізація завершена. Нових транзакцій: {company_total_new}")
        return company_total_new


def run_okko_sync(month=None, year=None):
    api_keys = {
        'Scania': '6b6df184-75e4-489d-bebf-a5e5fc558d84',
        'TF': 'd40a2036-84d2-44ed-bc2c-8c86b0ff61d2'
    }
    with application.app.app_context():
        sync = OkkoAPISync(api_keys)
        for company_name in api_keys.keys():
            sync.sync_transactions_for_company(company_name, month=month, year=year)


if __name__ == "__main__":
    print(f"Старт автоматичної синхронізації кожні 30 хвилин...")
    with application.app.app_context():
        while True:
            run_okko_sync()
            print(f"Чекаємо 30 хвилин... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            time.sleep(1800)
