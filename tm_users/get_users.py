from calendar import monthrange

from dateutil.utils import today
from sqlalchemy.util import column_set
from sqlalchemy.orm import joinedload
from concurrent.futures import ThreadPoolExecutor
from model import *
from datetime import datetime, timedelta, time as dtimeonly, date
import locale
from sqlalchemy import and_, func, extract, distinct, or_, outerjoin, select
from datetime import timedelta
from tqdm import tqdm
from dateutil.relativedelta import relativedelta
from sqlalchemy import desc
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import Cell
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class UserAuto:
    def __init__(self, user_id):
        self.user_id = user_id

    def check_user_avto(self):
        return user_car.query.filter_by(user_id=self.user_id).first()

    def insert_user_avto(self, avto_name, fuel_quantity, fuel_type, distance, compensation_type, user_card):
        print(avto_name, fuel_quantity, fuel_type)

        add_record = user_car(user_id=self.user_id, auto_name=avto_name, fuel_limit=fuel_quantity, fuel_type=fuel_type,
                              distance=distance, created_at=datetime.now().date(), compensation_type=compensation_type,
                              fuel_card=user_card)
        db.session.add(add_record)
        db.session.commit()
        db.session.close()

    def update_user_avto(self, avto_name, fuel_quantity, fuel_type, distance, compensation_type, user_cards):
        # Обновляем основные данные авто (убираем fuel_card из обновления)
        user_car.query.filter_by(user_id=self.user_id).update(dict(
            auto_name=avto_name,
            fuel_limit=fuel_quantity,
            fuel_type=fuel_type,
            distance=distance,
            compensation_type=compensation_type
        ))

        # Сначала отвязываем все карты от этого пользователя
        fuel_okko_cards.query.filter_by(user_id=self.user_id).update({'user_id': None})

        # Затем привязываем выбранные карты к пользователю
        if isinstance(user_cards, list) and user_cards:
            for card_id in user_cards:
                if card_id:  # Проверяем что card_id не пустой
                    fuel_okko_cards.query.filter_by(id=int(card_id)).update({'user_id': self.user_id})

        db.session.commit()
        db.session.close()


    def add_user_fuel_month_limit(self, limit):
        check_month_limit = fuel_limits.query.filter_by(user_id=self.user_id).first()

        if check_month_limit:
            fuel_limits.query.filter_by(user_id=self.user_id).update(dict(monthly_limit=limit))
            db.session.commit()
        else:
            add_records = fuel_limits(user_id=self.user_id, monthly_limit=limit)
            db.session.add(add_records)
            db.session.commit()

    def get_user_car_info(self):
        get_user_avto_info = self.check_user_avto()
        print(get_user_avto_info)
        if get_user_avto_info:
            result = {
                'id': get_user_avto_info.id,
                'auto_name': get_user_avto_info.auto_name,
                'fuel_limit': get_user_avto_info.fuel_limit,
                'fuel_type': get_user_avto_info.fuel_type,
                'distance': get_user_avto_info.distance
            }
        else:
            result = {
                'id': 0,
                'auto_name': "Немає",
                'fuel_limit': "0",
                'fuel_type': "0",
                'distance': "0"
            }
        return result

    def add_fuel_deff(self, quantity, comment, car_info, date):
        vehicle_name = car_info['auto_name']
        fuel_type = car_info['fuel_type']
        date_refuel = date

        if comment == '':
            comment = None

        add_record = fuel_data(user_id=self.user_id, vehicle_name=vehicle_name, fuel_type=fuel_type, cost=0,
                               quantity=quantity, date_refuel=date_refuel, comments=comment)
        db.session.add(add_record)
        db.session.commit()
        db.session.close()

    def get_all_users_and_car(self):
        results = (
            db.session.query(
                users.id.label("user_id"),
                users.user_fullname.label("driver_name"),
                user_car.auto_name.label("car_brand"),
                user_car.fuel_type.label("fuel_type"),
                user_car.distance.label("km"),
                user_car.fuel_limit.label("fuel_usage"),
                fuel_limits.monthly_limit.label("monthly_norm"),
                departaments.dep_name.label("department"),
                user_car.compensation_type.label("compensation_type"),
                users.transportation.label('transportation'),
                user_car.fuel_card.label("fuel_card"),
            )
            .filter(users.display == 1)
            .outerjoin(user_car, users.id == user_car.user_id)
            .outerjoin(fuel_limits, users.id == fuel_limits.user_id)
            .outerjoin(departaments, users.user_departament == departaments.id)
            .order_by(departaments.dep_name.asc())
            .all()
        )

        fuel_data_list = []
        for row in results:
            # Перетворюємо transportation у явне значення (1 або 0)
            transportation = 1 if row.transportation else 0  # Якщо None, то 0
            fuel_data = {
                "user_id": row.user_id,
                "driver_name": row.driver_name,
                "car_brand": row.car_brand or "",
                "fuel_type": row.fuel_type,
                "compensation_type": row.compensation_type,
                "km": row.km or 0,
                "fuel_usage": row.fuel_usage or 0,
                "monthly_norm": row.monthly_norm or 0,
                "transportation": transportation,  # Явно встановлюємо 1 або 0
                "department": row.department,
                'fuel_card': row.fuel_card or ''
            }
            print(
                f"User {row.user_id}: transportation = {transportation}, raw value = {row.transportation}")  # Дебагування
            fuel_data_list.append(fuel_data)
        return fuel_data_list

    def get_comments_report_info(self, report_month: int, report_year: int):
        report_month = int(report_month)
        report_year = int(report_year)

        # Отримуємо записи з коментарями за вказаний місяць і рік
        results = (
            db.session.query(
                users.user_fullname.label("driver_name"),
                fuel_data.date_refuel.label("date"),
                fuel_data.quantity.label("fuel_spent"),
                fuel_data.comments.label("comment")
            )
            .join(users, users.id == fuel_data.user_id)
            .filter(
                extract('year', fuel_data.date_refuel) == report_year,
                extract('month', fuel_data.date_refuel) == report_month,
                fuel_data.comments.isnot(None),
                fuel_data.comments != ""  # Додатково перевіряємо, що коментар не порожній
            )
            .order_by(fuel_data.date_refuel)  # Сортуємо за датою для зручності
            .all()
        )

        comments_data_list = []
        for row in results:
            comments_data_list.append({
                "driver_name": row.driver_name,
                "date": row.date,
                "fuel_spent": round(row.fuel_spent, 1),
                "comment": str(row.comment).replace(f'|{int(row.fuel_spent)} л.', '')
            })

        return comments_data_list

    from datetime import datetime, date, timedelta
    from calendar import monthrange, calendar
    from sqlalchemy import func, extract, and_, or_, outerjoin, select
    from application import db
    from model import fuel_technoforum, users, user_car, fuel_limits, company_list, calendar_work, fuel_data

    def get_refuel_num_in_month(self, month: int, user_id: int):
        # Визначаємо початок і кінець місяця
        current_year = datetime.now().year
        start_date = datetime(current_year, month, 1)
        end_date = start_date + relativedelta(months=1)

        # Отримуємо перший запис за місяць
        result = fuel_data.query.filter(
            fuel_data.date_refuel >= start_date,
            fuel_data.date_refuel < end_date,
            fuel_data.user_id == user_id,
            fuel_data.quantity != 0
        ).order_by(fuel_data.date_refuel.asc()).first()

        if result:
            return result.quantity
        else:
            result_car = user_car.query.filter_by(user_id=user_id).first()
            if result_car:
                norm_result = result_car.distance * (result_car.fuel_limit / 100) if result_car.fuel_limit else 0
                return norm_result
            else:
                return 0
        return 0  # Повертаємо None, якщо записів немає

    def get_technoforum_report_info(self, report_month: int, report_year: int):
        report_month = int(report_month)
        report_year = int(report_year)
        last_day_to_use = monthrange(report_year, report_month)[1]
        report_month_start = datetime(report_year, report_month, 1).date()
        report_month_end = datetime(report_year, report_month, last_day_to_use).date()

        # Визначаємо попередній місяць
        prev_month = report_month - 1 if report_month > 1 else 12
        prev_year = report_year if report_month > 1 else report_year - 1
        prev_month_start = datetime(prev_year, prev_month, 1).date()

        print(f"Звітний місяць (Технофорум): {report_month_start} - {report_month_end}")
        print(f"Попередній місяць: {prev_month_start}")

        query = (
            select(
                users.id.label("user_id"),
                users.company.label("company"),
                users.user_fullname.label("driver_name"),
                fuel_technoforum.created_at,
                fuel_technoforum.refuel,
                fuel_technoforum.cost,
                fuel_technoforum.comment,
                user_car.fuel_type.label("fuel_type"),
                user_car.distance.label("distance"),
                user_car.fuel_limit.label("fuel_limit"),
                user_car.created_at.label("car_created_at"),
                fuel_technoforum.travel_days,
                fuel_technoforum.total_fuel_usage,
                fuel_technoforum.additional_fuel_usage,
            )
            .select_from(users)
            .outerjoin(fuel_technoforum,
                       and_(fuel_technoforum.user_id == users.id,
                            fuel_technoforum.created_at == report_month_start))  # Outer join для всіх працівників
            .outerjoin(user_car, users.id == user_car.user_id)
            .join(company_list, users.company == company_list.id)
            .filter(users.company == 8, user_car.fuel_type != None)
        )

        results = db.session.execute(query).all()
        technoforum_data_list = []

        for row in results:
            user_id = row.user_id
            driver_name = row.driver_name
            created_at = row.created_at if row.created_at else report_month_start
            cost = row.cost if row.cost is not None else 0.0
            comment = row.comment if row.comment else ""
            distance = row.distance or 0.0
            fuel_limit = row.fuel_limit or 0.0
            car_created_at = row.car_created_at
            travel_days = row.travel_days if row.travel_days is not None else 0
            total_fuel_usage = row.total_fuel_usage if row.total_fuel_usage is not None else 0.0
            additional_fuel_usage = row.additional_fuel_usage if row.additional_fuel_usage is not None else 0.0

            # ВИПРАВЛЕНО: Розраховуємо заправлено з транзакцій, як у Сканії
            get_fuel_used_this_month = (
                    fuel_used.query.with_entities(func.sum(fuel_used.fuel))
                    .filter_by(year=report_year, month=report_month, user_id=user_id)
                    .scalar() or 0
            )
            refuel = get_fuel_used_this_month  # Тепер береться з транзакцій!

            # Розрахунок робочих днів, якщо не збережено в таблиці
            if travel_days == 0:
                count_work_days = calendar_work.query.filter(
                    calendar_work.work_fact > 0,
                    calendar_work.user_id == user_id,
                    calendar_work.today_date.between(report_month_start, report_month_end)
                ).count()
                travel_days = count_work_days
                print(f"User {user_id}: {travel_days} робочих днів за {report_month_start} - {report_month_end}")

            day_norm = self.get_refuel_num_in_month(report_month, user_id)
            if day_norm is None:
                day_norm = 0
            monthly_norm = day_norm * travel_days

            # Отримання залишку з попереднього місяця
            prev_month_record = db.session.query(
                fuel_technoforum.refuel,
                fuel_technoforum.total_fuel_usage,
                fuel_technoforum.additional_fuel_usage
            ).filter(
                fuel_technoforum.user_id == user_id,
                fuel_technoforum.created_at == prev_month_start
            ).first()

            if prev_month_record:
                # ВИПРАВЛЕНО: Також беремо заправлено з fuel_used для попереднього місяця
                prev_fuel_used = (
                        fuel_used.query.with_entities(func.sum(fuel_used.fuel))
                        .filter_by(year=prev_year, month=prev_month, user_id=user_id)
                        .scalar() or 0
                )
                prev_refuel = prev_fuel_used  # Використовуємо дані з fuel_used
                prev_total_fuel_usage = prev_month_record.total_fuel_usage or 0.0
                prev_additional_fuel_usage = prev_month_record.additional_fuel_usage or 0.0
                prev_start_balance = self.get_technoforum_start_balance(user_id, prev_year, prev_month)
                start_balance = prev_start_balance + prev_refuel - prev_total_fuel_usage - prev_additional_fuel_usage
                print(f"User {user_id}: Попередній залишок = {start_balance}")
            else:
                start_balance = 0.0  # Якщо немає запису за попередній місяць, початковий баланс = 0

            # ВИПРАВЛЕНО: Якщо total_fuel_usage не збережено в БД, рахуємо як день_норма * дні
            if total_fuel_usage == 0.0:
                total_fuel_usage = day_norm * travel_days

            end_balance = start_balance + refuel - total_fuel_usage - additional_fuel_usage

            user_fuel_cards = fuel_okko_cards.query.filter_by(user_id=user_id).all()
            transactions = []

            if user_fuel_cards:
                # Отримуємо номери всіх карток користувача
                card_numbers = [card.card_num for card in user_fuel_cards if card.card_num]

                if card_numbers:
                    transactions_query = db.session.query(
                        fuel_okko_transactions.id,
                        fuel_okko_transactions.trans_date.label("date"),
                        fuel_okko_transactions.fuel_volume.label("amount"),
                        fuel_okko_transactions.card_num.label("card_num"),
                        fuel_okko_transactions.amnt_trans.label("amnt_trans"),
                        fuel_okko_transactions.discount.label("discount"),
                        fuel_okko_transactions.trans_type.label("trans_type")
                    ).filter(
                        fuel_okko_transactions.card_num.in_(card_numbers),  # Шукаємо по всіх картках
                        extract('year', fuel_okko_transactions.trans_date) == report_year,
                        extract('month', fuel_okko_transactions.trans_date) == report_month
                    ).all()

                    transactions = [
                        {
                            "id": t.id,
                            "date": t.date.strftime('%d.%m.%y') if t.date else '',
                            "amount": (
                                round(t.amount / 1000, 1) if t.trans_type == 774
                                else -round(t.amount / 1000, 1) if t.trans_type == 775
                                else round(t.amount / 1000, 1)
                            ),
                            "price": (
                                round((t.amnt_trans - (t.discount or 0)) / 100, 1) if t.trans_type == 774
                                else -round((t.amnt_trans - (t.discount or 0)) / 100, 1) if t.trans_type == 775
                                else round((t.amnt_trans - (t.discount or 0)) / 100, 1)
                            ),
                            "card_num": t.card_num,  # Додаємо номер картки
                        } for t in transactions_query
                    ]

            technoforum_data_list.append({
                "user_id": user_id,
                "driver_name": driver_name,
                "created_at": created_at,
                "refuel": round(refuel, 1),  # Тепер це значення з fuel_used!
                "refuel_details": f"З таблиці fuel_used: {round(refuel, 1)}л (транзакцій: {len(transactions)})",
                "cost": round(cost, 2),
                "comment": comment,
                "fuel_type": row.fuel_type,
                "distance": distance,
                "day_norm": round(day_norm, 1),
                "travel_days": travel_days,
                "start_balance": round(start_balance, 1),
                "end_balance": round(end_balance, 1),
                "total_fuel_usage": round(total_fuel_usage, 1),
                "additional_fuel_usage": round(additional_fuel_usage, 1),
                "transactions": transactions
            })

        print(f"Technoforum data list: {technoforum_data_list}")
        return technoforum_data_list

    def get_technoforum_start_balance(self, user_id, year, month):
        """Обчислює start_balance для заданого користувача і місяця на основі останнього запису."""
        month_start = datetime(year, month, 1).date()

        # Знаходимо останній запис перед вибраним місяцем
        last_record = db.session.query(
            fuel_technoforum.created_at,
            fuel_technoforum.refuel,
            fuel_technoforum.total_fuel_usage,
            fuel_technoforum.additional_fuel_usage
        ).filter(
            fuel_technoforum.user_id == user_id,
            fuel_technoforum.created_at < month_start
        ).order_by(fuel_technoforum.created_at.desc()).first()

        if last_record:
            # Якщо запис є, беремо дані останнього місяця
            last_created_at = last_record.created_at
            last_refuel = last_record.refuel or 0.0
            last_total_fuel_usage = last_record.total_fuel_usage or 0.0
            last_additional_fuel_usage = last_record.additional_fuel_usage or 0.0

            # Визначаємо місяць і рік останнього запису
            last_year = last_created_at.year
            last_month = last_created_at.month

            # Рекурсивно отримуємо start_balance для цього місяця
            prev_start_balance = self.get_technoforum_start_balance(user_id, last_year, last_month) if (
                        last_year < year or (last_year == year and last_month < month)) else 0.0

            # Розрахунок end_balance останнього запису, який стає start_balance для поточного місяця
            start_balance = prev_start_balance + last_refuel - last_total_fuel_usage - last_additional_fuel_usage
            print(f"User {user_id}: Last record {last_created_at}, Start balance for {year}-{month} = {start_balance}")
        else:
            # Якщо записів до цього місяця немає, повертаємо 0
            start_balance = 0.0
            print(f"User {user_id}: No records before {year}-{month}, Start balance = 0")

        return round(start_balance, 1)

    def get_cash_fuel_report_info(self, report_month: int, report_year: int):
        report_month = int(report_month)
        report_year = int(report_year)
        import calendar
        # Отримуємо останній день звітного місяця
        last_day_to_use = calendar.monthrange(report_year, report_month)[1]

        # Форматуємо початок і кінець звітного місяця
        report_month_start = datetime(report_year, report_month, 1).date()
        report_month_end = datetime(report_year, report_month, last_day_to_use).date()

        print(f"Звітний місяць для готівки: {report_month_start} - {report_month_end}")

        # Форматуємо початок звітного місяця для порівняння у MySQL
        report_month_start_str = f"{report_year}-{report_month:02d}"

        # Отримуємо дані за допомогою SQLAlchemy
        results = (
            db.session.query(
                users.id.label("user_id"),
                users.company.label("company"),
                users.user_fullname.label("driver_name"),
                user_car.fuel_type.label("fuel_type"),
                func.sum(fuel_data.quantity).label("total_quantity"),
                func.count(fuel_data.id).label("fuel_count"),
                func.min(fuel_data.date_refuel).label("first_refuel_date"),
                company_list.company_name.label("company_name"),
                user_car.distance.label("distance"),
                user_car.fuel_limit.label("fuel_limit"),
                user_car.created_at.label("car_created_at"),
            )
            .outerjoin(user_car, users.id == user_car.user_id)
            .outerjoin(fuel_data, users.id == fuel_data.user_id)
            .join(company_list, users.company == company_list.id)
            .filter(user_car.compensation_type == 'cash')  # Змінено фільтр на 'cash'
            .filter(user_car.id.isnot(None))
            .filter(
                or_(
                    func.date_format(fuel_data.date_refuel, '%Y-%m') == report_month_start_str,
                    func.date_format(user_car.created_at, '%Y-%m') == report_month_start_str
                )
            )
            .group_by(
                users.id,
                users.user_fullname,
                user_car.auto_name,
                user_car.fuel_type,
                user_car.distance,
                user_car.fuel_limit,
                company_list.company_name,
                user_car.created_at
            )
            .all()
        )

        cash_fuel_data_list = []

        for row in results:
            user_id = row.user_id
            driver_name = row.driver_name
            distance = row.distance
            fuel_limit = row.fuel_limit

            # Розрахунок кількості робочих днів
            count_work_days = calendar_work.query.filter(
                calendar_work.work_fact > 0,
                calendar_work.user_id == user_id,
                calendar_work.today_date.between(report_month_start, report_month_end)
            ).count()

            day_norm = self.get_refuel_num_in_month(report_month, user_id)#distance * (fuel_limit / 100) if fuel_limit else 0
            if day_norm is None:
                day_norm = 0
            monthly_norm = day_norm * count_work_days

            # Отримуємо витрати за готівку за місяць
            total_fuel_usage = (
                    db.session.query(func.sum(fuel_data.quantity))
                    .filter(
                        fuel_data.user_id == user_id,
                        fuel_data.comments.is_(None),
                        extract('year', fuel_data.date_refuel) == report_year,
                        extract('month', fuel_data.date_refuel) == report_month
                    )
                    .scalar() or 0
            )

            travel_days = (
                    db.session.query(func.count(distinct(fuel_data.date_refuel)))
                    .filter(
                        fuel_data.user_id == user_id,
                        extract('year', fuel_data.date_refuel) == report_year,
                        extract('month', fuel_data.date_refuel) == report_month
                    )
                    .scalar() or 0
            )

            cash_fuel_data_list.append({
                "user_id": user_id,
                "driver_name": driver_name,
                "distance": distance,
                "fuel_type": row.fuel_type,
                "day_norm": round(day_norm, 1),
                "travel_days": int(travel_days),
                "total_fuel_usage": round(total_fuel_usage, 1)
            })

        return cash_fuel_data_list

    def get_fuel_report_info(self, report_month: int, report_year: int):
        report_month = int(report_month)
        report_year = int(report_year)
        import calendar
        from datetime import datetime, timedelta
        from sqlalchemy import func, extract, distinct, or_, and_

        if today().month == report_month and today().year == report_year:
            sync_result, sync_message = sync_fuel_used_with_okko_transactions(report_year, report_month)
            print(sync_message), sync_result
        # Отримуємо останній день звітного місяця
        last_day_to_use = calendar.monthrange(report_year, report_month)[1]

        # Форматуємо початок і кінець звітного місяця
        report_month_start = datetime(report_year, report_month, 1).date()
        report_month_end = datetime(report_year, report_month, last_day_to_use).date()

        print(f"Звітний місяць: {report_month_start} - {report_month_end}")

        # Форматуємо початок звітного місяця для порівняння у MySQL
        report_month_start_str = f"{report_year}-{report_month:02d}"

        # Отримуємо дані за допомогою SQLAlchemy (убрали fuel_card з запиту)
        results = (
            db.session.query(
                users.id.label("user_id"),
                users.company.label("company"),
                users.user_fullname.label("driver_name"),
                user_car.fuel_type.label("fuel_type"),
                fuel_limits.monthly_limit.label("monthly_limit"),
                func.sum(fuel_data.quantity).label("total_quantity"),
                func.count(fuel_data.id).label("fuel_count"),
                func.min(fuel_data.date_refuel).label("first_refuel_date"),
                company_list.company_name.label("company_name"),
                user_car.distance.label("distance"),
                user_car.fuel_limit.label("fuel_limit"),
                user_car.created_at.label("car_created_at"),
            )
            .outerjoin(user_car, users.id == user_car.user_id)
            .outerjoin(fuel_limits, users.id == fuel_limits.user_id)
            .outerjoin(fuel_data, users.id == fuel_data.user_id)
            .join(company_list, users.company == company_list.id)
            .filter(user_car.compensation_type == 'card')
            .filter(user_car.id.isnot(None), users.company != 8)
            .filter(
                or_(
                    func.date_format(fuel_data.date_refuel, '%Y-%m') == report_month_start_str,
                    func.date_format(user_car.created_at, '%Y-%m') == report_month_start_str
                )
            )
            .group_by(
                users.id,
                users.user_fullname,
                user_car.auto_name,
                user_car.fuel_type,
                user_car.distance,
                user_car.fuel_type,
                user_car.fuel_limit,
                fuel_limits.monthly_limit,
                company_list.company_name,
                user_car.created_at,
            )
            .all()
        )

        fuel_data_list = []

        for row in results:
            user_id = row.user_id
            driver_name = row.driver_name
            distance = row.distance
            fuel_limit = row.fuel_limit
            car_created_at = row.car_created_at
            count_work_days = calendar_work.query.filter(
                calendar_work.work_fact > 0,
                calendar_work.user_id == user_id,
                calendar_work.today_date.between(report_month_start, report_month_end)
            ).count()

            day_norm = self.get_refuel_num_in_month(report_month,
                                                    user_id)  # distance * (fuel_limit / 100) if fuel_limit else 0
            print(day_norm, count_work_days)
            if day_norm is None:
                day_norm = 0
            monthly_norm = day_norm * count_work_days

            def calculate_balance_up_to_month(target_year, target_month):
                start_balance = 0
                first_fuel_year = db.session.query(func.min(extract('year', fuel_data.date_refuel))).filter(
                    fuel_data.user_id == user_id
                ).scalar()
                if car_created_at:
                    start_date = car_created_at
                else:
                    start_date = datetime(int(first_fuel_year), 1, 1) if first_fuel_year else datetime(target_year, 1,
                                                                                                       1)

                current_year = start_date.year
                current_month = start_date.month

                while (current_year < target_year) or (current_year == target_year and current_month < target_month):
                    month_start = datetime(current_year, current_month, 1)
                    next_month_start = datetime(current_year, current_month + 1, 1) if current_month < 12 else datetime(
                        current_year + 1, 1, 1
                    )
                    month_end = next_month_start - timedelta(days=1)

                    count_work_days = calendar_work.query.filter(
                        calendar_work.work_fact > 0,
                        calendar_work.user_id == user_id,
                        calendar_work.today_date.between(month_start, month_end)
                    ).count()
                    day_norm = self.get_refuel_num_in_month(report_month,
                                                            user_id)  # distance * (fuel_limit / 100) if fuel_limit else 0
                    if day_norm is None:
                        day_norm = 0
                    monthly_norm = day_norm * count_work_days

                    refueled = (
                            fuel_used.query.with_entities(func.sum(fuel_used.fuel))
                            .filter_by(year=current_year, month=current_month, user_id=user_id)
                            .scalar() or 0
                    )
                    total_fuel = (
                            db.session.query(func.sum(fuel_data.quantity))
                            .filter(
                                fuel_data.user_id == user_id,
                                extract('year', fuel_data.date_refuel) == current_year,
                                extract('month', fuel_data.date_refuel) == current_month,
                                fuel_data.comments.is_(None)  # Тільки без коментарів
                            )
                            .scalar() or 0
                    )
                    additional_fuel = (
                            db.session.query(func.sum(fuel_data.quantity))
                            .filter(
                                fuel_data.user_id == user_id,
                                extract('year', fuel_data.date_refuel) == current_year,
                                extract('month', fuel_data.date_refuel) == current_month,
                                fuel_data.comments.isnot(None)  # Тільки з коментарями
                            )
                            .scalar() or 0
                    )

                    end_balance = start_balance + refueled - total_fuel - additional_fuel
                    # Логування для перевірки
                    print(f"User: {user_id}, Year: {current_year}, Month: {current_month}, "
                          f"Start: {start_balance}, Refueled: {refueled}, Total: {total_fuel}, "
                          f"Additional: {additional_fuel}, End: {end_balance}")
                    start_balance = end_balance

                    current_month += 1
                    if current_month > 12:
                        current_month = 1
                        current_year += 1

                return start_balance

            start_balance = calculate_balance_up_to_month(report_year, report_month)

            get_fuel_used_this_month = (
                    fuel_used.query.with_entities(func.sum(fuel_used.fuel))
                    .filter_by(year=report_year, month=report_month, user_id=user_id)
                    .scalar() or 0
            )
            total_fuel_usage = (
                    db.session.query(func.sum(fuel_data.quantity))
                    .filter(
                        fuel_data.user_id == user_id,
                        fuel_data.comments.is_(None),  # Тільки без коментарів
                        extract('year', fuel_data.date_refuel) == report_year,
                        extract('month', fuel_data.date_refuel) == report_month
                    )
                    .scalar() or 0
            )
            additional_fuel_usage = (
                    db.session.query(func.sum(fuel_data.quantity))
                    .filter(
                        fuel_data.user_id == user_id,
                        extract('year', fuel_data.date_refuel) == report_year,
                        extract('month', fuel_data.date_refuel) == report_month,
                        fuel_data.comments.isnot(None)  # Тільки з коментарями
                    )
                    .scalar() or 0
            )

            end_balance = start_balance + get_fuel_used_this_month - total_fuel_usage - additional_fuel_usage

            get_fuel_used_until_report_month = (
                    fuel_used.query.with_entities(func.sum(fuel_used.fuel))
                    .filter(
                        fuel_used.user_id == user_id,
                        or_(
                            fuel_used.year < report_year,
                            and_(fuel_used.year == report_year, fuel_used.month <= report_month)
                        )
                    )
                    .scalar() or 0
            )
            months_with_records_until_report_month = (
                    db.session.query(
                        func.count(distinct(
                            extract('year', fuel_data.date_refuel) * 12 + extract('month', fuel_data.date_refuel)
                        ))
                    )
                    .filter(
                        fuel_data.user_id == user_id,
                        fuel_data.date_refuel <= report_month_end
                    )
                    .scalar() or 0
            )
            accumulated_norm_until_report_month = months_with_records_until_report_month * monthly_norm
            delta = accumulated_norm_until_report_month - get_fuel_used_until_report_month

            travel_days = (
                    db.session.query(func.count(distinct(fuel_data.date_refuel)))
                    .filter(
                        fuel_data.user_id == user_id,
                        extract('year', fuel_data.date_refuel) == report_year,
                        extract('month', fuel_data.date_refuel) == report_month
                    )
                    .scalar() or 0
            )

            # Нова логіка отримання транзакцій для всіх карток користувача
            user_fuel_cards = fuel_okko_cards.query.filter_by(user_id=user_id).all()
            transactions = []

            if user_fuel_cards:
                # Отримуємо номери всіх карток користувача
                card_numbers = [card.card_num for card in user_fuel_cards if card.card_num]

                if card_numbers:
                    transactions_query = db.session.query(
                        fuel_okko_transactions.id,
                        fuel_okko_transactions.trans_date.label("date"),
                        fuel_okko_transactions.fuel_volume.label("amount"),
                        fuel_okko_transactions.card_num.label("card_num"),
                        fuel_okko_transactions.amnt_trans.label("amnt_trans"),
                        fuel_okko_transactions.discount.label("discount"),
                        fuel_okko_transactions.trans_type.label("trans_type")
                    ).filter(
                        fuel_okko_transactions.card_num.in_(card_numbers),  # Шукаємо по всіх картках
                        extract('year', fuel_okko_transactions.trans_date) == report_year,
                        extract('month', fuel_okko_transactions.trans_date) == report_month
                    ).all()

                    transactions = [
                        {
                            "id": t.id,
                            "date": t.date.strftime('%d.%m.%y') if t.date else '',
                            "amount": (
                                round(t.amount / 1000, 1) if t.trans_type == 774
                                else -round(t.amount / 1000, 1) if t.trans_type == 775
                                else round(t.amount / 1000, 1)
                            ),
                            "price": (
                                round((t.amnt_trans - (t.discount or 0)) / 100, 1) if t.trans_type == 774
                                else -round((t.amnt_trans - (t.discount or 0)) / 100, 1) if t.trans_type == 775
                                else round((t.amnt_trans - (t.discount or 0)) / 100, 1)
                            ),
                            "card_num": t.card_num,  # Додаємо номер картки
                        } for t in transactions_query
                    ]

            # Форматування чисел із пробілами як роздільниками тисяч
            fuel_data_list.append({
                "user_id": user_id,
                "driver_name": driver_name,
                "monthly_norm": round(monthly_norm, 1),
                "start_balance": round(start_balance, 1),
                "refueled_this_month": round(get_fuel_used_this_month, 1),
                "refuel_details": f"З таблиці fuel_used: {round(get_fuel_used_this_month, 1)}л (транзакцій: {len(transactions)})",
                "additional_fuel_usage": round(additional_fuel_usage, 1),
                "total_fuel_usage": round(total_fuel_usage, 1),
                "end_balance": round(end_balance, 1),
                "fuel_type": row.fuel_type,
                "delta": round(delta, 1),
                "day_norm": round(day_norm, 1),
                "travel_days": int(travel_days),
                "company": row.company_name,
                "distance": distance if distance else 0,
                "transactions": transactions  # Тепер включає транзакції з усіх карток користувача
            })

        return fuel_data_list

    def update_user_fuel_used_data(self, user_id, fuel, month, year):
        check_in_db = fuel_used.query.filter_by(user_id=user_id, month=month, year=year)
        if check_in_db.first():
            check_in_db.update(dict(fuel=fuel))
            db.session.commit()
        else:
            add_records = fuel_used(
                user_id=user_id,
                month=month,
                year=year,
                fuel=fuel
            )
            db.session.add(add_records)
            db.session.commit()

    def generate_fuel_report_pdf(self, report_month: int, report_year: int):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # Реєстрація шрифту з підтримкою кирилиці
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))  # Переконайся, що шлях до шрифту правильний

        # Отримуємо дані
        fuel_data_list = self.get_fuel_report_info(report_month, report_year)
        comments_data_list = self.get_comments_report_info(report_month, report_year)

        # Конвертуємо місяць у текст
        month_names = {
            1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень", 6: "Червень",
            7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"
        }
        month_name = month_names[report_month]

        # Налаштування PDF з альбомною орієнтацією
        filename = f"fuel_report_{month_name}_{report_year}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
        elements = []

        # Стилі
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Title'],
            fontName='DejaVuSans',
            fontSize=16,
            alignment=1,  # Центрування
            spaceAfter=12
        )
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontName='DejaVuSans',
            fontSize=14,
            alignment=1,
            spaceAfter=10
        )
        cell_style = ParagraphStyle(
            'Cell',
            fontName='DejaVuSans',
            fontSize=9,
            alignment=1,  # Центрування
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

        # Заголовок першої таблиці
        header_title = f"Облік витрат пального по паливним карткам - {month_name} {report_year}"
        elements.append(Paragraph(header_title, title_style))

        # Дані для таблиці паливних карток
        headers = [
            "ПІБ", "км.", "Тип палива", "Залишок на початок, л", "Заправлено, л",
            "Норма на день, л", "Днів поїздок", "Витрати за місяць, л",
            "Додаткові витрати, л", "Залишок на кінець, л"
        ]
        table_data = [[Paragraph(h, header_style) for h in headers]]

        # Заповнення даних
        total_refueled = 0
        for data in fuel_data_list:
            row = [
                Paragraph(data["driver_name"], cell_style),
                Paragraph(str(data["distance"]), cell_style),
                Paragraph(data["fuel_type"], cell_style),
                Paragraph(str(data["start_balance"]), cell_style),
                Paragraph(str(data["refueled_this_month"]), cell_style),
                Paragraph(str(data["day_norm"]), cell_style),
                Paragraph(str(data["travel_days"]), cell_style),
                Paragraph(str(data["total_fuel_usage"]), cell_style),
                Paragraph(str(data["additional_fuel_usage"]), cell_style),
                Paragraph(str(data["end_balance"]), cell_style)
            ]
            table_data.append(row)
            total_refueled += float(data["refueled_this_month"])

        # Підсумковий рядок
        summary_row = [
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph(f"Всього: {total_refueled:.1f} л", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style)
        ]
        table_data.append(summary_row)

        # Створення таблиці
        table = Table(table_data, colWidths=[120, 50, 60, 80, 80, 70, 60, 80, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWHEIGHT', (0, 0), (-1, 0), 40),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(table)

        # Відступ
        elements.append(Spacer(1, 20))

        # Заголовок для додаткових витрат
        comments_title = f"Додаткові витрати - {month_name} {report_year}"
        elements.append(Paragraph(comments_title, subtitle_style))

        # Дані для таблиці додаткових витрат
        comments_headers = ["ПІБ", "Дата", "Витрата, л", "Коментар"]
        comments_table_data = [[Paragraph(h, header_style) for h in comments_headers]]

        for data in comments_data_list:
            row = [
                Paragraph(data["driver_name"], cell_style),
                Paragraph(data["date"].strftime("%Y-%m-%d"), cell_style),
                Paragraph(str(data["fuel_spent"]), cell_style),
                Paragraph(data["comment"], cell_style)
            ]
            comments_table_data.append(row)

        # Створення таблиці додаткових витрат
        comments_table = Table(comments_table_data, colWidths=[120, 90, 70, 250])
        comments_table.setStyle(TableStyle([
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
        ]))
        elements.append(comments_table)

        # Генерація PDF
        doc.build(elements)
        return filename

    def generate_fuel_cash_report_pdf(self, report_month: int, report_year: int):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from io import BytesIO
        from datetime import date, timedelta
        from calendar import monthrange
        from model import fuel_price  # Імпортуємо модель

        # Реєстрація шрифту з підтримкою кирилиці
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))

        # Отримуємо дані
        cash_fuel_data_list = self.get_cash_fuel_report_info(report_month, report_year)

        # Додаємо логіку для середньої вартості
        for data in cash_fuel_data_list:
            fuel_type = data["fuel_type"]
            today = date.today()
            last_5_days = [today - timedelta(days=i) for i in range(5)]

            # Визначаємо, які 5 днів брати
            if report_year < today.year or (report_year == today.year and report_month < today.month):
                last_day_of_month = date(report_year, report_month, monthrange(report_year, report_month)[1])
                last_5_days = [last_day_of_month - timedelta(days=i) for i in range(5)]

            prices = fuel_price.query.filter(
                fuel_price.created_at.in_(last_5_days),
                fuel_price.fuel_type == fuel_type
            ).all()

            if prices:
                avg_price = sum(p.price for p in prices) / len(prices)
            else:
                avg_price = 0.0

            data['avg_fuel_price'] = round(avg_price, 2)  # Округляємо до цілого числа
            data['total_cost'] = int(avg_price * data['total_fuel_usage']) if avg_price else 0  # Округляємо до цілого

        # Конвертуємо місяць у текст
        month_names = {
            1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень", 6: "Червень",
            7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"
        }
        month_name = month_names[report_month]

        # Налаштування PDF з альбомною орієнтацією у пам’яті
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
            alignment=1,  # Центрування
            spaceAfter=12
        )
        cell_style = ParagraphStyle(
            'Cell',
            fontName='DejaVuSans',
            fontSize=9,
            alignment=1,  # Центрування
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
            alignment=1,  # Центрування
            leading=12,
            textColor=colors.black,
            fontWeight='bold'  # Жирний шрифт для підсумку
        )

        # Заголовок таблиці
        header_title = f"Компенсація витрат палива за готівку - {month_name} {report_year}"
        elements.append(Paragraph(header_title, title_style))

        # Дані для таблиці
        headers = ["ПІБ", "км", "Тип палива", "Норма в день, л", "Днів поїздок", "Витрати за місяць, л",
                   "Середня вартість, грн", "Сума, грн"]
        table_data = [[Paragraph(h, header_style) for h in headers]]

        # Заповнення даних
        total_cost_sum = 0
        for data in cash_fuel_data_list:
            # Форматуємо значення як цілі числа з пробілами
            formatted_avg_price = "{:,}".format(data['avg_fuel_price']).replace(",", " ")
            formatted_total_cost = "{:,}".format(data['total_cost']).replace(",", " ")
            row = [
                Paragraph(data["driver_name"], cell_style),
                Paragraph(str(data["distance"]), cell_style),
                Paragraph(data["fuel_type"], cell_style),
                Paragraph(str(data["day_norm"]), cell_style),
                Paragraph(str(data["travel_days"]), cell_style),
                Paragraph(str(data["total_fuel_usage"]), cell_style),
                Paragraph(formatted_avg_price, cell_style),
                Paragraph(formatted_total_cost, cell_style)
            ]
            table_data.append(row)
            total_cost_sum += data['total_cost']  # Додаємо до загальної суми

        # Додаємо рядок із загальною сумою
        formatted_total_sum = "{:,}".format(int(total_cost_sum)).replace(",", " ")
        total_row = [
            Paragraph("", cell_style),  # Порожні клітинки для перших 7 колонок
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("Загальна сума:", total_style),
            Paragraph(formatted_total_sum, total_style)
        ]
        table_data.append(total_row)

        # Створення таблиці
        table = Table(table_data, colWidths=[140, 60, 80, 90, 70, 90, 90, 90])  # Додано ширину для нових колонок
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWHEIGHT', (0, 0), (-1, 0), 40),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),  # Сірий фон для рядка з сумою
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(table)

        # Генерація PDF у пам’яті
        doc.build(elements)
        buffer.seek(0)  # Повертаємо позицію на початок буфера
        return buffer  # Повертаємо BytesIO із вмістом PDF

