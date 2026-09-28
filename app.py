import os
import json
import hashlib
import base64
import secrets
import uuid
import requests
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

# Личные сообщения
private_messages = deque(maxlen=200)

connected_users = {}
active_sessions = {}
username_to_sid = {}
users_db = {}

# ===== JSONBIN CLOUD =====
JSONBIN_ID = os.environ.get('JSONBIN_ID', '')
JSONBIN_KEY = os.environ.get('JSONBIN_KEY', '')
JSONBIN_URL = f'https://api.jsonbin.io/v3/b/{JSONBIN_ID}'

def save_to_cloud():
    if not JSONBIN_ID or not JSONBIN_KEY:
        print("⚠️ JSONBIN_ID или JSONBIN_KEY не заданы", flush=True)
        return
    try:
        data_to_save = {}
        for username, user_data in users_db.items():
            data_to_save[username] = {
                'password_hash': user_data.get('password_hash'),
                'salt': user_data.get('salt'),
                'avatar': None
            }
        payload = {"users": data_to_save}
        resp = requests.put(
            JSONBIN_URL,
            json=payload,
            headers={'X-Master-Key': JSONBIN_KEY, 'Content-Type': 'application/json'},
            timeout=10
        )
        if resp.status_code == 200:
            print(f"💾 Сохранено в облако: {len(data_to_save)} пользователей", flush=True)
        else:
            print(f"❌ Ошибка облака: {resp.status_code} - {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка сохранения в облако: {e}", flush=True)

def load_from_cloud():
    global users_db
    if not JSONBIN_ID or not JSONBIN_KEY:
        return False
    try:
        resp = requests.get(
            JSONBIN_URL + '/latest',
            headers={'X-Master-Key': JSONBIN_KEY},
            timeout=10
        )
        if resp.status_code == 200:
            cloud_data = resp.json().get('record', {}).get('users', {})
            if cloud_data:
                for username, user_data in cloud_data.items():
                    if username in users_db:
                        users_db[username]['password_hash'] = user_data.get('password_hash')
                        users_db[username]['salt'] = user_data.get('salt')
                    else:
                        users_db[username] = user_data
                print(f"✅ Загружено {len(users_db)} пользователей из облака", flush=True)
                return True
    except Exception as e:
        print(f"❌ Ошибка загрузки из облака: {e}", flush=True)
    return False

USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_db():
    global users_db
    print("🚀 Загрузка базы данных...", flush=True)
    if load_from_cloud():
        return
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users_db = json.load(f)
            print("📁 Загружено из локального файла", flush=True)
    except Exception:
        users_db = {}

def save_db():
    save_to_cloud()
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_db, f, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка локального сохранения: {e}", flush=True)

load_db()

# ===== HELPERS =====
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
    return h, salt

def verify_password(password, stored_hash, salt):
    h, _ = hash_password(password, salt)
    return h == stored_hash

def make_msg_id():
    return str(uuid.uuid4())

# ===== ROUTES =====
@app.route('/')
def index():
    return render_template('index.html')

# ===== AUTH =====
@socketio.on('connect')
def handle_connect():
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
    users_db[username] = {'password_hash': pw_hash, 'salt': salt, 'avatar': None}
    save_db()

    active_sessions[client_id] = username
    connected_users[request.sid] = username
    username_to_sid[username] = request.sid
    emit('update_user_list', list(connected_users.values()), broadcast=True)
    emit('auth_success', {'username': username, 'avatar': None, 'client_id': client_id})

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
    username_to_sid[username] = request.sid
    emit('update_user_list', list(connected_users.values()), broadcast=True)
    emit('auth_success', {'username': username, 'avatar': user.get('avatar'), 'client_id': client_id})

@socketio.on('check_session')
def handle_check_session(data):
    client_id = data.get('client_id')
    if client_id and client_id in active_sessions:
        username = active_sessions[client_id]
        user = users_db.get(username, {})
        connected_users[request.sid] = username
        username_to_sid[username] = request.sid
        emit('update_user_list', list(connected_users.values()), broadcast=True)
        emit('auth_success', {'username': username, 'avatar': user.get('avatar'), 'client_id': client_id})
    else:
        emit('session_expired')

@socketio.on('set_avatar')
def handle_set_avatar(data):
    username = data.get('username')
    avatar_data = data.get('avatar')
    if not username or username not in users_db:
        return
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
        username_to_sid.pop(username, None)
        emit('user_left', {'msg': f'{username} вышел'}, broadcast=True)
        emit('update_user_list', list(connected_users.values()), broadcast=True)

# ===== ОБЩИЕ СООБЩЕНИЯ =====
@socketio.on('text_message')
def handle_text(data):
    msg = {
        'id': make_msg_id(),
        'username': data.get('username', 'Аноним'),
        'text': str(data.get('text', ''))[:2000],
        'edited': False
    }
    text_messages.append(msg)
    emit('text_message', msg, broadcast=True)

