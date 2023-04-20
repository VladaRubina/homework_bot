import os
import logging
import telegram
import requests
import time
import sys

from http import HTTPStatus
from dotenv import load_dotenv
from exceptions import DoNotSend, IncorrectAPIResponse
from telegram.error import TelegramError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """
    Check availability of venv variables required for bot operation.

    logging writes information to a log file.
    If all environment variables are present,
    the function returns True, otherwise False.
    """
    logging.info('check for all tokens availability')
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """
    Send message to Telegram chat.
    Use a bot instance and a text message string.
    The chat ID is obtained from the venv variable TELEGRAM_CHAT_ID.
    """
    try:
        logging.debug('Send of status into telegram')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.info(message)
    except TelegramError as e:
        logging.error(f'something wrong with message sending to telegram: {e}')


def get_api_answer(load):
    """
    Makes a request to an API endpoint.

    Returns the response in JSON format.
    It takes a temporary token as an argument and
    returns the API response if the request is successful.
    """
    timeline = load or time.time_ns()
    message = ('Begin request to API. Request:{url}, {headers}, {params}.')
    logging.info(message)

    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timeline}
        )

        if response.status_code != HTTPStatus.OK:
            raise IncorrectAPIResponse(
                f'API response does not return 200.'
                f'Response code: {response.status_code}.'
                f'Reason: {response.reason}.'
                f'Text: {response.text}.'
            )
        return response.json()

    except Exception as error:
        raise IncorrectAPIResponse(message, error)

    finally:
        message = 'got API response. Request: {url}, {headers}, {params}'
        logging.info(message)


def check_response(response):
    """
    Check API response for compliance with documentation.
    Accepts API response as an argument, which is expected to be in JSON format
    and converted to a Python data type.
    The function checks if the response complies with the API documentation and
    returns True if it does, False otherwise.
    """
    if 'homeworks' not in response:
        raise TypeError('Response does not contain "homeworks" key')

    if not isinstance(response, dict):
        raise TypeError('Response is not a dictionary')

    if not isinstance(response['homeworks'], list):
        raise TypeError('"homeworks" value is not a list')

    if 'current_date' not in response:
        raise TypeError('Response does not contain "current_date" key')

    return response['homeworks']


def parse_status(homework):
    """
    Extracts the status of a specific homework.
    Takes a homework object as an argument and extracts its status.
    If successful, the function will return a string formatted for Telegram,
    containing the appropriate verdict from the dictionary HOMEWORK_VERDICTS.
    """
    if 'homework_name' not in homework:
        raise KeyError('No key for homework_name in API response')

    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    if verdict is None:
        raise ValueError('Invalid status value in API response')

    homework_name = homework['homework_name']

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = 'No token. Bot operation stopped!'
        logging.critical(message)
        sys.exit(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    load = int(time.time())
    start_message = 'Bot starts operation'
    send_message(bot, start_message)
    logging.info(start_message)
    prev_msg = ''

    while True:
        try:
            response = get_api_answer(load)
            load = response.get(
                'current_date', int(time.time())
            )
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                message = 'No new status'
            if message != prev_msg:
                send_message(bot, message)
                prev_msg = message
            else:
                logging.info(message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)
            if message != prev_msg:
                send_message(bot, message)
                prev_msg = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.FileHandler(
                os.path.abspath('main.log'), mode='a', encoding='UTF-8'),
            logging.StreamHandler(stream=sys.stdout)],
        format='%(asctime)s, %(levelname)s, %(funcName)s, '
               '%(name)s, %(message)s'
    )
    main()