def diff_vacation_calc(profile_id, year_now):
    get_vacation_info = vacation.query.filter_by(years=year_now, user_id=profile_id).first()
    get_before_vacation_days_sum = db.session.query(func.sum(vacation.count_days)).filter(
        and_(
            vacation.years < year_now,
            vacation.user_id == profile_id
        )
    ).scalar() or 0

    # Якщо year_now передається як datetime.date, отримайте рік як int
    if isinstance(year_now, date):
        year_now = year_now.year

    # Тепер це безпечно використовувати для обчислень
    last_day_of_last_year = date(year_now - 1, 12, 31)

    count_vacation_days = get_vacation_info.count_days if get_vacation_info else 0
    get_count_used_vacation_before = calendar_work.query.filter(
        and_(calendar_work.reason == 'vacation', calendar_work.user_id == profile_id,
             calendar_work.today_date <= last_day_of_last_year)).count()

    count_before_vacation_days = get_before_vacation_days_sum - get_count_used_vacation_before

    get_used_money = calendar_work.query.filter(
        and_(calendar_work.reason == 'dripicons-card', calendar_work.user_id == profile_id,
             calendar_work.today_date < datetime.now())).count()

    get_count_user_vacation_calendar = calendar_work.query.filter(and_(
        calendar_work.user_id == profile_id,
        calendar_work.reason == 'vacation',
        calendar_work.today_date >= f'{year_now}-01-01',
        calendar_work.today_date <= f'{year_now}-12-31'
    )).count()

    # Логіка обчислення diff_vacation
    if count_before_vacation_days > get_used_money:
        count_before_vacation_days -= get_used_money
    else:
        count_vacation_days -= (get_used_money - count_before_vacation_days)
        count_before_vacation_days = 0

    if count_before_vacation_days >= get_count_user_vacation_calendar:
        count_before_vacation_days -= get_count_user_vacation_calendar
    else:
        diff_new = get_count_user_vacation_calendar - count_before_vacation_days
        count_vacation_days -= diff_new
        count_before_vacation_days = 0

    count_canceled_days = vacations_canceled.query.with_entities(func.sum(vacations_canceled.count_days)).filter(
        vacations_canceled.user_id==profile_id, vacations_canceled.year<=year_now
    ).scalar() or 0

    diff_vacation = count_vacation_days + count_before_vacation_days - count_canceled_days

    return diff_vacation, count_vacation_days, count_before_vacation_days

