import telebot

# TOKEN = "6059467054:AAEbIUNhRayD2Hw2ifHjNPkfnY-2ztpvqFw"

bot = telebot.TeleBot("", parse_mode=None)


@bot.message_handler(commands=['start'])
def send_start(message):
    bot.reply_to(message, f"ID этого чата: {message.chat.id}. "
                          f"Нужно добавить в настройки бота для возможности отправки сообщений")


@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, f"Этот бот автоматически отправляет сообщения по ошибкам в ботах ПОЕ. "
                          f"/start - чтобы узнать ID чата")


@bot.message_handler(func=lambda m: True)
def echo_all(message):
    msg_edited = False

    if message.text == "+":
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=message.reply_to_message.message_id,
                                  text="*Взято*\n"+message.reply_to_message.text)
            msg_edited = True
        except Exception as e:
            pass

    if not msg_edited:
        bot.reply_to(message, "Для того, чтобы взять в работу ошибку, нужно 'Ответить' на сообщение плюсиком")


def send_message_to_telegram(bot_token: str, chat_ids: list, message: str):
    global bot

    try:
        if not bot.token:
            bot = telebot.TeleBot(bot_token, parse_mode=None)

        for chat_id in chat_ids:
            bot.send_message(chat_id, message)
    except Exception as e:
        print(f"Ошибка при отправке в телеграм {e}")


if __name__ == '__main__':
    CHAT_ID = -1001530455388
    TOKEN = "6273069511:AAGPH3qy6UTGhZl5e33pWXQtr-ZoURsu0ig"

    send_message_to_telegram(TOKEN, [CHAT_ID, ], "test1")
