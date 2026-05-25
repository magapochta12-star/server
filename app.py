from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-something-random'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

voice_messages = []
image_messages = []   # храним последние 20 фото

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    # Отправляем новому клиенту историю
    for vm in voice_messages[-10:]:
        emit('voice_message', vm)
    for im in image_messages[-10:]:
        emit('image_message', im)

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
        'image': data['image'],   # base64
        'mime': data.get('mime', 'image/jpeg')
    }
    image_messages.append(msg)
    if len(image_messages) > 20:
        image_messages.pop(0)
    emit('image_message', msg, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