class Users:
    def __init__(self, user_id):
        self.user_id = user_id

    def get_user_info(self):
        get_user = users.query.filter_by(id=self.user_id).first()
        departament_info = departaments.query.filter_by(id=get_user.user_departament).first()
        user_info = {
            'id': get_user.id,
            'email': get_user.user_email,
            'full_name': get_user.user_fullname,
            'user_avatar': get_user.user_avatar,
            'user_access': get_user.user_access,
            'user_departament_id': departament_info.id if departament_info else None,
            'user_departament': departament_info.dep_name if departament_info else None,
            'departament_name': departaments.query.filter_by(id=get_user.user_departament).first().dep_name,
            'user_phone_1': get_user.phone_num_one,
            'user_phone_2': get_user.phone_num_two,
            'birthdate': get_user.birthdate.strftime('%Y-%m-%d') if get_user.birthdate else None,
            'join_date': get_user.join_date.strftime('%Y-%m-%d') if get_user.join_date else None,
            'company_name': get_user.company,
            'company_str_name': company_list.query.filter_by(id=get_user.company).first().company_name,
            'gender': get_user.gender,
            'user_age': 23#datetime.now() - get_user.birthdate
        }
        return user_info

    def get_user_info_from_id(self, user_id):
        get_user = users.query.filter_by(id=user_id).first()
        departament_info = departaments.query.filter_by(id=get_user.user_departament).first()
        user_info = {
            'id': get_user.id,
            'email': get_user.user_email,
            'full_name': get_user.user_fullname,
            'user_access': get_user.user_access,
            'user_departament_id': departament_info.id if departament_info else None,
            'user_departament': departament_info.dep_name if departament_info else None,
            'departament_name': departaments.query.filter_by(id=get_user.user_departament).first().dep_name,
            'user_phone_1': get_user.phone_num_one,
            'user_phone_2': get_user.phone_num_two,
            'birthdate': get_user.birthdate.strftime('%Y-%m-%d') if get_user.birthdate else None,
            'join_date': get_user.join_date.strftime('%Y-%m-%d') if get_user.join_date else None,
            'company_name': get_user.company,
            'gender': get_user.gender,
            'user_age': 23#datetime.now() - get_user.birthdate
        }
        return user_info

    def get_list_companyes(self):
        get_list = company_list.query.all()
        company_full_list = []
        for company in get_list:
            company_full_list.append({
                'id': company.id,
                'name': company.company_name
            })
        return company_full_list

    def get_list_users(self):
        get_users = users.query.filter_by(display=1).order_by(users.user_departament.desc()).all()
        list_users = []
        for user in get_users:
            list_users.append({
                'id': user.id,
                'user_avatar': user.user_avatar,
                'user_name': user.user_fullname,
                'departament': departaments.query.filter_by(id=user.user_departament).first().dep_name,
                'phone': user.phone_num_one,
                'birth': user.birthdate,
                'join': user.join_date,
                'gender': user.gender,
                'display': user.display
            })
        return list_users

    def get_list_users_departements(self):
        # Отримати всі user_ids з user_head для певного head_id
        user_ids_from_user_head = [users_head.user_id for users_head in
                                   user_head.query.filter_by(head_id=self.user_id).all()]

        # Отримати всі user_ids з users, де user_departament входить в users_departament.dep_id
        # і users_departament.access_level дорівнює 6, а також users_departament.user_id дорівнює self.user_id
        user_ids_from_users = [user.id for user in users.query.join(users_departament, and_(
            users.user_departament == users_departament.dep_id,
            users_departament.access_level == 6,
            users_departament.user_id == self.user_id
        )).all()]

        # Об'єднати списки user_ids_from_user_head та user_ids_from_users
        user_ids = user_ids_from_user_head + user_ids_from_users

        # Видалити дублікати, якщо такі є
        user_ids = list(set(user_ids))
        unic_ids = []
        list_users = []
        for user in user_ids:
            if user not in unic_ids:
                user_info = users.query.filter_by(id=user).first()
                if user_info.display == 1:
                    list_users.append({
                        'id': user_info.id,
                        'user_avatar': user_info.user_avatar,
                        'user_name': user_info.user_fullname,
                        'departament': departaments.query.filter_by(id=user_info.user_departament).first().dep_name,
                        'phone': user_info.phone_num_one,
                        'birth': user_info.birthdate,
                        'join': user_info.join_date,
                        'gender': user_info.gender,
                        'display': user_info.display
                    })
                unic_ids.append(user)
        users_info = sorted(list_users, key=lambda x: (x['departament']))
        return users_info

    def get_list_users_by_access(self):
        get_users = users.query.filter_by(display=1).order_by(users.user_departament.desc()).all()
        list_users = []
        for user in get_users:
            list_users.append({
                'id': user.id,
                'user_avatar': user.user_avatar,
                'user_name': user.user_fullname,
                'departament': departaments.query.filter_by(id=user.user_departament).first().dep_name,
                'phone': user.phone_num_one,
                'birth': user.birthdate,
                'join': user.join_date,
                'gender': user.gender,
                'display': user.display
            })
        return list_users

    def get_all_list_users(self):
        get_users = users.query.filter_by(display=0).order_by(users.user_departament.desc()).all()
        list_users = []
        for user in get_users:
            get_remove_info = absens_from_work.query.filter_by(user_id=user.id).first()
            list_users.append({
                'id': user.id,
                'user_avatar': user.user_avatar,
                'user_name': user.user_fullname,
                'departament': departaments.query.filter_by(id=user.user_departament).first().dep_name,
                'phone': user.phone_num_one,
                'birth': user.birthdate,
                'join': user.join_date,
                'gender': user.gender,
                'display': user.display,
                'remove_info': get_remove_info.remove_reason if get_remove_info else 'Коментарів немає'
            })
        return list_users

    def get_mob_list_users(self):
        get_users = users.query.filter_by(display=2).order_by(users.user_departament.desc()).all()
        list_users = []
        for user in get_users:
            get_remove_info = absens_from_work.query.filter_by(user_id=user.id).first()
            list_users.append({
                'id': user.id,
                'user_avatar': user.user_avatar,
                'user_name': user.user_fullname,
                'departament': departaments.query.filter_by(id=user.user_departament).first().dep_name,
                'phone': user.phone_num_one,
                'birth': user.birthdate,
                'join': user.join_date,
                'gender': user.gender,
                'display': user.display,
                'remove_info': get_remove_info.remove_reason if get_remove_info else 'Коментарів немає'
            })
        return list_users

    def get_users_calendar_info(self, user_id, date_start, date_end):
        # Встановлення локалі
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        # Отримання списку відділів користувача
        dep_id_list = users_departament.query.with_entities(users_departament.dep_id).filter(
            users_departament.user_id == user_id,
            users_departament.access_level >= 1
        ).all()
        dep_id_list = [ud.dep_id for ud in dep_id_list]

        # Визначення, чи є користувач керівником
        user_in_head = user_head.query.filter_by(head_id=user_id).first() is not None

        # Отримання списку користувачів
        if user_id != 11:
            get_user_list = users.query.filter(users.user_departament.in_(dep_id_list), users.display == 1).all()
        else:
            get_user_list = users.query.all()

        # Створення словника для оптимізації запитів на відсутності
        all_absences = absens_from_work.query.filter(
            absens_from_work.user_id.in_([user.id for user in get_user_list])
        ).all()
        absences_dict = {absence.user_id: absence for absence in all_absences}

        info_list = []
        for user in get_user_list:
            # Отримання інформації про робочі години, планові та фактичні
            work_hours_data = db.session.query(
                func.sum(calendar_work.work_time).label("plan_hours"),
                func.sum(calendar_work.work_fact).label("fact_hours")
            ).filter(
                calendar_work.user_id == user.id,
                calendar_work.today_date >= date_start,
                calendar_work.today_date <= date_end
            ).first()

            plan_hours = work_hours_data.plan_hours or 0
            fact_hours = work_hours_data.fact_hours or 0
            diff_hours = fact_hours - plan_hours

            user_info = {
                'user_id': user.id,
                'user_departament': user.user_departament,
                'user_dep_head': user_in_head,
                'user_name': user.user_fullname,
                'birthday': str(user.birthdate),
                'count_day_in_work': 0,  # Потрібна логіка для обчислення
                'plan_work': self.format_number(plan_hours),
                'fact_work': self.format_number(fact_hours),
                'diff_work': self.format_number(diff_hours),
                'calendar': []  # Додавання деталей за кожен день потребує додаткової логіки
            }

            current_date = date_start
            check_user_in_remove = absens_from_work.query.filter_by(user_id=user.id).first()
            while current_date <= date_end:
                calendar_entry = calendar_work.query.filter_by(user_id=user.id, today_date=current_date).first()

                if calendar_entry:
                    get_comment = work_comments.query.filter_by(records_id=calendar_entry.id, user_id=user.id).order_by(
                        work_comments.id.desc()).first()

                    # Дані з calendar_entry, якщо запис існує
                    day_info = {
                        'date': current_date,
                        'user_id': user.id,
                        'work_time': self.format_number(calendar_entry.work_time),
                        'work_fact': self.format_number(calendar_entry.work_fact),
                        'work_status': 'white-text' if calendar_entry.work_status == 2 and calendar_entry.reason == 'work' else 'original-color',
                        'difference': (calendar_entry.work_time - calendar_entry.work_fact) * (
                            -1) if calendar_entry.work_fact is not None else None,
                        'reason': calendar_entry.reason if calendar_entry.reason else None,
                        'weekend': 0,
                        'comment': get_comment.comment if get_comment else 'Коментарів немає',
                        'remove': check_user_in_remove,
                        'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                        'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                    }
                else:
                    # '-' і None, якщо запису немає
                    day_info = {
                        'date': current_date,
                        'user_id': user.id,
                        'work_status': 1,
                        'work_time': '-',
                        'work_fact': None,
                        'difference': None,
                        'reason': None,
                        'weekend': 1,
                        'comment': 'Коментарів немає',
                        'remove': check_user_in_remove,
                        'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                        'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                    }

                user_info['calendar'].append(day_info)
                current_date += timedelta(days=1)

            if user_info['user_departament'] != 'Адміністратори':
                info_list.append(user_info)

        # Сортування і повернення інформації
        users_info = sorted(info_list, key=lambda x: (x['user_departament'], x['user_name']))
        return users_info

    @staticmethod
    def format_number(value):
        if value is None:
            return 0
        # Перетворюємо значення на float
        float_value = float(value)
        # Перевіряємо, чи дробова частина дорівнює нулю
        if float_value.is_integer():
            return int(float_value)
        else:
            return round(float_value, 2)

    def get_users_calendar_info1(self, user_id, date_start, date_end):
        get_user_departaments = users_departament.query.filter(users_departament.user_id==user_id,
                            users_departament.access_level>=1).all()
        dep_id_list = [ud.dep_id for ud in get_user_departaments]

        if user_id != 11:
            get_user_list = users.query.filter(users.user_departament.in_(dep_id_list)).all()

        else:
            get_user_list = users.query.all()

        # Встановлення локалі для отримання назви днів тижня українською мовою
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        info_list = []
        for user in tqdm(get_user_list):
            count_work_day = calendar_work.query.filter(and_(calendar_work.user_id == user.id,
                                                             calendar_work.today_date >= date_start,
                                                             calendar_work.today_date <= date_end,
                                                             calendar_work.work_fact>0)).count()
            if count_work_day != 0:

                departament_name = departaments.query.filter_by(id=user.user_departament).first()
                check_user_in_remove = absens_from_work.query.filter_by(user_id=user.id).first()

                plan_hours, fact_hours = db.session.query(
                    func.sum(calendar_work.work_time),
                    func.sum(calendar_work.work_fact)
                ).filter(
                    calendar_work.user_id == user.id,
                    calendar_work.today_date.between(date_start, date_end)
                ).first()

                if fact_hours is None:
                    fact_hours = 0

                if fact_hours and plan_hours:
                    diff_hours = fact_hours - plan_hours
                else:
                    diff_hours = 0
                    fact_hours = 0
                    plan_hours = 0

                user_head_leader = user_head.query.filter_by(head_id=user.id).first()
                user_head_worker = user_head_leader
                if user_head_worker:
                    user_head_worker = user_head_worker.head_id

                user_info = {
                    'user_id': user.id,
                    'sort': departament_name.sort_num,
                    'user_departament': departament_name.dep_name if departament_name else 'Не вибраний',
                    'user_dep_head': user_head_leader,
                    'num_in_list': user.user_num_list,
                    'user_leader': user.id if user_head_leader else user_head_worker,
                    'user_name': user.user_fullname,
                    'birthday': str(user.birthdate),
                    'calendar': [],
                    'count_day_in_work': int(count_work_day),
                    'plan_work': self.format_number(plan_hours),
                    'fact_work': self.format_number(fact_hours),
                    'diff_work': self.format_number(diff_hours),
                }

                from collections import defaultdict
                # Цикл для кожного дня
                current_date = date_start
                calendar_entries = db.session.query(
                    calendar_work.id,
                    calendar_work.today_date,
                    calendar_work.user_id,
                    calendar_work.work_time,
                    calendar_work.work_status,
                    calendar_work.work_fact,
                    calendar_work.reason
                ).filter(
                    calendar_work.user_id == user.id,
                    calendar_work.today_date.between(date_start, date_end)
                ).all()

                # Перетворюємо у список словників
                calendar_list = [
                    {
                        "id": entry.id,
                        "today_date": entry.today_date,
                        "user_id": entry.user_id,
                        "work_time": entry.work_time,
                        "work_status": entry.work_status,
                        "work_fact": entry.work_fact,
                        "reason": entry.reason
                    }
                    for entry in calendar_entries
                ]

                # Опціонально: створюємо словник для швидкого доступу за датою
                calendar_dict = {entry["today_date"].strftime('%Y-%m-%d'): entry for entry in calendar_list}

                #айді всіх записів користувача
                ids = [entry["id"] for entry in calendar_dict.values()]

                get_comments = work_comments.query.filter(
                    work_comments.records_id.in_(ids),
                    work_comments.user_id == user.id
                ).order_by(work_comments.id.desc()).all()

                # Створюємо список коментарів у вигляді словників
                comments_list = [
                    {
                        "id": comment.id,
                        "records_id": comment.records_id,
                        "user_id": comment.user_id,
                        "comment": comment.comment,
                        "dt_event": comment.dt_event,
                        "user_add_comment": comment.user_add_comment
                    }
                    for comment in get_comments
                ]

                while current_date <= date_end:
                    current_date_str = current_date.strftime('%Y-%m-%d')

                    specific_entry = calendar_dict.get(current_date_str)
                    if specific_entry:

                        # Об'єднуємо всі коментарі в один рядок
                        filtered_comments = [comment for comment in get_comments if
                                             comment.records_id == specific_entry['id']]

                        # Об'єднуємо всі коментарі у один рядок
                        all_comments = '; '.join([comment.comment for comment in
                                                  filtered_comments]) if filtered_comments else 'Коментарів немає'

                        # Дані з calendar_entry, якщо запис існує
                        day_info = {
                            'date': current_date,
                            'user_id': user.id,
                            'work_time': self.format_number(specific_entry['work_time']),
                            'work_fact': self.format_number(specific_entry['work_fact']),
                            'work_status': 'white-text' if specific_entry['work_status'] == 2 and specific_entry['reason'] == 'work' else 'original-color',
                            'difference': (specific_entry['work_time'] - specific_entry['work_fact']) * (-1) if specific_entry['work_fact'] is not None else None,
                            'reason': specific_entry['reason'] if specific_entry['reason'] else None,
                            'weekend': 0,
                            'comment': all_comments,
                            'remove': check_user_in_remove,
                            'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                            'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                        }
                    else:
                        # '-' і None, якщо запису немає
                        day_info = {
                            'date': current_date,
                            'user_id': user.id,
                            'work_status': 1,
                            'work_time': '-',
                            'work_fact': None,
                            'difference': None,
                            'reason': None,
                            'weekend': 1,
                            'comment': 'Коментарів немає',
                            'remove': check_user_in_remove,
                            'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                            'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                        }

                    user_info['calendar'].append(day_info)
                    current_date += timedelta(days=1)

                if user_info['user_departament'] != 'Адміністратори':
                    info_list.append(user_info)
        users_info = sorted(info_list, key=lambda x: (x['sort'], x['num_in_list']))
        return users_info


    def get_users_calendar_info_optimized(self, user_id, date_start, date_end):
        get_user_departaments = users_departament.query.filter(users_departament.user_id==user_id,
                            users_departament.access_level>=1).all()
        dep_id_list = [ud.dep_id for ud in get_user_departaments]

        if user_id != 11:
            get_user_list = users.query.filter(users.user_departament.in_(dep_id_list)).all()

        else:
            get_user_list = users.query.all()


        # Встановлення локалі для отримання назви днів тижня українською мовою
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        info_list = []
        for user in tqdm(get_user_list):
            check_user_in_remove = absens_from_work.query.filter_by(user_id=user.id).first()
            count_work_day = calendar_work.query.filter(and_(calendar_work.user_id == user.id,
                                                             calendar_work.today_date >= date_start,
                                                             calendar_work.today_date <= date_end)).count()
            if count_work_day != 0:

                departament_name = departaments.query.filter_by(id=user.user_departament).first()

                count_days = calendar_work.query.filter(calendar_work.user_id == user.id,
                    calendar_work.today_date >= date_start,
                    calendar_work.today_date <= date_end).count()
                plan_hours = db.session.query(func.sum(calendar_work.work_time)).filter(
                    calendar_work.user_id == user.id,
                    calendar_work.today_date >= date_start,
                    calendar_work.today_date <= date_end
                ).scalar()

                fact_hours = db.session.query(func.sum(calendar_work.work_fact)).filter(
                    calendar_work.user_id == user.id,
                    calendar_work.today_date >= date_start,
                    calendar_work.today_date <= date_end
                ).scalar()
                if fact_hours is None:
                    fact_hours = 0

                if fact_hours and plan_hours:
                    diff_hours = fact_hours - plan_hours
                else:
                    diff_hours = 0
                    fact_hours = 0
                    plan_hours = 0

                user_head_leader = user_head.query.filter_by(head_id=user.id).first()
                user_head_worker = user_head_leader
                if user_head_worker:
                    user_head_worker = user_head_worker.head_id

                user_info = {
                    'user_id': user.id,
                    'sort': departament_name.sort_num,
                    'user_departament': departament_name.dep_name if departament_name else 'Не вибраний',
                    'user_dep_head': user_head_leader,
                    'num_in_list': user.user_num_list,
                    'user_leader': user.id if user_head_leader else user_head_worker,
                    'user_name': user.user_fullname,
                    'birthday': str(user.birthdate),
                    'calendar': [],
                    'count_day_in_work': int(count_days),
                    'plan_work': self.format_number(plan_hours),
                    'fact_work': self.format_number(fact_hours),
                    'diff_work': self.format_number(diff_hours),
                }

                from collections import defaultdict
                # Цикл для кожного дня
                current_date = date_start
                calendar_entries = {entry.today_date: entry for entry in calendar_work.query.filter(
                    calendar_work.user_id == user.id,
                    calendar_work.today_date.between(date_start, date_end)
                ).all()}
                print(calendar_entries)
                while current_date <= date_end:
                    calendar_entry = calendar_work.query.filter_by(user_id=user.id, today_date=current_date).first()

                    if calendar_entry:
                        get_comments = work_comments.query.filter_by(records_id=calendar_entry.id,
                                                                     user_id=user.id).order_by(
                            work_comments.id.desc()).all()

                        # Об'єднуємо всі коментарі в один рядок
                        all_comments = '; '.join(
                            [comment.comment for comment in get_comments]) if get_comments else 'Коментарів немає'

                        # Дані з calendar_entry, якщо запис існує
                        day_info = {
                            'date': current_date,
                            'user_id': user.id,
                            'work_time': self.format_number(calendar_entry.work_time),
                            'work_fact': self.format_number(calendar_entry.work_fact),
                            'work_status': 'white-text' if calendar_entry.work_status == 2 and calendar_entry.reason == 'work' else 'original-color',
                            'difference': (calendar_entry.work_time - calendar_entry.work_fact) * (-1) if calendar_entry.work_fact is not None else None,
                            'reason': calendar_entry.reason if calendar_entry.reason else None,
                            'weekend': 0,
                            'comment': all_comments,
                            'remove': check_user_in_remove,
                            'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                            'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                        }
                    else:
                        # '-' і None, якщо запису немає
                        day_info = {
                            'date': current_date,
                            'user_id': user.id,
                            'work_status': 1,
                            'work_time': '-',
                            'work_fact': None,
                            'difference': None,
                            'reason': None,
                            'weekend': 1,
                            'comment': 'Коментарів немає',
                            'remove': check_user_in_remove,
                            'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                            'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                        }

                    user_info['calendar'].append(day_info)
                    current_date += timedelta(days=1)

                if user_info['user_departament'] != 'Адміністратори':
                    info_list.append(user_info)
        users_info = sorted(info_list, key=lambda x: (x['sort'], x['num_in_list']))
        return users_info

    def get_users_calendar_info2(self, user_id, date_start, date_end):
        # Використовуємо join для фільтрації по департаменту
        get_user_departaments = db.session.query(users_departament).filter(
            users_departament.user_id == user_id,
            users_departament.access_level >= 1
        ).all()

        dep_id_list = [ud.dep_id for ud in get_user_departaments]

        # Визначаємо список користувачів
        if user_id != 11:
            get_user_list = db.session.query(users).join(
                users_departament, users.user_departament == users_departament.dep_id
            ).filter(
                users.user_departament.in_(dep_id_list),
                users.display == 1
            ).all()
        else:
            get_user_list = users.query.all()

        # Встановлення локалі для отримання назв днів тижня українською мовою
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        # Запит для всіх користувачів та їх відсутностей
        absens_users = db.session.query(absens_from_work).filter(
            absens_from_work.user_id.in_([user.id for user in get_user_list])
        ).all()

        absens_dict = {absens.user_id: absens for absens in absens_users}

        # Запити для календаря та коментарів
        calendar_data = db.session.query(
            calendar_work.user_id,
            calendar_work.today_date,
            calendar_work.work_time,
            calendar_work.work_fact,
            calendar_work.work_status,
            calendar_work.reason,
            work_comments.comment
        ).join(work_comments, work_comments.records_id == calendar_work.id, isouter=True).filter(
            calendar_work.today_date >= date_start,
            calendar_work.today_date <= date_end,
            calendar_work.user_id.in_([user.id for user in get_user_list])
        ).all()

        calendar_dict = {}
        for entry in calendar_data:
            user_calendar = calendar_dict.setdefault(entry.user_id, {})
            user_calendar[entry.today_date] = {
                'work_time': entry.work_time,
                'work_fact': entry.work_fact,
                'work_status': entry.work_status,
                'reason': entry.reason,
                'comment': entry.comment
            }

        # Тепер формуємо дані
        info_list = []
        for user in tqdm(get_user_list):
            departament_name = departaments.query.filter_by(id=user.user_departament).first()
            user_head_leader = user_head.query.filter_by(head_id=user.id).first()
            user_head_worker = user_head.query.filter_by(user_id=user.id).first()

            if user_head_worker:
                user_head_worker = user_head_worker.head_id

            # Підсумки по роботі
            count_days = db.session.query(func.count(calendar_work.id)).filter(
                calendar_work.user_id == user.id,
                calendar_work.today_date >= date_start,
                calendar_work.today_date <= date_end
            ).scalar()

            plan_hours = db.session.query(func.sum(calendar_work.work_time)).filter(
                calendar_work.user_id == user.id,
                calendar_work.today_date >= date_start,
                calendar_work.today_date <= date_end
            ).scalar()

            fact_hours = db.session.query(func.sum(calendar_work.work_fact)).filter(
                calendar_work.user_id == user.id,
                calendar_work.today_date >= date_start,
                calendar_work.today_date <= date_end
            ).scalar()

            if fact_hours is None:
                fact_hours = 0

            if fact_hours and plan_hours:
                diff_hours = fact_hours - plan_hours
            else:
                diff_hours = 0
                fact_hours = 0
                plan_hours = 0

            user_info = {
                'user_id': user.id,
                'sort': departament_name.sort_num,
                'user_departament': departament_name.dep_name if departament_name else 'Не вибраний',
                'user_dep_head': user_head_leader,
                'num_in_list': user.user_num_list,
                'user_leader': user.id if user_head_leader else user_head_worker,
                'user_name': user.user_fullname,
                'birthday': str(user.birthdate),
                'calendar': [],
                'count_day_in_work': int(count_days),
                'plan_work': self.format_number(plan_hours),
                'fact_work': self.format_number(fact_hours),
                'diff_work': self.format_number(diff_hours),
            }

            current_date = date_start
            while current_date <= date_end:
                # Використовуємо підготовлені дані для кожного дня
                day_info = {
                    'date': current_date,
                    'user_id': user.id,
                    'work_status': 1,
                    'work_time': '-',
                    'work_fact': None,
                    'difference': None,
                    'reason': None,
                    'weekend': 1,
                    'comment': 'Коментарів немає',
                    'remove': absens_dict.get(user.id),
                    'date_remove': absens_dict.get(user.id).date_remove if absens_dict.get(user.id) else False,
                    'comm_remove': absens_dict.get(user.id).remove_reason if absens_dict.get(user.id) else False
                }

                # Оновлюємо інформацію для дня, якщо є
                if user.id in calendar_dict and current_date in calendar_dict[user.id]:
                    calendar_entry = calendar_dict[user.id][current_date]
                    day_info.update({
                        'work_time': self.format_number(calendar_entry['work_time']),
                        'work_fact': self.format_number(calendar_entry['work_fact']),
                        'work_status': 'white-text' if calendar_entry['work_status'] == 2 and calendar_entry[
                            'reason'] == 'work' else 'original-color',
                        'difference': (calendar_entry['work_time'] - calendar_entry['work_fact']) * (-1) if
                        calendar_entry['work_fact'] is not None else None,
                        'reason': calendar_entry['reason'] if calendar_entry['reason'] else None,
                        'comment': calendar_entry['comment'] if calendar_entry['comment'] else 'Коментарів немає',
                    })

                user_info['calendar'].append(day_info)
                current_date += timedelta(days=1)
            if user_info['user_departament'] != 'Адміністратори':
                info_list.append(user_info)

        users_info = sorted(info_list, key=lambda x: (x['sort'], x['num_in_list']))
        return users_info

    def update_files_script(self, user_id, date_start, date_end):
        # Отримання відділів та списку користувачів у одному запиті
        get_user_departaments = db.session.query(users_departament.dep_id).filter(
            users_departament.user_id == user_id,
            users_departament.access_level >= 1
        ).subquery()

        if user_id != 11:
            get_user_list = db.session.query(users).join(get_user_departaments, users.user_departament == get_user_departaments.c.dep_id).filter(
                users.display == 1
            ).all()
        else:
            get_user_list = db.session.query(users).all()

        # Встановлення локалі для отримання назви днів тижня українською мовою
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        # Отримання всіх записів в одному запиті
        calendar_work_data = db.session.query(
            calendar_work.user_id,
            calendar_work.today_date,
            func.sum(calendar_work.work_time).label('plan_hours'),
            func.sum(calendar_work.work_fact).label('fact_hours'),
            func.count(calendar_work.id).label('count_days')
        ).filter(
            calendar_work.today_date >= date_start,
            calendar_work.today_date <= date_end
        ).group_by(
            calendar_work.user_id,
            calendar_work.today_date
        ).all()

        # Оптимізоване отримання коментарів
        work_comments_data = db.session.query(
            work_comments.records_id,
            work_comments.user_id,
            work_comments.comment
        ).order_by(work_comments.id.desc()).all()

        # Оптимізоване отримання відділів
        departaments_data = {d.id: d.dep_name for d in db.session.query(departaments).all()}

        # Оптимізоване отримання керівників
        user_heads_data = {u.id: u.head_id for u in db.session.query(user_head).all()}

        # Оптимізоване отримання записів про відсутність
        absens_data = {a.user_id: a for a in db.session.query(absens_from_work).all()}

        info_list = []
        for user in tqdm(get_user_list):
            # Отримання записів календаря для кожного користувача
            user_calendar_entries = [entry for entry in calendar_work_data if entry.user_id == user.id]
            user_comments = {comment.records_id: comment.comment for comment in work_comments_data if comment.user_id == user.id}

            departament_name = departaments_data.get(user.user_departament, 'Не вибраний')
            user_head_leader = user_heads_data.get(user.id, None)
            user_head_worker = user_heads_data.get(user.id, None)

            user_info = {
                'user_id': user.id,
                'sort': user.user_departament,
                'user_departament': departament_name,
                'user_dep_head': user_head_leader,
                'num_in_list': user.user_num_list,
                'user_leader': user.id if user_head_leader else user_head_worker,
                'user_name': user.user_fullname,
                'birthday': str(user.birthdate),
                'calendar': [],
                'count_day_in_work': sum(entry.count_days for entry in user_calendar_entries),
                'plan_work': self.format_number(sum(entry.plan_hours for entry in user_calendar_entries)),
                'fact_work': self.format_number(sum(entry.fact_hours for entry in user_calendar_entries)),
                'diff_work': self.format_number(sum(entry.fact_hours - entry.plan_hours for entry in user_calendar_entries)),
            }

            # Цикл для кожного дня
            current_date = date_start
            while current_date <= date_end:
                calendar_entry = calendar_work.query.filter_by(user_id=user.id, today_date=current_date).first()

                if calendar_entry:
                    get_comments = work_comments.query.filter_by(records_id=calendar_entry.id,
                                                                 user_id=user.id).order_by(
                        work_comments.id.desc()).all()

                    # Об'єднуємо всі коментарі в один рядок
                    all_comments = '; '.join(
                        [comment.comment for comment in get_comments]) if get_comments else 'Коментарів немає'

                    # Дані з calendar_entry, якщо запис існує
                    day_info = {
                        'date': current_date,
                        'user_id': user.id,
                        'work_time': self.format_number(calendar_entry.work_time),
                        'work_fact': self.format_number(calendar_entry.work_fact),
                        'work_status': 'white-text' if calendar_entry.work_status == 2 and calendar_entry.reason == 'work' else 'original-color',
                        'difference': (calendar_entry.work_time - calendar_entry.work_fact) * (
                            -1) if calendar_entry.work_fact is not None else None,
                        'reason': calendar_entry.reason if calendar_entry.reason else None,
                        'weekend': 0,
                        'comment': all_comments,
                        'remove': check_user_in_remove,
                        'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                        'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                    }
                else:
                    # '-' і None, якщо запису немає
                    day_info = {
                        'date': current_date,
                        'user_id': user.id,
                        'work_status': 1,
                        'work_time': '-',
                        'work_fact': None,
                        'difference': None,
                        'reason': None,
                        'weekend': 1,
                        'comment': 'Коментарів немає',
                        'remove': check_user_in_remove,
                        'date_remove': check_user_in_remove.date_remove if check_user_in_remove else False,
                        'comm_remove': check_user_in_remove.remove_reason if check_user_in_remove else False
                    }

                user_info['calendar'].append(day_info)
                current_date += timedelta(days=1)

            if user_info['user_departament'] != 'Адміністратори':
                info_list.append(user_info)

        users_info = sorted(info_list, key=lambda x: (x['sort'], x['num_in_list']))
        return users_info

    def calculate_diff_vacation(self, profile_id, year_now):
        get_vacation_info = vacation.query.filter_by(years=year_now, user_id=profile_id).first()
        get_before_vacation_days_sum = db.session.query(func.sum(vacation.count_days)).filter(
            and_(
                vacation.years < year_now,
                vacation.user_id == profile_id
            )
        ).scalar() or 0

        # Якщо year_now передається як datetime.date, отримайте рік як int
        if isinstance(year_now, date):
            year_now = year_now.year

        # Тепер це безпечно використовувати для обчислень
        last_day_of_last_year = date(year_now - 1, 12, 31)

        count_vacation_days = get_vacation_info.count_days if get_vacation_info else 0
        get_count_used_vacation_before = calendar_work.query.filter(
            and_(calendar_work.reason == 'vacation', calendar_work.user_id == profile_id,
                 calendar_work.today_date <= last_day_of_last_year)).count()

        count_before_vacation_days = get_before_vacation_days_sum - get_count_used_vacation_before

        get_used_money = calendar_work.query.filter(
            and_(calendar_work.reason == 'dripicons-card', calendar_work.user_id == profile_id,
                 calendar_work.today_date < datetime.now())).count()

        get_count_user_vacation_calendar = calendar_work.query.filter(and_(
            calendar_work.user_id == profile_id,
            calendar_work.reason == 'vacation',
            calendar_work.today_date >= f'{year_now}-01-01',
            calendar_work.today_date <= f'{year_now}-12-31'
        )).count()

        # Логіка обчислення diff_vacation
        if count_before_vacation_days > get_used_money:
            count_before_vacation_days -= get_used_money
        else:
            count_vacation_days -= (get_used_money - count_before_vacation_days)
            count_before_vacation_days = 0

        if count_before_vacation_days >= get_count_user_vacation_calendar:
            count_before_vacation_days -= get_count_user_vacation_calendar
        else:
            diff_new = get_count_user_vacation_calendar - count_before_vacation_days
            count_vacation_days -= diff_new
            count_before_vacation_days = 0

        diff_vacation = count_vacation_days + count_before_vacation_days

        return diff_vacation, count_vacation_days, count_before_vacation_days


    def get_users_calendar_full_info(self, departament, companies, date_start, date_end):
        get_user_list = users.query.filter_by(display=1)
        if len(companies) > 0:
            get_user_list = get_user_list.filter(users.company.in_(companies))

        get_user_departaments = users_departament.query.filter(and_(users_departament.user_id==self.user_id,
                                                                    users_departament.access_level>=1)).all()
        print(get_user_departaments)
        for user_depart in get_user_departaments:
            if user_depart.dep_id not in departament:
                departament.append(user_depart.dep_id)

        print('departaments', departament)
        if departament and int(self.user_id) != 11:
            get_user_list = get_user_list.filter(users.user_departament.in_(departament))
        print(get_user_list)

        import locale
        # Встановлення української локалі
        locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')

        info_list = []
        for user in get_user_list.all():
            # Для отримання суми та кількості записів де work_time > 0
            get_plan_sum_and_count = db.session.query(
                func.sum(calendar_work.work_time),
                func.count()
            ).filter(
                and_(calendar_work.user_id == user.id, calendar_work.work_time > 0,
                     calendar_work.today_date >= date_start, calendar_work.today_date <= date_end)
            ).one()

            # Для отримання суми та кількості записів де work_fact > 0
            get_fact_sum_and_count = db.session.query(
                func.sum(calendar_work.work_fact),
                func.count()
            ).filter(
                and_(calendar_work.user_id == user.id, calendar_work.work_fact > 0,
                     calendar_work.today_date >= date_start, calendar_work.today_date <= date_end)
            ).one()

            # Розділення результатів
            plan_hours, plan_days = get_plan_sum_and_count
            fact_hours, fact_days = get_fact_sum_and_count

            if fact_hours and plan_hours:
                diff_hours = fact_hours - plan_hours
            else:
                diff_hours = 0
                fact_hours = 0
                plan_hours = 0

            if fact_days and plan_days:
                diff_days = fact_days - plan_days
            else:
                diff_days = 0
                fact_days = 0
                plan_days = 0

            user_info = self.get_user_info_from_id(user.id)

            user_join_datetime = datetime.strptime(user_info['join_date'], '%Y-%m-%d')
            user_age_datetime = datetime.strptime(user_info['birthdate'], '%Y-%m-%d')
            # Обчислити різницю у роках і днях для join_difference
            join_delta = relativedelta(datetime.now(), user_join_datetime)
            join_years = join_delta.years
            join_month = join_delta.months
            join_days = join_delta.days

            # Обчислити різницю у роках і днях для age_difference
            age_delta = relativedelta(datetime.now(), user_age_datetime)
            age_years = age_delta.years


            get_dodatcovo_hours = calendar_work.query.with_entities(func.sum(calendar_work.work_fact)).filter(
                and_(calendar_work.user_id == user.id, calendar_work.reason == 'dripicons-jewel',
                     calendar_work.today_date >= date_start, calendar_work.today_date <= date_end)).scalar()
            get_dodatcovo_hours_diff = calendar_work.query.with_entities(func.sum(calendar_work.work_time)).filter(
                and_(calendar_work.user_id == user.id, calendar_work.reason == 'dripicons-jewel',
                     calendar_work.today_date >= date_start, calendar_work.today_date <= date_end)).scalar()
            dodatcovo_hours = 0
            if get_dodatcovo_hours:
                dodatcovo_hours = get_dodatcovo_hours - get_dodatcovo_hours_diff

            this_year = datetime.now().year
            total_vacation_days = db.session.query(func.sum(vacation.count_days)). \
                filter(vacation.user_id == user.id). \
                scalar()
            vacation_used = calendar_work.query.filter_by(user_id=user.id, reason='vacation').count()
            if total_vacation_days:
                count_vacation_this_year = total_vacation_days
            else:
                count_vacation_this_year = 0

            user_dep_name = departaments.query.filter_by(id=user.user_departament).first()
            user_head_leader = user_head.query.filter_by(head_id=user.id).first()
            user_head_worker = user_head.query.filter_by(user_id=user.id).first()
            if user_head_worker:
                user_head_worker = user_head_worker.head_id

            if user_dep_name.dep_name != 'Адміністратори':
                info_list.append({
                    'user_dep_head': user_head_leader,
                    'num_in_list': user.user_num_list,
                    'user_leader': user.id if user_head_leader else user_head_worker,
                    'sort': user_dep_name.sort_num,
                    'user_id': user.id,
                    'user_name': user.user_fullname,
                    'user_dep_name': user_dep_name.dep_name,
                    'dodatcovo_one': calendar_work.query.filter(and_(calendar_work.user_id == user.id, calendar_work.today_date >= date_start, calendar_work.today_date <= date_end, calendar_work.reason=='dripicons-jewel')).count(),
                    'dodatcovo_two': dodatcovo_hours,
                    'otgul': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-flag', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'likarnjaniy': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-medical', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'vidrjad': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-suitcase', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'progul': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-cross', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'vidpustka_used': vacation_used,
                    'vidpustka_diff': self.calculate_diff_vacation(user.id, datetime.now().date())[0],
                    'nezyasovano': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-cross', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    #todo: кількість перепрацьованих
                    'pererobka': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-jewel', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'vidprosivsya': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-time-reverse', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'mymoney': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-hourglass', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),
                    'compensation': calendar_work.query.filter(calendar_work.user_id==user.id, calendar_work.reason=='dripicons-card', calendar_work.today_date >= date_start, calendar_work.today_date <= date_end).count(),


                    'prisutnist_plan': int(plan_days),
                    'prisutnist_fact': int(fact_days),
                    'prisutnist_differens': int(diff_days),

                    'fond_plan': int(plan_hours),
                    'fond_fact': int(fact_hours),
                    'fond_diff': int(diff_hours),

                    'user_departament': company_list.query.filter_by(id=user_info['company_name']).first().company_name if company_list.query.filter_by(id=user_info['company_name']).first() else 'Не вказаний',
                    'user_starg': f"{join_years} роки {join_month} місяці {join_days} днів",
                    'user_age': f"{age_years} р."
                })
        users_info = sorted(info_list, key=lambda x: (x['sort'], x['num_in_list']))
        return users_info

    def get_all_users(self):
        get_list = users.query.all()
        list_users = []
        for user in get_list:
            list_users.append({
                'id': user.id,
                'username': user.user_fullname
            })
        return list_users

    def get_premission(self, profile_id):
        get_premission_user = users_departament.query.filter_by(user_id=profile_id).all()
        department_access = {dep.dep_id: dep.access_level for dep in get_premission_user}
        return department_access

    def get_all_vacations_year_info(self):
        get_vacations_all = vacation.query.filter_by(user_id=self.user_id).order_by(desc(vacation.years)).all()

        vacations_list = []
        for vac in get_vacations_all:
            # Отримуємо рік та кількість днів відпустки
            year = vac.years
            count_days = vac.count_days

            # Отримуємо кількість скасованих днів відпустки для цього року
            count_vacation_canceled_days = 0
            get_count_vacation_canceled_days = vacations_canceled.query.filter_by(year=year,
                                                                                  user_id=self.user_id).first()
            if get_count_vacation_canceled_days:
                count_vacation_canceled_days = get_count_vacation_canceled_days.count_days

            # Додаємо інформацію до списку
            vacations_list.append({
                "year": year,
                "count_days": count_days,
                "canceled_days": count_vacation_canceled_days
            })

        return vacations_list