# ===== ЛИЧНЫЕ СООБЩЕНИЯ =====
@socketio.on('private_message')
def handle_private(data):
    sender = data.get('username', 'Аноним')
    recipient = data.get('to', '')
    text = str(data.get('text', ''))[:2000]
    
    if not recipient or not text:
        return
    
    msg = {
        'id': make_msg_id(),
        'from': sender,
        'to': recipient,
        'text': text,
        'edited': False
    }
    private_messages.append(msg)
    
    emit('private_message', msg)
    recipient_sid = username_to_sid.get(recipient)
    if recipient_sid:
        emit('private_message', msg, room=recipient_sid)

@socketio.on('get_private_history')
def handle_get_private_history(data):
    username = data.get('username')
    if not username:
        return
    history = [m for m in private_messages if m['from'] == username or m['to'] == username]
    emit('private_history', history)

# ===== РЕДАКТИРОВАНИЕ =====
@socketio.on('edit_message')
def handle_edit(data):
    msg_id = data.get('msg_id')
    new_text = str(data.get('text', ''))[:2000]
    username = data.get('username')
    is_private = data.get('is_private', False)
    
    if is_private:
        for msg in private_messages:
            if msg.get('id') == msg_id:
                if msg['from'] != username:
                    emit('error_msg', {'message': 'Можно редактировать только свои сообщения'})
                    return
                msg['text'] = new_text
                msg['edited'] = True
                payload = {'id': msg_id, 'text': new_text, 'from': msg['from'], 'to': msg['to']}
                emit('private_message_edited', payload)
                recipient_sid = username_to_sid.get(msg['to'])
                if recipient_sid:
                    emit('private_message_edited', payload, room=recipient_sid)
                return
        emit('error_msg', {'message': 'Сообщение не найдено'})
        return
    
    for msg in text_messages:
        if msg.get('id') == msg_id:
            if msg['username'] != username:
                emit('error_msg', {'message': 'Можно редактировать только свои сообщения'})
                return
            msg['text'] = new_text
            msg['edited'] = True
            emit('message_edited', {'id': msg_id, 'text': new_text, 'username': username}, broadcast=True)
            return
    emit('error_msg', {'message': 'Сообщение не найдено'})

# ===== УДАЛЕНИЕ (ищет во ВСЕХ хранилищах) =====
@socketio.on('delete_message')
def handle_delete(data):
    msg_id = data.get('msg_id')
    username = data.get('username')
    is_private = data.get('is_private', False)
    
    if is_private:
        for msg in private_messages:
            if msg.get('id') == msg_id:
                if msg['from'] != username:
                    emit('error_msg', {'message': 'Можно удалять только свои сообщения'})
                    return
                private_messages.remove(msg)
                emit('message_deleted', {'id': msg_id})
                recipient_sid = username_to_sid.get(msg['to'])
                if recipient_sid:
                    emit('message_deleted', {'id': msg_id}, room=recipient_sid)
                return
        emit('error_msg', {'message': 'Сообщение не найдено'})
        return
    
    # Ищем во всех хранилищах: текст, голосовые, фото, файлы
    for store in (text_messages, voice_messages, image_messages, file_messages):
        for msg in store:
            if msg.get('id') == msg_id:
                if msg.get('username') != username:
                    emit('error_msg', {'message': 'Можно удалять только свои сообщения'})
                    return
                store.remove(msg)
                emit('message_deleted', {'id': msg_id}, broadcast=True)
                return
    emit('error_msg', {'message': 'Сообщение не найдено'})

# ===== МЕДИА =====
@socketio.on('voice_message')
def handle_voice(data):
    audio = data['audio']
    audio_b64 = base64.b64encode(audio).decode('ascii') if isinstance(audio, bytes) else audio
    msg = {'id': make_msg_id(), 'username': data.get('username', 'Аноним'), 'audio': audio_b64}
    voice_messages.append(msg)
    emit('voice_message', msg, broadcast=True)

@socketio.on('image_message')
def handle_image(data):
    image = data['image']
    image_b64 = base64.b64encode(image).decode('ascii') if isinstance(image, bytes) else image
    msg = {'id': make_msg_id(), 'username': data.get('username', 'Аноним'), 'image': image_b64, 'mime': data.get('mime', 'image/jpeg')}
    image_messages.append(msg)
    emit('image_message', msg, broadcast=True)

@socketio.on('file_message')
def handle_file(data):
    fd = data['file_data']
    fd_b64 = base64.b64encode(fd).decode('ascii') if isinstance(fd, bytes) else fd
    msg = {
        'id': make_msg_id(),
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
