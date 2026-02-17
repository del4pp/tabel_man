from novaposhta.client import NovaPoshtaApi
from datetime import datetime, timedelta
import application
from model import nova_poshta_parcels
from application import db  # Імпортуємо базу даних із Flask-додатку

class NovaPoshtaTracker:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = NovaPoshtaApi(api_key, timeout=30)
        self.base_url = 'https://api.novaposhta.ua/v2.0/json/'

    def fetch_incoming_documents(self):
        """Отримання вхідних документів за останні 30 днів через NovaPoshtaApi"""
        date_to = datetime.now()
        date_from = date_to - timedelta(days=30)

        date_from_str = date_from.strftime('%d.%m.%Y %H:%M:%S')
        date_to_str = date_to.strftime('%d.%m.%Y %H:%M:%S')

        try:
            get_docs = self.client.internet_document.get_incoming_documents_by_phone(date_from_str, date_to_str, 200)
            print(f"Отримано {len(get_docs['data'][0]['result'])} документів за період {date_from_str} - {date_to_str}")
            return get_docs['data'][0]['result']  # Повертаємо список документів
        except Exception as e:
            print(f"Помилка отримання документів: {e}")
            return []

    def update_parcels(self):
        """Оновлення даних про посилки в базі та позначення старих як отриманих"""
        documents = self.fetch_incoming_documents()

        if not documents:
            print("Немає документів для обробки.")
            return

        # Збираємо список ТТН із API
        api_tracking_numbers = {doc.get('Number') for doc in documents if doc.get('Number')}

        # Оновлення або додавання записів із API
        for doc in documents:
            tracking_number = doc.get('Number')
            if not tracking_number:
                print(f"Пропущено запис без номера ТТН: {doc}")
                continue

            # Перевірка, чи існує запис у базі
            parcel = nova_poshta_parcels.query.filter_by(tracking_number=tracking_number).first()

            # Підготовка даних для запису
            parcel_data = {
                'tracking_number': tracking_number,
                'recipient_phone': doc.get('PhoneRecipient', ''),
                'sender_phone': doc.get('PhoneSender', ''),
                'nova_poshta_status': doc.get('TrackingStatusName', 'Невідомий статус'),
                'tracking_status_code': doc.get('TrackingStatusCode', ''),
                'ref_ew': doc.get('RefEW', ''),
                'cost': float(doc.get('Cost', 0)) if doc.get('Cost') else 0.0,
                'document_cost': float(doc.get('DocumentCost', 0)) if doc.get('DocumentCost') else 0.0,
                'payment_method': doc.get('PaymentMethod', ''),
                'payer_type': doc.get('PayerType', ''),
                'cargo_type': doc.get('CargoType', ''),
                'seats_amount': int(doc.get('SeatsAmount', 0)) if doc.get('SeatsAmount') else 0,
                'created_at': datetime.strptime(doc.get('DateTime', '0001-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') if doc.get('DateTime') != '0001-01-01 00:00:00' else None,
                'updated_at': datetime.strptime(doc.get('TrackingUpdateDate', '0001-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') if doc.get('TrackingUpdateDate') != '0001-01-01 00:00:00' else None,
                'arrival_date_time': datetime.strptime(doc.get('ArrivalDateTime', '0001-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') if doc.get('ArrivalDateTime') != '0001-01-01 00:00:00' else None,
                'scheduled_delivery_date': datetime.strptime(doc.get('ScheduledDeliveryDate', '0001-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S') if doc.get('ScheduledDeliveryDate') != '0001-01-01 00:00:00' else None,
                'cargo_description': doc.get('CargoDescription', ''),
                'sender_name': doc.get('SenderName', ''),
                'city_sender': doc.get('CitySenderDescription', ''),
                'counterparty_sender': doc.get('CounterpartySenderDescription', ''),
                'recipient_name': doc.get('RecipientName', ''),
                'city_recipient': doc.get('CityRecipientDescription', ''),
                'recipient_address': doc.get('RecipientAddressDescription', ''),
                'note': doc.get('Note', ''),
                'scania_updated_at': datetime.now()
            }

            if parcel:
                # Оновлення існуючого запису
                for key, value in parcel_data.items():
                    setattr(parcel, key, value)
                print(f"Оновлено запис: ТТН {tracking_number}, Статус НП: {parcel.nova_poshta_status}")
            else:
                # Створення нового запису
                parcel = nova_poshta_parcels(**parcel_data)
                db.session.add(parcel)
                print(f"Додано новий запис: ТТН {tracking_number}, Статус НП: {parcel.nova_poshta_status}")

            db.session.commit()

        # Перевірка записів у базі, які не оновилися з API
        all_parcels = nova_poshta_parcels.query.all()
        for parcel in all_parcels:
            if parcel.tracking_number not in api_tracking_numbers and parcel.nova_poshta_status != "Отримано":
                # Якщо ТТН немає в API і статус ще не "Отримано", змінюємо статус
                parcel.nova_poshta_status = "Отримано"
                parcel.updated_at = datetime.now()  # Оновлюємо дату оновлення
                print(f"Позначено як отримано (відсутнє в API): ТТН {parcel.tracking_number}")
                db.session.commit()

    def close(self):
        """Закриття клієнта"""
        self.client.close_sync()