from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-something-random'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

voice_messages = []
image_messages = []
file_messages = []    # храним последние 10 файлов

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    for vm in voice_messages[-10:]:
        emit('voice_message', vm)
    for im in image_messages[-10:]:
        emit('image_message', im)
    for fm in file_messages[-10:]:
        emit('file_message', fm)

@socketio.on('disconnect')
def handle_disconnect():
    emit('user_left', {'msg': 'Кто-то вышел'}, broadcast=True)

@socketio.on('text_message')
def handle_text(data):
    emit('text_message', {
        'username': data.get('username', 'Аноним'),
        'text': data['text']
    }, broadcast=True)

@socketio.on('voice_message')
def handle_voice(data):
    msg = {
        'username': data.get('username', 'Аноним'),
        'audio': data['audio']
    }
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
        'file_data': data['file_data'],   # base64
        'mime': data.get('mime', 'application/octet-stream'),
        'size': data.get('size', 0)
    }
    file_messages.append(msg)
    if len(file_messages) > 10:
        file_messages.pop(0)
    emit('file_message', msg, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
