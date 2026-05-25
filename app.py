from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-something-random'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

# Хранилища сообщений
voice_messages = []
image_messages = []
file_messages = []

# Активные пользователи: sid -> username
connected_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    # Отправляем историю новичку
    for vm in voice_messages[-10:]:
        emit('voice_message', vm)
    for im in image_messages[-10:]:
        emit('image_message', im)
    for fm in file_messages[-10:]:
        emit('file_message', fm)

@socketio.on('register')
def handle_register(data):
    username = data.get('username', 'Аноним')
    connected_users[request.sid] = username
    emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in connected_users:
        del connected_users[request.sid]
    emit('user_left', {'msg': 'Кто-то вышел'}, broadcast=True)
    emit('update_user_list', list(connected_users.values()), broadcast=True)

@socketio.on('text_message')
def handle_text(data):
    emit('text_message', {
        'username': data.get('username', 'Аноним'),
        'text': data['text']
    }, broadcast=True)

@socketio.on('voice_message')
def handle_voice(data):
    msg = {'username': data.get('username', 'Аноним'), 'audio': data['audio']}
    voice_messages.append(msg)
    if len(voice_messages) > 50:
        voice_messages.pop(0)
    emit('voice_message', msg, broadcast=True)

@socketio.on('image_message')
def handle_image(data):
    msg = {
        'username': data.get('username', 'Аноним'),
        'image': data['image'],
        'mime': data.get('mime', 'image/jpeg')
    }
    image_messages.append(msg)
    if len(image_messages) > 20:
        image_messages.pop(0)
    emit('image_message', msg, broadcast=True)

@socketio.on('file_message')
def handle_file(data):
    msg = {
        'username': data.get('username', 'Аноним'),
        'filename': data['filename'],
        'file_data': data['file_data'],
        'mime': data.get('mime', 'application/octet-stream'),
        'size': data.get('size', 0)
    }
    file_messages.append(msg)
    if len(file_messages) > 10:
        file_messages.pop(0)
    emit('file_message', msg, broadcast=True)

# ------------------ Звонки (WebRTC сигналинг) ------------------
@socketio.on('call_user')
def handle_call(data):
    """Переслать предложение конкретному пользователю"""
    target_sid = None
    for sid, name in connected_users.items():
        if name == data['to_username']:
            target_sid = sid
            break
    if not target_sid:
        emit('call_error', {'message': 'Пользователь не найден'})
        return
    emit('incoming_call', {
        'from_username': data['from_username'],
        'signal': data['signal']
    }, room=target_sid)

@socketio.on('call_accepted')
def handle_call_accepted(data):
    """Ответ вызывающему, что звонок принят"""
    target_sid = None
    for sid, name in connected_users.items():
        if name == data['to_username']:
            target_sid = sid
            break
    if target_sid:
        emit('call_accepted', {'signal': data['signal']}, room=target_sid)

@socketio.on('call_rejected')
def handle_call_rejected(data):
    target_sid = None
    for sid, name in connected_users.items():
        if name == data['to_username']:
            target_sid = sid
            break
    if target_sid:
        emit('call_rejected', {'message': 'Звонок отклонён'}, room=target_sid)

@socketio.on('hang_up')
def handle_hang_up(data):
    target_sid = None
    for sid, name in connected_users.items():
        if name == data['to_username']:
            target_sid = sid
            break
    if target_sid:
        emit('call_ended', {}, room=target_sid)

@socketio.on('ice_candidate')
def handle_ice(data):
    target_sid = None
    for sid, name in connected_users.items():
        if name == data['to_username']:
            target_sid = sid
            break
    if target_sid:
        emit('ice_candidate', {'candidate': data['candidate']}, room=target_sid)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