def get_month_start_end(year, month):
    # Початок місяця
    start_date = datetime(year, month, 1)

    # Отримання наступного місяця
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    # Останній день місяця - це день перед першим днем наступного місяця
    end_date = next_month - timedelta(days=1)

    return start_date, end_date

def get_calendar_data(user_id, reasons, thisyear):
    from collections import defaultdict
    this_year = thisyear
    start_of_year = datetime(this_year, 1, 1)
    end_of_year = datetime(this_year, 12, 31)

    result_list = []
    sum_year_data = {}  # Для суми за рік
    aggregated_data = defaultdict(lambda: [0] * 12)
    reason_list = ['dripicons-jewel', 'dripicons-return', 'vacation', 'dripicons-medical', 'dripicons-suitcase',
                   'dripicons-pulse', 'dripicons-cross', 'dripicons-time-reverse', 'dripicons-home']


    print(start_of_year, end_of_year)
    vacation_count_days = 0
    for reason_name in reason_list:
        if reason_name == 'vacation':
            get_count_days = vacation.query.filter_by(years=this_year, user_id=user_id).first()
            if get_count_days:
                vacation_count_days = get_count_days.count_days

        sum_year = calendar_work.query.filter(
            calendar_work.user_id == user_id,
            calendar_work.reason == reason_name,
            calendar_work.today_date >= start_of_year,
            calendar_work.today_date <= end_of_year
        ).count()
        if reason_name == 'vacation':
            sum_year_data[reason_name] = f'{sum_year}/{diff_vacation_calc(user_id, this_year)[0]}'
        else:
            sum_year_data[reason_name] = sum_year  # Зберігаємо суму за рік для кожної причини

        for i in range(1, 13):
            start_month, end_month = get_month_start_end(this_year, i)
            count_work_days = calendar_work.query.filter(and_(calendar_work.user_id==user_id,
                                                              calendar_work.reason==reason_name,
                                                              calendar_work.today_date>=start_month,
                                                              calendar_work.today_date<=end_month)).count()

            result_list.append([reason_name, i, count_work_days])

    # Ініціалізація структур даних
    monthly_plan_hours = [0] * 12
    monthly_fact_hours = [0] * 12
    monthly_diff_hours = [0] * 12
    year_plan_hours = 0
    year_fact_hours = 0

    for i in range(1, 13):
        start_month, end_month = get_month_start_end(this_year, i)

        # Плановані години за місяць
        month_plan_hours = db.session.query(func.sum(calendar_work.work_time)).filter(
            calendar_work.user_id == user_id,
            calendar_work.today_date >= start_month,
            calendar_work.today_date <= end_month
        ).scalar() or 0

        # Фактичні години за місяць
        month_fact_hours = db.session.query(func.sum(calendar_work.work_fact)).filter(
            calendar_work.user_id == user_id,
            calendar_work.today_date >= start_month,
            calendar_work.today_date <= end_month
        ).scalar() or 0

        # Різниця годин за місяць
        month_diff_hours = month_fact_hours - month_plan_hours

        # Зберігання місячних даних
        monthly_plan_hours[i - 1] = month_plan_hours
        monthly_fact_hours[i - 1] = month_fact_hours
        monthly_diff_hours[i - 1] = month_diff_hours

        # Агрегування річних даних
        year_plan_hours += month_plan_hours
        year_fact_hours += month_fact_hours

    year_diff_hours = year_fact_hours - year_plan_hours

    for item in result_list:
        reason_code, month, count = item
        aggregated_data[reason_code][month - 1] = count

    data_for_table = []
    for reason, reason_code in zip(reasons, reason_list):
        data_row = [reason, sum_year_data[reason_code]]  # Додаємо суму за рік як другий елемент
        data_row += aggregated_data[reason_code]  # Додаємо дані по місяцях
        data_for_table.append(data_row)
    data_for_table += [
        ["План годин", year_plan_hours] + monthly_plan_hours,
        ["Факт годин", year_fact_hours] + monthly_fact_hours,
        ["Різниця годин", year_diff_hours] + monthly_diff_hours
    ]
    return data_for_table


