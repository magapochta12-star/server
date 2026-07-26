import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from collections import deque

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(64))
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

# Лимиты на количество сообщений (чтобы не переполнить 512 МБ)
MAX_TEXT = 50
MAX_VOICE = 10
MAX_IMAGE = 20
MAX_FILE = 10

# Хранилища: теперь содержат bytes, а не base64-строки
voice_messages = deque(maxlen=MAX_VOICE)   # каждый элемент: {'username': str, 'audio': bytes}
image_messages = deque(maxlen=MAX_IMAGE)   # элемент: {'username': str, 'image': bytes, 'mime': str}
file_messages = deque(maxlen=MAX_FILE)     # элемент: {'username': str, 'filename': str, 'file_data': bytes, 'mime': str, 'size': int}
text_messages = deque(maxlen=MAX_TEXT)

connected_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    # Отправляем историю: бинарные данные остаются бинарными, Socket.IO сам упакует
    for vm in voice_messages:
        emit('voice_message', vm)
    for im in image_messages:
        emit('image_message', im)
    for fm in file_messages:
        emit('file_message', fm)
    if text_messages:
        emit('text_history', list(text_messages))

@socketio.on('register')
def handle_register(data):
    username = data.get('username', 'Аноним')[:30]
    connected_users[request.sid] = username
    emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = connected_users.pop(request.sid, None)
    emit('user_left', {'msg': f'{username or "Кто-то"} вышел'}, broadcast=True)
    emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('text_message')
def handle_text(data):
    msg = {'username': data.get('username', 'Аноним'), 'text': data['text']}
    text_messages.append(msg)
    emit('text_message', msg, broadcast=True)

@socketio.on('voice_message')
def handle_voice(data):
    # data['audio'] — это bytes (бинарный поток от клиента)
    msg = {
        'username': data.get('username', 'Аноним'),
        'audio': data['audio']      # bytes
    }
    voice_messages.append(msg)
    # Шлём всем, включая отправителя (для подтверждения)
    emit('voice_message', msg, broadcast=True)

@socketio.on('image_message')
def handle_image(data):
    msg = {
        'username': data.get('username', 'Аноним'),
        'image': data['image'],     # bytes
        'mime': data.get('mime', 'image/jpeg')
    }
    image_messages.append(msg)
    emit('image_message', msg, broadcast=True)

@socketio.on('file_message')
def handle_file(data):
    msg = {
        'username': data.get('username', 'Аноним'),
        'filename': data['filename'],
        'file_data': data['file_data'],  # bytes
        'mime': data.get('mime', 'application/octet-stream'),
        'size': data.get('size', 0)
    }
    file_messages.append(msg)
    emit('file_message', msg, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('typing', {
        'username': data.get('username', 'Аноним'),
        'typing': data.get('typing', False)
    }, broadcast=True, include_self=False)

@socketio.on('action_status')
def handle_action_status(data):
    emit('action_status', {
        'username': data.get('username', 'Аноним'),
        'action': data.get('action', '')
    }, broadcast=True, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
