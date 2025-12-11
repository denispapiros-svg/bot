# 📞 Начало процесса отправки по ID (Callback-запрос от кнопки)
@bot.callback_query_handler(func=lambda call: call.data == "send_by_id_start")
def start_send_by_id(call):
    chat_id = call.message.chat.id
    
    # Удаляем меню
    bot.edit_message_text(chat_id=chat_id, 
                          message_id=call.message.message_id,
                          text="⚙️ Панель Администратора\n\nВыбрано: Отправить по ID",
                          parse_mode='Markdown')
    
    # Устанавливаем состояние и запрашиваем ID
    admin_states[chat_id] = 'waiting_for_id'
    bot.send_message(chat_id, "🔢 Введите ID пользователя, которому хотите отправить сообщение:")

# 📥 Получение ID пользователя
@bot.message_handler(func=lambda message: is_admin(message.chat.id) and admin_states.get(message.chat.id) == 'waiting_for_id', 
                     content_types=['text'])
def get_target_id(message):
    chat_id = message.chat.id
    
    try:
        # Пытаемся преобразовать введенный текст в число (ID)
        target_id = int(message.text.strip())
        
        # Сохраняем ID и переводим в следующее состояние
        target_user_id[chat_id] = target_id
        admin_states[chat_id] = 'waiting_for_text'
        bot.send_message(chat_id, f"✅ ID {target_id} сохранен. Теперь отправьте текст сообщения, которое нужно отправить этому пользователю.", parse_mode='Markdown')
        
    except ValueError:
        bot.send_message(chat_id, "❌ Некорректный ID. Пожалуйста, введите только целое число (ID пользователя).")

# 📝 Получение текста и отправка сообщения
@bot.message_handler(func=lambda message: is_admin(message.chat.id) and admin_states.get(message.chat.id) == 'waiting_for_text', 
                     content_types=['text'])
def send_message_to_target(message):
    chat_id = message.chat.id
    
    # Получаем ID, на который нужно отправить сообщение
    user_id = target_user_id.get(chat_id)
    text_to_send = message.text
    
    # Очищаем состояние и сохраненный ID
    admin_states.pop(chat_id, None)
    target_user_id.pop(chat_id, None)
    
    if user_id is None:
        bot.send_message(chat_id, "❌ Произошла внутренняя ошибка. Пожалуйста, попробуйте снова, используя команду /admin.")
        return
        
    admin_response = f"✉️ Сообщение от администратора:\n{text_to_send}"
    
    try:
        # Отправляем сообщение целевому пользователю
        bot.send_message(user_id, admin_response)
        
        # Подтверждение для администратора
        bot.send_message(chat_id, f"✅ Сообщение успешно отправлено пользователю ID: {user_id}\n\nНажмите /admin для возврата в меню.", parse_mode='Markdown')
        
    except Exception as e:
        # Если бот не может отправить сообщение
        bot.send_message(chat_id, f"❌ Ошибка отправки пользователю ID {user_id}. Возможно, пользователь заблокировал бота. Ошибка: {e}\n\nНажмите /admin для возврата в меню.", parse_mode='Markdown')


# --- Запуск бота ---
print("Бот запущен. Ожидание сообщений...")
try:
    bot.polling(none_stop=True, interval=0)
except Exception as e:
    print(f"Произошла ошибка: {e}")