def get_employees_data(year, user_id):
    from sqlalchemy import func, case

    if user_id == 11:
        get_list_departament_of_edit_access = [dep.id for dep in
                                               departaments.query.with_entities(departaments.id).all()]
    else:
        get_list_departament_of_edit_access = [ud.dep_id for ud in users_departament.query.with_entities(
            users_departament.dep_id).filter_by(access_level=6, user_id=user_id).all()]

    print(get_list_departament_of_edit_access)

    # Основний запит до бази даних
    user_list = (
        users.query
        .join(departaments, users.user_departament == departaments.id)  # Приєднуємо департаменти
        .join(calendar_work, calendar_work.user_id == users.id, isouter=True)  # Приєднуємо calendar_work
        .join(vacation, vacation.user_id == users.id, isouter=True)  # Приєднуємо vacation
        .join(vacations_canceled,
              (vacations_canceled.user_id == users.id) &
              (vacations_canceled.year == year),
              isouter=True)
        .filter(calendar_work.today_date >= f'2023-01-01')  # Фільтруємо записи з поточного року
        .filter(users.display == 1)  # Фільтруємо записи з поточного року
        .filter(departaments.id.in_(get_list_departament_of_edit_access))
        .filter(calendar_work.today_date <= datetime.now().date())  # Фільтруємо записи до кінця року
        .add_columns(
            users.id.label('user_id'),
            departaments.sort_num.label('depart_num_list'),
            users.user_num_list.label('user_num_list'),
            users.user_fullname.label('full_name'),
            departaments.dep_name.label('department'),
            departaments.dep_name.label('department'),
            func.count(
                func.distinct(
                    case(
                        (calendar_work.reason == 'vacation', calendar_work.id),
                        else_=None
                    )
                )
            ).label('vacation_count'),  # Кількість відпусток
            func.count(
                func.distinct(
                    case(
                        (calendar_work.reason == 'dripicons-card', calendar_work.id),
                        else_=None
                    )
                )
            ).label('dripicons_card_count'),  # Кількість dripicons-card
            vacations_canceled.count_days.label('canceled_vacation_days')  # Сума скасованих днів відпустки
        )
        .group_by(users.id, departaments.dep_name, users.user_num_list, departaments.sort_num, vacations_canceled.count_days)
        .order_by(departaments.sort_num.asc(), users.user_num_list.desc())
        .all()  # Отримуємо всі записи
    )

    result = []
    last_depart = ''
    sorted_user_list = sorted(
        user_list,
        key=lambda x: (x.depart_num_list, x.user_num_list)
    )

    # Обробка даних
    for user in sorted_user_list:
        canceled_days = vacations_canceled.query.with_entities(func.sum(vacations_canceled.count_days)).filter(and_(
            vacations_canceled.user_id == user.user_id, vacations_canceled.year <= year)
        ).scalar() or 0

        sum_vacation_days = (
                                db.session.query(func.sum(vacation.count_days))
                                .filter(
                                    and_(
                                        vacation.user_id == user.user_id,
                                        vacation.years <= year
                                    )
                                )
                                .scalar()
                            ) or 0


        # Отримуємо перший день поточного року
        current_year = datetime.now().year

        user_id = user.user_id
        department = user.department or ""
        full_name = user.full_name or ""
        sort_user = user.user_num_list or ""
        vacation_taken = calendar_work.query.filter(
            calendar_work.today_date >= datetime(current_year, 1, 1)  # Початок року
        ).filter(
            calendar_work.today_date <= datetime.now()  # Поточна дата
        ).filter(
            calendar_work.user_id == user_id
        ).filter(
            calendar_work.reason == 'vacation'
        ).count()  # Кількість відпусток
        dripicons_card = calendar_work.query.filter(calendar_work.today_date >= datetime(current_year, 1, 1)).filter(
            calendar_work.today_date <= datetime.now()).filter(
            calendar_work.user_id == user_id).filter(
            calendar_work.reason == 'dripicons-card').count()
        color = None

        head_of_departament = (
            users_departament.query.filter(
                and_(
                    users_departament.user_id == user_id,
                    users_departament.access_level == 6
                ),
                or_(
                    users_departament.dep_id == 29,
                    users_departament.dep_id == 40
                )
            ).first()
        )
        if head_of_departament and department in ['Відділ сервісу', 'Рихтування'] and full_name != "Кролівець Тетяна":
            color = '#838c96'


        # Якщо департамент не змінюється, очищаємо поле
        if last_depart == department:
            department = ""
        else:
            last_depart = user.department

        # Розрахунок залишку відпусток
        vacation_left = sum_vacation_days - (user.vacation_count + user.dripicons_card_count) - canceled_days

        # Формуємо результат
        if full_name != 'Administrator' and department not in ['Розвозка']:
            result.append({
                "department": department,
                "name": full_name, #+ f"[{int(sum_vacation_days)}, {user.vacation_count}, {user.dripicons_card_count}, {canceled_days}]",
                "vacation_taken": vacation_taken,
                "vacation_compensation": dripicons_card,
                "vacation_left": f"{vacation_left}",
                "color": color
            })

    return result

