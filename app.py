import os
import json
import hashlib
import base64
import secrets
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from collections import deque

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*',
                    max_http_buffer_size=40 * 1024 * 1024)

MAX_TEXT, MAX_VOICE, MAX_IMAGE, MAX_FILE = 100, 10, 20, 10
voice_messages = deque(maxlen=MAX_VOICE)
image_messages = deque(maxlen=MAX_IMAGE)
file_messages = deque(maxlen=MAX_FILE)
text_messages = deque(maxlen=MAX_TEXT)

# Онлайн: {socket_sid: username}
connected_users = {}
# Активные сессии: {client_id: username}
active_sessions = {}

# Файл пользователей
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')
users_db = {}

def load_db():
    global users_db
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users_db = json.load(f)
    except Exception:
        users_db = {}

def save_db():
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_db, f, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

load_db()

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
    return h, salt

def verify_password(password, stored_hash, salt):
    h, _ = hash_password(password, salt)
    return h == stored_hash

def safe_avatar_b64(data):
    """Сжимаем аватарку до разумного размера для хранения"""
    if isinstance(data, bytes):
        return base64.b64encode(data).decode('ascii')
    return data

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # Восстанавливаем историю
    for vm in voice_messages: emit('voice_message', vm)
    for im in image_messages: emit('image_message', im)
    for fm in file_messages: emit('file_message', fm)
    if text_messages: emit('text_history', list(text_messages))

@socketio.on('register')
def handle_register(data):
    username = data.get('username', '').strip()[:30]
    password = data.get('password', '')
    client_id = data.get('client_id', request.sid)

    if not username or not password:
        emit('auth_error', {'message': 'Заполните все поля'})
        return
    if len(password) < 4:
        emit('auth_error', {'message': 'Пароль минимум 4 символа'})
        return
    if username.lower() in [u.lower() for u in users_db.keys()]:
        emit('auth_error', {'message': 'Этот ник уже занят'})
        return

    pw_hash, salt = hash_password(password)
    users_db[username] = {
        'password_hash': pw_hash,
        'salt': salt,
        'avatar': None
    }
    save_db()

    active_sessions[client_id] = username
    connected_users[request.sid] = username
    emit('update_user_list', list(connected_users.values()), broadcast=True)
    emit('auth_success', {
        'username': username,
        'avatar': None,
        'client_id': client_id
    })

@socketio.on('login')
def handle_login(data):
    username = data.get('username', '').strip()[:30]
    password = data.get('password', '')
    client_id = data.get('client_id', request.sid)

    if not username or not password:
        emit('auth_error', {'message': 'Заполните все поля'})
        return

    user = users_db.get(username)
    if not user:
        emit('auth_error', {'message': 'Пользователь не найден'})
        return

    if not verify_password(password, user['password_hash'], user['salt']):
        emit('auth_error', {'message': 'Неверный пароль'})
        return

    active_sessions[client_id] = username
    connected_users[request.sid] = username
    emit('update_user_list', list(connected_users.values()), broadcast=True)
    emit('auth_success', {
        'username': username,
        'avatar': user.get('avatar'),
        'client_id': client_id
    })

@socketio.on('check_session')
def handle_check_session(data):
    client_id = data.get('client_id')
    if client_id and client_id in active_sessions:
        username = active_sessions[client_id]
        user = users_db.get(username, {})
        emit('auth_success', {
            'username': username,
            'avatar': user.get('avatar'),
            'client_id': client_id
        })
    else:
        emit('session_expired')

@socketio.on('set_avatar')
def handle_set_avatar(data):
    username = data.get('username')
    avatar_data = data.get('avatar')
    if not username or username not in users_db:
        return
    # avatar_data может быть bytes или строкой
    if isinstance(avatar_data, bytes):
        avatar_b64 = base64.b64encode(avatar_data).decode('ascii')
    else:
        avatar_b64 = avatar_data
    users_db[username]['avatar'] = avatar_b64
    save_db()
    emit('avatar_updated', {'username': username, 'avatar': avatar_b64}, broadcast=True)

@socketio.on('get_user_avatars')
def handle_get_avatars(data):
    usernames = data.get('usernames', [])
    result = {}
    for u in usernames:
        if u in users_db:
            result[u] = users_db[u].get('avatar')
    emit('user_avatars', result)

@socketio.on('disconnect')
def handle_disconnect():
    username = connected_users.pop(request.sid, None)
    if username:
        emit('user_left', {'msg': f'{username} вышел'}, broadcast=True)
        emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('text_message')
def handle_text(data):
    msg = {'username': data.get('username', 'Аноним'), 'text': str(data.get('text', ''))[:2000]}
    text_messages.append(msg)
    emit('text_message', msg, broadcast=True)

@socketio.on('voice_message')
def handle_voice(data):
    audio = data['audio']
    audio_b64 = base64.b64encode(audio).decode('ascii') if isinstance(audio, bytes) else audio
    msg = {'username': data.get('username', 'Аноним'), 'audio': audio_b64}
    voice_messages.append(msg)
    emit('voice_message', msg, broadcast=True)

@socketio.on('image_message')
def handle_image(data):
    image = data['image']
    image_b64 = base64.b64encode(image).decode('ascii') if isinstance(image, bytes) else image
    msg = {'username': data.get('username', 'Аноним'), 'image': image_b64, 'mime': data.get('mime', 'image/jpeg')}
    image_messages.append(msg)
    emit('image_message', msg, broadcast=True)

@socketio.on('file_message')
def handle_file(data):
    fd = data['file_data']
    fd_b64 = base64.b64encode(fd).decode('ascii') if isinstance(fd, bytes) else fd
    msg = {
        'username': data.get('username', 'Аноним'),
        'filename': str(data.get('filename', 'file'))[:100],
        'file_data': fd_b64,
        'mime': data.get('mime', 'application/octet-stream'),
        'size': int(data.get('size', 0))
    }
    file_messages.append(msg)
    emit('file_message', msg, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('typing', {
        'username': data.get('username', 'Аноним'),
        'typing': bool(data.get('typing', False))
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
