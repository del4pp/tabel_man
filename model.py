from application import db
from datetime import datetime
from sqlalchemy.orm import relationship


class users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(255))
    user_avatar = db.Column(db.String(255))
    user_fullname = db.Column(db.String(255))
    user_pass = db.Column(db.String(255))
    user_access = db.Column(db.Integer)
    user_departament = db.Column(db.Integer)
    display = db.Column(db.Integer)
    phone_num_one = db.Column(db.String(255))
    phone_num_two = db.Column(db.String(255))
    birthdate = db.Column(db.DateTime)
    join_date = db.Column(db.DateTime)
    company = db.Column(db.String(255))
    gender = db.Column(db.String(255))
    user_num_list = db.Column(db.Integer)
    transportation = db.Column(db.Integer)

    def __init__(self, *args, **kwargs):
        super(users, self).__init__(*args, **kwargs)

    def is_active(self):
        return True

    def get_id(self):
        return self.id

    def is_authenticated(self):
        return self.authenticated

    def is_anonymous(self):
        return False

    def __repr__(self):
            return "user name: {}".format(self.id)


class departaments(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dep_name = db.Column(db.String)
    leader = db.Column(db.Integer)
    sort_num = db.Column(db.Integer)


    def __init__(self, *args, **kwargs):
        super(departaments, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"DepartmentID: {self.id}"

class users_departament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    dep_id = db.Column(db.Integer, db.ForeignKey('departaments.id'), nullable=False)
    access_level = db.Column(db.Integer)

    def __init__(self, *args, **kwargs):
        super(users_departament, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"

class company_list(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String)

    def __init__(self, *args, **kwargs):
        super(company_list, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class absens_from_work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    date_remove = db.Column(db.Date)
    remove_reason = db.Column(db.String)

    def __init__(self, *args, **kwargs):
        super(absens_from_work, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"

class user_head(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    head_id = db.Column(db.Integer)

    def __init__(self, *args, **kwargs):
        super(user_head, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"



class calendar_work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    today_date = db.Column(db.Date)
    user_id = db.Column(db.Integer)
    work_time = db.Column(db.Float)
    work_status = db.Column(db.Integer)
    work_fact = db.Column(db.Float)
    reason = db.Column(db.String)

    def __init__(self, *args, **kwargs):
        super(calendar_work, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class work_comments(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    records_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    comment = db.Column(db.Integer)
    dt_event = db.Column(db.DateTime)
    user_add_comment = db.Column(db.Integer)

    def __init__(self, *args, **kwargs):
        super(work_comments, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class user_car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    auto_name = db.Column(db.String(255))
    fuel_type = db.Column(db.String(255))
    fuel_limit = db.Column(db.Float)
    distance = db.Column(db.Float)
    created_at = db.Column(db.Date)
    compensation_type = db.Column(db.String(20))
    fuel_card = db.Column(db.String(255))

    def __init__(self, *args, **kwargs):
        super(user_car, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"

class settings_table(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)  # Назва налаштування, наприклад "compensation_cost"
    value = db.Column(db.String(1055), nullable=False)  # Значення налаштування, наприклад 100 (грн)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Дата створення для відстеження

    def __init__(self, *args, **kwargs):
        super(settings_table, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"Setting: {self.key} = {self.value}"

class fuel_technoforum(db.Model):
    __tablename__ = 'fuel_technoforum'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.Date, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    refuel = db.Column(db.Float, nullable=False)
    comment = db.Column(db.String(255), nullable=True)
    total_fuel_usage = db.Column(db.Float, nullable=True)
    additional_fuel_usage = db.Column(db.Float, nullable=True)
    travel_days = db.Column(db.Integer, nullable=True)  # Переконайтеся, що це поле є

    def __init__(self, *args, **kwargs):
        super(fuel_technoforum, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"FuelTechnoforum(id={self.id}, user_id={self.user_id}, created_at={self.created_at})"

class company_car(db.Model):
    __tablename__ = 'company_car'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    car_number = db.Column(db.String(255), nullable=False)
    car_name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    fuel_norm = db.Column(db.Float, nullable=False)
    tank_volume = db.Column(db.Integer, nullable=True)
    public_insurance = db.Column(db.Date, nullable=True)
    kasko_insurance = db.Column(db.Date, nullable=True)
    company_name = db.Column(db.String(255), nullable=False)
    fuel_type = db.Column(db.String(50), nullable=False, default='Бензин')
    initial_mileage = db.Column(db.Integer, nullable=True)  # Нове поле: Початковий пробіг
    initial_fuel_balance = db.Column(db.Float, nullable=True)  # Нове поле: Початковий залишок палива
    created_at = db.Column(db.Date, nullable=True)
    public_company = db.Column(db.String(255), nullable=False)
    kasko_company = db.Column(db.String(255), nullable=False)
    plan_to = db.Column(db.Date, nullable=True)
    avtopark = db.Column(db.Integer, nullable=True)
    pay_date = db.Column(db.String(255), nullable=True)

    def __init__(self, *args, **kwargs):
        super(company_car, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"CompanyCar(id={self.id}, car_number={self.car_number}, car_name={self.car_name})"



class car_mileage(db.Model):
    __tablename__ = 'car_mileage'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    car_id = db.Column(db.Integer, db.ForeignKey('company_car.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    mileage = db.Column(db.Integer, nullable=False)  # Пробіг
    fuel_added = db.Column(db.Float, nullable=True)  # Кількість заправленого палива
    public_insurance = db.Column(db.Date, nullable=True)  # Оновлення державної страховки
    kasko_insurance = db.Column(db.Date, nullable=True)  # Оновлення КАСКО

    car = db.relationship('company_car', backref='mileages')

    def __init__(self, *args, **kwargs):
        super(car_mileage, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"CarMileage(id={self.id}, car_id={self.car_id}, mileage={self.mileage})"

class fuel_price(db.Model):
    __tablename__ = 'fuel_price'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.Date, nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __init__(self, *args, **kwargs):
        super(fuel_price, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"Fuel: {self.price}"

class employee_transport(db.Model):
    __tablename__ = 'employee_transport'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    day_shift = db.Column(db.Boolean, default=False)  # Денна зміна (0 або 1)
    night_shift = db.Column(db.Boolean, default=False)  # Нічна зміна (0 або 1)
    day_comment = db.Column(db.String(255), nullable=True)
    night_comment = db.Column(db.String(255), nullable=True)

    # Унікальний індекс для комбінації user_id та date
    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='unique_user_date'),)

    def __init__(self, *args, **kwargs):
        super(employee_transport, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"EmployeeTransport(id={self.id}, user_id={self.user_id}, date={self.date}, day_shift={self.day_shift}, night_shift={self.night_shift})"

class fuel_data(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    vehicle_name = db.Column(db.String(255))
    fuel_type = db.Column(db.String(255))
    quantity = db.Column(db.Float)
    cost = db.Column(db.Float)
    date_refuel = db.Column(db.DateTime)
    comments = db.Column(db.Text)

    def __init__(self, *args, **kwargs):
        super(fuel_data, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class fuel_limits(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    monthly_limit = db.Column(db.Float)

    def __init__(self, *args, **kwargs):
        super(fuel_limits, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"

class fuel_used(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    month = db.Column(db.Integer)
    year = db.Column(db.Integer)
    fuel = db.Column(db.Float)

    def __init__(self, *args, **kwargs):
        super(fuel_used, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"

class vacations_canceled(db.Model):
    __tablename__ = 'vacations_canceled'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # Рік анулювання відпусток
    year = db.Column(db.Integer)  # Рік анулювання відпусток
    count_days = db.Column(db.Integer)  # Кількість анульованих відпусток

    def __init__(self, *args, **kwargs):
        super(vacations_canceled, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"<CanceledVacations(id={self.id}, year={self.year}, canceled_count={self.count_days})>"


class vacation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    count_days = db.Column(db.Integer)
    years = db.Column(db.Integer)

    def __init__(self, *args, **kwargs):
        super(vacation, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class resetpassword(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    secret_key = db.Column(db.String)
    end_dt = db.Column(db.DateTime)

    def __init__(self, *args, **kwargs):
        super(resetpassword, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class log_system(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    type_event = db.Column(db.String)

    def __init__(self, *args, **kwargs):
        super(log_system, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class telegram_exclusions(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # 'scania' or 'tf'
    company_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, *args, **kwargs):
        super(telegram_exclusions, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"UserID: {self.id}"


class nova_poshta_parcels(db.Model):
    __tablename__ = 'nova_poshta_parcels'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tracking_number = db.Column(db.String(14), nullable=False, unique=True)  # Номер ТТН (IntDocNumber або Number)
    recipient_phone = db.Column(db.String(13), nullable=False)  # Телефон отримувача
    sender_phone = db.Column(db.String(13), nullable=True)  # Телефон відправника
    nova_poshta_status = db.Column(db.String(255), nullable=True)  # Статус від НП (TrackingStatusName)
    internal_status = db.Column(db.String(20), nullable=False, default='Не отримано')  # Внутрішній статус
    created_at = db.Column(db.DateTime, nullable=True)  # Дата створення (DateTime)
    updated_at = db.Column(db.DateTime, nullable=True)  # Дата оновлення (TrackingUpdateDate)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Зв'язок із користувачем

    # Додаткові поля з API
    tracking_status_code = db.Column(db.String(10), nullable=True)  # Код статусу (TrackingStatusCode)
    ref_ew = db.Column(db.String(36), nullable=True)  # RefEW
    cost = db.Column(db.Float, nullable=True)  # Вартість (Cost)
    document_cost = db.Column(db.Float, nullable=True)  # Вартість доставки (DocumentCost)
    payment_method = db.Column(db.String(50), nullable=True)  # Метод оплати (PaymentMethod)
    payer_type = db.Column(db.String(50), nullable=True)  # Тип платника (PayerType)
    cargo_type = db.Column(db.String(50), nullable=True)  # Тип вантажу (CargoType)
    seats_amount = db.Column(db.Integer, nullable=True)  # Кількість місць (SeatsAmount)
    arrival_date_time = db.Column(db.DateTime, nullable=True)  # Дата прибуття (ArrivalDateTime)
    scheduled_delivery_date = db.Column(db.DateTime, nullable=True)  # Запланована дата доставки (ScheduledDeliveryDate)
    scania_updated_at = db.Column(db.DateTime, nullable=True)  # Запланована дата доставки (ScheduledDeliveryDate)
    cargo_description = db.Column(db.String(255), nullable=True)  # Опис вантажу (CargoDescription)
    sender_name = db.Column(db.String(255), nullable=True)  # Ім'я відправника (SenderName)
    city_sender = db.Column(db.String(255), nullable=True)  # Місто відправника (CitySenderDescription)
    counterparty_sender = db.Column(db.String(255),
                                    nullable=True)  # Контрагент відправника (CounterpartySenderDescription)
    recipient_name = db.Column(db.String(255), nullable=True)  # Ім'я отримувача (RecipientName)
    city_recipient = db.Column(db.String(255), nullable=True)  # Місто отримувача (CityRecipientDescription)
    recipient_address = db.Column(db.String(255), nullable=True)  # Адреса отримувача (RecipientAddressDescription)
    note = db.Column(db.Text, nullable=True)  # Примітка (Note)
    # Нове поле "Коментар"
    comment = db.Column(db.String(255), nullable=True)

    # Зв'язок із таблицею users
    user = db.relationship('users', backref='parcels')

    def __init__(self, **kwargs):
        super(nova_poshta_parcels, self).__init__(**kwargs)
        # Встановлення internal_status залежно від nova_poshta_status
        if self.nova_poshta_status and (
                'Доставлено' in self.nova_poshta_status or 'Отримано' in self.nova_poshta_status):
            self.internal_status = 'Отримано'

    def __repr__(self):
        return f"Parcel(tracking_number={self.tracking_number}, recipient_phone={self.recipient_phone}, internal_status={self.internal_status})"

class transactions(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    edrpou_sender = db.Column(db.String(255), nullable=True)
    sender_nbu_code = db.Column(db.String(255), nullable=True)
    sender_account = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    operation_date = db.Column(db.DateTime, nullable=True)
    operation_code = db.Column(db.String(10), nullable=True)
    receiver_nbu_code = db.Column(db.String(255), nullable=True)
    receiver_name = db.Column(db.String(255), nullable=True)
    receiver_account = db.Column(db.String(255), nullable=True)
    receiver_edrpou = db.Column(db.String(255), nullable=True)
    receiver_correspondent = db.Column(db.String(255), nullable=True)
    document_number = db.Column(db.String(255), nullable=True)
    document_date = db.Column(db.Date, nullable=True)
    debit = db.Column(db.Float, nullable=True, default=0.0)
    credit = db.Column(db.Float, nullable=True, default=0.0)
    payment_purpose = db.Column(db.Text, nullable=True)
    uah_coverage = db.Column(db.Float, nullable=True, default=0.0)

    def __init__(self, *args, **kwargs):
        super(transactions, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"Transaction(id={self.id}, document_number={self.document_number}, operation_date={self.operation_date})"

    def to_dict(self):
        return {
            'id': self.id,
            'edrpou_sender': self.edrpou_sender,
            'sender_nbu_code': self.sender_nbu_code,
            'sender_account': self.sender_account,
            'currency': self.currency,
            'operation_date': self.operation_date.strftime('%Y-%m-%d %H:%M:%S') if self.operation_date else None,
            'operation_code': self.operation_code,
            'receiver_nbu_code': self.receiver_nbu_code,
            'receiver_name': self.receiver_name,
            'receiver_account': self.receiver_account,
            'receiver_edrpou': self.receiver_edrpou,
            'receiver_correspondent': self.receiver_correspondent,
            'document_number': self.document_number,
            'document_date': self.document_date.strftime('%Y-%m-%d') if self.document_date else None,
            'debit': self.debit,
            'credit': self.credit,
            'payment_purpose': self.payment_purpose,
            'uah_coverage': self.uah_coverage
        }


# Додайте ці класи в кінець вашого файлу models.py

class fuel_contracts(db.Model):
    __tablename__ = 'fuel_contracts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.String(20), nullable=True)
    contract_name = db.Column(db.String(255), nullable=True)
    company_name = db.Column(db.String(255), nullable=True)

    def __init__(self, *args, **kwargs):
        super(fuel_contracts, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"FuelContract(id={self.id}, contract_name={self.contract_name}, company_name={self.company_name})"


class fuel_okko_cards(db.Model):
    __tablename__ = 'fuel_okko_cards'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    card_num = db.Column(db.String(25), nullable=True, index=True)
    card_first_name = db.Column(db.String(255), nullable=True)
    card_last_name = db.Column(db.String(255), nullable=True)
    card_owner_vin = db.Column(db.String(255), nullable=True)
    exp_date = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT', onupdate='RESTRICT'), nullable=True,
                        index=True)

    # Зв'язок з таблицею users
    user = db.relationship('users', backref='fuel_cards')

    def __init__(self, *args, **kwargs):
        super(fuel_okko_cards, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"FuelOkkoCard(id={self.id}, card_num={self.card_num}, user_id={self.user_id})"


class fuel_okko_transactions(db.Model):
    __tablename__ = 'fuel_okko_transactions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    trans_id = db.Column(db.Integer, nullable=True)
    amnt_trans = db.Column(db.Integer, nullable=True)
    card_num = db.Column(db.String(255),
                         db.ForeignKey('fuel_okko_cards.card_num', ondelete='RESTRICT', onupdate='RESTRICT'),
                         nullable=True, index=True)
    trans_date = db.Column(db.DateTime, nullable=True)
    contract_id = db.Column(db.String(20),
                            db.ForeignKey('fuel_contracts.contract_id', ondelete='RESTRICT', onupdate='RESTRICT'),
                            nullable=True, index=True)
    azs_name = db.Column(db.String(255), nullable=True)
    addr_name = db.Column(db.String(512), nullable=True)
    fuel_volume = db.Column(db.Integer, nullable=True)
    fuel_price = db.Column(db.Integer, nullable=True)
    product_desc = db.Column(db.String(255), nullable=True)
    person_first_name = db.Column(db.String(255), nullable=True)
    person_last_name = db.Column(db.String(255), nullable=True)
    trans_type = db.Column(db.Integer, nullable=True)
    discount = db.Column(db.Integer, nullable=True)

    # Зв'язки з іншими таблицями
    card = db.relationship('fuel_okko_cards', backref='transactions')
    contract = db.relationship('fuel_contracts', backref='transactions', foreign_keys=[contract_id])

    def __init__(self, *args, **kwargs):
        super(fuel_okko_transactions, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"FuelOkkoTransaction(id={self.id}, trans_id={self.trans_id}, card_num={self.card_num}, contract_id={self.contract_id})"


class calendar_work_temp(db.Model):
    __tablename__ = 'calendar_work_temp'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    original_id = db.Column(db.Integer, db.ForeignKey('calendar_work.id', ondelete='CASCADE'), nullable=False)
    today_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    work_time = db.Column(db.Float)
    work_status = db.Column(db.Integer)
    work_fact = db.Column(db.Float)
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, *args, **kwargs):
        super(calendar_work_temp, self).__init__(*args, **kwargs)

    def __repr__(self):
        return f"CalendarWorkTemp(id={self.id}, original_id={self.original_id}, user_id={self.user_id})"