# Допоміжна функція для отримання даних
def get_transport_data(month, year):
    from calendar import monthrange
    from datetime import datetime, timedelta

    start_date = datetime(year, month, 1)
    _, days_in_month = monthrange(year, month)
    end_date = datetime(year, month, days_in_month)

    # Запит до таблиці employee_transport із зв’язкою до users
    transport_records = (
        db.session.query(employee_transport, users.user_fullname)
        .join(users, employee_transport.user_id == users.id)
        .filter(
            employee_transport.date >= start_date,
            employee_transport.date <= end_date,
            users.display == 1  # Тільки активні працівники
        )
        .all()
    )

    # Групування даних по працівниках
    from collections import defaultdict
    employee_data = defaultdict(lambda: {'daily_counts': defaultdict(int), 'total_count': 0, 'full_name': '', 'user_id': None})
    for record, full_name in transport_records:
        day = record.date.day
        employee_data[record.user_id]['full_name'] = full_name
        employee_data[record.user_id]['user_id'] = record.user_id  # Додаємо user_id
        if record.day_shift:
            employee_data[record.user_id]['daily_counts'][day] += 1
        if record.night_shift:
            employee_data[record.user_id]['daily_counts'][day] += 1
        employee_data[record.user_id]['total_count'] = sum(employee_data[record.user_id]['daily_counts'].values())

    # Визначення вихідних для місяця
    weekends = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() >= 5:  # 5 = субота, 6 = неділя
            weekends.append(current_date.day)
        current_date += timedelta(days=1)

    # Форматування результату з інформацією про вихідні
    result = [
        {
            'user_id': data['user_id'],  # Додаємо user_id до результату
            'full_name': data['full_name'],
            'daily_counts': dict(data['daily_counts']),
            'total_count': data['total_count']
        }
        for data in employee_data.values()
    ]
    return sorted(result, key=lambda x: x['full_name']), weekends  # Повертаємо дані та список вихідних



