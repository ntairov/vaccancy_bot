import configparser
import logging
import typing

import aiogram.utils.markdown as md
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.utils.callback_data import CallbackData
from aiogram.utils.exceptions import MessageNotModified

from db_connection import PostgresClient

config = configparser.ConfigParser()
config.read('config.ini')
# Configure logging
logging.basicConfig(level=logging.INFO)
API_TOKEN = config['telegram']['API_TOKEN']

bot = Bot(token=API_TOKEN)

db_query = {'Lang': '', 'Area': '', 'Salary': 0}

# For example use simple MemoryStorage for Dispatcher.
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

languages = ['инженер', 'ios', 'javascript', 'сис админ', 'rust', 'php', 'django', 'unity',
             'программист', 'help desk', 'go', 'python', 'c#', 'c++', 'ruby', '1c', 'perl', 'kotlin', 'android']
area = ['MO', 'Москва', 'Питер', 'Удаленная работа']
ONE_BILLION = 10 ** 9
salary = {'от 100k': (100000, 150000), 'от 150k': (150000, 200000),
          'от 200к': (200000, 300000), 'от 300к': (300000, ONE_BILLION)}

choose_cb = CallbackData('aggregator', 'action')


# States
class Form(StatesGroup):
    lang = State()  # Will be represented in storage as 'Form:lang'
    area = State()  # Will be represented in storage as 'Form:area'
    salary = State()  # Will be represented in storage as 'Form:salary'


def get_lang_keyboard():
    markup = types.InlineKeyboardMarkup()
    for lang in languages:
        markup.insert(
            types.InlineKeyboardButton(
                lang.upper(),
                callback_data=choose_cb.new(action=lang)),
        )
    return markup


def get_area_keyboard():
    markup = types.InlineKeyboardMarkup()
    for ar in area:
        markup.insert(
            types.InlineKeyboardButton(
                ar,
                callback_data=choose_cb.new(action=ar)),
        )
    return markup


def get_salary_keyboard():
    markup = types.InlineKeyboardMarkup()
    for sal in salary.keys():
        markup.insert(
            types.InlineKeyboardButton(
                sal,
                callback_data=choose_cb.new(action=sal)),
        )
    return markup


@dp.message_handler(commands=['start'])
async def say_hi(message: types.Message):
    await message.reply(f"Привет,{message.from_user.full_name}. \nОтправьте /help если хотите посмотреть мои команды ")


@dp.message_handler(commands=['help'])
async def show_available_commands(message: types.Message):
    # msg = md.text(
    #     md.bold("Мои доступные команды:"),
    #     md.text("/get_vaccancy — Найти подходящие вакансии"),
    #     md.text("/get_top_5 — Вывести топ 5 вакансий по зарплатам"),  sep='\n')
    msg = """
         Доступные команды:
        /get_vaccancy — Найти подходящие вакансии
        /get_top_5 — Вывести топ 5 вакансий по зарплатам
        /cancel - отменить все действия по поиску вакансий
    """
    await message.reply(msg)


@dp.message_handler(commands='get_vaccancy', state='*')
async def cmd_start(message: types.Message):
    await message.reply("Выберите специализацию или язык программирования 👨🏼‍💻", reply_markup=get_lang_keyboard())


@dp.errors_handler(exception=MessageNotModified)  # handle the cases when this exception raises
async def message_not_modified_handler(update, error):
    return True  # errors_handler must return True if error was handled correctly


@dp.callback_query_handler(choose_cb.filter(action=languages), state='*')
async def language_query_callback(query: types.CallbackQuery, callback_data: typing.Dict[str, str], state: FSMContext):
    await Form.lang.set()
    logging.info('Got this callback data: %r', callback_data)
    await query.answer()

    lang = callback_data['action']
    await state.update_data(language=lang.lower())
    await Form.next()
    await query.message.reply(" Выберите желаемую зарплату?  🤑💰", reply_markup=get_salary_keyboard())


@dp.callback_query_handler(choose_cb.filter(action=list(salary.keys())), state='*')
async def salary_query_callback(query: types.CallbackQuery, callback_data: typing.Dict[str, str], state: FSMContext):
    logging.info('Got this callback data: %r', callback_data)
    await query.answer()
    salary = callback_data['action']

    await state.update_data(salary=salary)
    await Form.next()
    await query.message.reply(" Выберите желаемый регион ☮️", reply_markup=get_area_keyboard())


def connect_db():
    db_connection = PostgresClient(
        dbname=config['backend_db']['database_name'],
        user=config['backend_db']['username'],
        password=config['backend_db']['password'],
        host=config['backend_db']['host'],
        port=config['backend_db']['port']
    )
    return db_connection.db_connection()


