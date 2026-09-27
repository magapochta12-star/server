import os
import base64
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from collections import deque

app = Flask(__name__)
# Фиксированный секрет: сессии не слетают при рестарте
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production-env-var')
# Убран unsafe werkzeug, добавлен max_http_buffer_size под лимиты
socketio = SocketIO(
    app, async_mode='threading',
    cors_allowed_origins='*',
    max_http_buffer_size=40 * 1024 * 1024  # 40 МБ — запас под фото
)

MAX_TEXT = 100
MAX_VOICE = 10
MAX_IMAGE = 20
MAX_FILE = 10

# Храним base64-строки — они безопасно сериализуются Socket.IO при рестарте
voice_messages = deque(maxlen=MAX_VOICE)
image_messages = deque(maxlen=MAX_IMAGE)
file_messages = deque(maxlen=MAX_FILE)
text_messages = deque(maxlen=MAX_TEXT)
connected_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    for vm in voice_messages: emit('voice_message', vm)
    for im in image_messages: emit('image_message', im)
    for fm in file_messages: emit('file_message', fm)
    if text_messages: emit('text_history', list(text_messages))

@socketio.on('register')
def handle_register(data):
    username = data.get('username', 'Аноним')[:30].strip() or 'Аноним'
    connected_users[request.sid] = username
    emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    username = connected_users.pop(request.sid, None)
    emit('user_left', {'msg': f'{username or "Кто-то"} вышел'}, broadcast=True)
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
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