"""def get_employees_data_next(year):
    from sqlalchemy import func, case

    # Основний запит до бази даних
    user_list = (
        users.query
        .join(departaments, users.user_departament == departaments.id)  # Приєднуємо департаменти
        .join(calendar_work, calendar_work.user_id == users.id, isouter=True)  # Приєднуємо calendar_work
        .join(vacation, vacation.user_id == users.id, isouter=True)  # Приєднуємо vacation
        .filter(calendar_work.today_date >= f'{year}-01-01')  # Фільтруємо записи з поточного року
        .filter(users.display == 1)  # Фільтруємо записи з поточного року
        .filter(calendar_work.today_date <= f'{year}-12-31')  # Фільтруємо записи до кінця року
        .add_columns(
            users.id.label('user_id'),
            users.user_num_list.label('user_num_list'),
            users.user_fullname.label('full_name'),
            departaments.dep_name.label('department'),
            func.count(
                func.distinct(
                    case(
                        (calendar_work.reason == 'vacation', calendar_work.id),
                        else_=None
                    )
                )
            ).label('vacation_count'),  # Кількість відпусток
            func.count(
                func.distinct(
                    case(
                        (calendar_work.reason == 'dripicons-card', calendar_work.id),
                        else_=None
                    )
                )
            ).label('dripicons_card_count')  # Кількість dripicons-card
        )
        .group_by(users.id, departaments.dep_name, users.user_num_list, departaments.sort_num)
        .order_by(departaments.sort_num.asc(), users.user_num_list.desc())
        .all()  # Отримуємо всі записи
    )

    result = []
    last_depart = ''

    # Обробка даних
    for user in user_list:
        sum_vacation_days = (
                                db.session.query(func.sum(vacation.count_days))
                                .filter(
                                    and_(
                                        vacation.user_id == user.user_id,
                                        vacation.years <= year
                                    )
                                )
                                .scalar()
                            ) or 0

        vacation_count_query = calendar_work.query.filter_by(user_id=user.user_id, reason='vacation').count()
        dripicons_card_count_query = calendar_work.query.filter_by(user_id=user.user_id, reason='dripicons-card').count()

        user_id = user.user_id
        department = user.department or ""
        full_name = user.full_name or ""
        vacation_taken = user.vacation_count or 0  # Кількість відпусток
        dripicons_card = user.dripicons_card_count or 0  # Кількість компенсацій

        # Якщо департамент не змінюється, очищаємо поле
        if last_depart == department:
            department = ""
        else:
            last_depart = user.department

        # Розрахунок залишку відпусток
        vacation_left = sum_vacation_days - (vacation_count_query + dripicons_card_count_query)
        print(user_id, sum_vacation_days, vacation_count_query, dripicons_card_count_query, (vacation_count_query, dripicons_card_count_query))

        # Формуємо результат
        result.append({
            "department": department,
            "name": full_name,
            "vacation_taken": vacation_taken,
            "vacation_compensation": dripicons_card,
            "vacation_left": f"{vacation_left}",
        })

    return result"""