@dp.callback_query_handler(choose_cb.filter(action=area), state='*')
async def area_query_callback(query: types.CallbackQuery, callback_data: typing.Dict[str, str], state: FSMContext):
    logging.info('Got this callback data: %r', callback_data)
    await query.answer()
    area = callback_data['action']
    await state.update_data(area=area)
    data = await state.get_data()
    lang, salary, area = data.get('language'), data.get('salary'), data.get('area')

    await query.message.reply(
        md.text(
            md.bold(f"Вы выбрали:"),
            md.text(f"Специализация: {md.bold(lang)}"),
            md.text(f"Зарплата: {md.bold(salary)}"),
            md.text(f"Регион: {md.bold(area)}") if area != 'Удаленная работа' else md.text(f"Формат: {md.bold(area)}"),
            md.code("Записал данные, выполняю запрос на сервер..."), sep='\n\n'), parse_mode=ParseMode.MARKDOWN
    )
    send_query = get_data(lang, salary, area)
    for data in send_query:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(text='Перейти', url=data['URL']),
        )
        salary_max = data['SalaryMin'] if data['SalaryMax'] == '0' else data['SalaryMax']
        await query.message.answer(
            md.text(
                md.text(f"{md.bold('Локация: ')} {(data['Area'])}"),
                md.text(f"{md.bold('Язык программировнания: ')} {data['Lang']}"),
                md.text(f"{md.bold('Специализация: ')} {data['Name']}"),
                md.text(f"{md.bold('Возможный формат работы:')} {data['Schedule']}"),
                md.text(f"{md.bold('Валюта: ')}{data['Currency']}"),
                md.text(f"{md.bold('Зарплатная вилка: ')} от {data['SalaryMin']} до {salary_max}"),
                md.text(f"Требования : {data['Requirement']}"), sep='\n\n'), parse_mode=ParseMode.MARKDOWN,
            reply_markup=markup
        )

    logging.info('retrived')


def get_data(lang: str, sal: str, ar: str):
    cursor = connect_db()
    get_lang_query = ''
    salary_min, salary_max = salary.get(sal)

    if ar == 'Удаленная работа':
        get_lang_query = """
                SELECT vaccancy#>>'{URL}' as "URL",
                   vaccancy#>>'{Area}' as "Area",
                   vaccancy#>>'{Lang}' as "Lang",
                   vaccancy#>>'{Name}' as "Name",
                   vaccancy#>>'{Schedule}' as "Schedule",
                   vaccancy#>>'{Currency}' as "Currency",
                   vaccancy#>>'{Published}' as "Published",
                   vaccancy#>>'{Salary Max}' as "SalaryMax",
                   vaccancy#>>'{Salary Min}' as "SalaryMin",
                   vaccancy#>>'{Requirement}' as "Requirement"

            FROM jobs WHERE vaccancy#>>'{Lang}' =%s AND vaccancy#>>'{Schedule}'  =%s AND vaccancy#>>'{Salary Min}' >= %s AND  vaccancy#>>'{Salary Max}' <= %s LIMIT 7;
                """
    else:
        get_lang_query = """
                        SELECT vaccancy#>>'{URL}' as "URL",
                           vaccancy#>>'{Area}' as "Area",
                           vaccancy#>>'{Lang}' as "Lang",
                           vaccancy#>>'{Name}' as "Name",
                           vaccancy#>>'{Schedule}' as "Schedule",
                           vaccancy#>>'{Currency}' as "Currency",
                           vaccancy#>>'{Published}' as "Published",
                           vaccancy#>>'{Salary Max}' as "SalaryMax",
                           vaccancy#>>'{Salary Min}' as "SalaryMin",
                           vaccancy#>>'{Requirement}' as "Requirement"

                    FROM jobs WHERE vaccancy#>>'{Lang}' =%s AND vaccancy#>>'{Area}' =%s AND vaccancy#>>'{Salary Min}' >= %s AND  vaccancy#>>'{Salary Max}' <= %s LIMIT 7;
                        """
    try:
        cursor.execute(get_lang_query, (lang.lower(), ar.lower(), str(salary_min), str(salary_max)))
    except Exception as e:
        print(e)
    result = cursor.fetchall()
    return result


# You can use state '*' if you need to handle all states
@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info('Cancelling state %r', current_state)
    # Cancel state and inform user about it
    await state.finish()
    # And remove keyboard (just in case)
    await message.reply('Отменено.', reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state='*', commands='get_top_5')
async def get_top_five(message: types.Message, state: FSMContext):
    query = """
    SELECT
       vaccancy#>>'{URL}' as "URL",
       vaccancy#>>'{Area}' as "Area",
       vaccancy#>>'{Lang}' as "Lang",
       vaccancy#>>'{Name}' as "Name",
       vaccancy#>>'{Schedule}' as "Schedule",
       vaccancy#>>'{Currency}' as "Currency",
       vaccancy#>>'{Published}' as "Published",
       (vaccancy#>>'{Salary Max}')::int as SalaryMax,
       vaccancy#>>'{Salary Min}' as "SalaryMin",
       vaccancy#>>'{Requirement}' as "Requirement"
        FROM jobs ORDER BY (vaccancy#>>'{Salary Max}')::int DESC LIMIT 5;
    """
    logging.info('Sending request  %r')
    cursor = connect_db()
    cursor.execute(query)
    send_query = cursor.fetchall()
    for data in send_query:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(text='Перейти', url=data['URL']),
        )
        salary_max = data['SalaryMin'] if data['salarymax'] == '0' else data['salarymax']
        await message.answer(
            md.text(
                md.text(f"{md.bold('Локация: ')} {(data['Area'])}"),
                md.text(f"{md.bold('Язык программировнания: ')} {data['Lang']}"),
                md.text(f"{md.bold('Специализация: ')} {data['Name']}"),
                md.text(f"{md.bold('Возможный формат работы:')} {data['Schedule']}"),
                md.text(f"{md.bold('Валюта: ')}{data['Currency']}"),
                md.text(f"{md.bold('Зарплатная вилка: ')} от {data['SalaryMin']} до {salary_max}"),
                md.text(f"Требования : {data['Requirement']}"), sep='\n\n'), parse_mode=ParseMode.MARKDOWN,
            reply_markup=markup
        )


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