# Додайте цю функцію до вашого коду
from decimal import Decimal
def sync_fuel_used_with_okko_transactions(report_year, report_month):
    """
    Синхронізує таблицю fuel_used з даними з OKKO транзакцій
    """
    try:
        from sqlalchemy import extract, func, case
        from model import fuel_used, fuel_okko_transactions, fuel_okko_cards

        print(f"🔄 Синхронізація fuel_used з OKKO за {report_month}/{report_year}")

        # Отримуємо всіх користувачів, які мають паливні картки
        users_with_cards = db.session.query(
            fuel_okko_cards.user_id
        ).distinct().all()

        updated_count = 0
        created_count = 0

        for user_row in users_with_cards:
            user_id = user_row.user_id
            if not user_id:
                continue

            # Отримуємо всі картки користувача
            user_cards = fuel_okko_cards.query.filter_by(user_id=user_id).all()
            card_numbers = [card.card_num for card in user_cards if card.card_num]

            if not card_numbers:
                continue

            # Рахуємо загальний об'єм палива з OKKO транзакцій за місяць
            total_fuel_liters = db.session.query(
                func.sum(
                    case(
                        (fuel_okko_transactions.trans_type == 774, fuel_okko_transactions.fuel_volume / 1000),
                        (fuel_okko_transactions.trans_type == 775, -fuel_okko_transactions.fuel_volume / 1000),
                        else_=fuel_okko_transactions.fuel_volume / 1000
                    )
                )
            ).filter(
                fuel_okko_transactions.card_num.in_(card_numbers),
                extract('year', fuel_okko_transactions.trans_date) == report_year,
                extract('month', fuel_okko_transactions.trans_date) == report_month
            ).scalar() or 0

            # Приводимо total_fuel_liters до float
            total_fuel_liters = float(total_fuel_liters)

            # Перевіряємо, чи існує запис в fuel_used
            existing_record = fuel_used.query.filter_by(
                user_id=user_id,
                year=report_year,
                month=report_month
            ).first()

            if existing_record:
                # Оновлюємо існуючий запис, якщо різниця суттєва або total_fuel_liters == 0
                if abs(float(existing_record.fuel) - total_fuel_liters) > 0.1 or total_fuel_liters == 0:
                    print(
                        f"  Оновлюємо користувача {user_id}: {existing_record.fuel}л → {round(total_fuel_liters, 1)}л")
                    existing_record.fuel = round(total_fuel_liters, 1)  # Зберігаємо як float
                    updated_count += 1
            else:
                # Створюємо новий запис тільки якщо total_fuel_liters > 0
                if total_fuel_liters > 0:
                    new_record = fuel_used(
                        user_id=user_id,
                        year=report_year,
                        month=report_month,
                        fuel=round(total_fuel_liters, 1)  # Зберігаємо як float
                    )
                    db.session.add(new_record)
                    print(f"  Створюємо для користувача {user_id}: {round(total_fuel_liters, 1)}л")
                    created_count += 1

        # Зберігаємо зміни
        db.session.commit()
        print(f"✅ Синхронізацію завершено: створено {created_count}, оновлено {updated_count} записів")

        return True, f"Створено {created_count}, оновлено {updated_count} записів"

    except Exception as e:
        db.session.rollback()
        print(f"❌ Помилка при синхронізації fuel_used: {e}")
        return False, str(e)