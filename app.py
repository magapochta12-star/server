from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-me-12345'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# Хранилище для последних голосовых сообщений
voice_messages = []

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
    # Отправляем новому клиенту историю голосовых (последние 10)
    for vm in voice_messages[-10:]:
        emit('voice_message', vm)

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
        'audio': data['audio']   # base64 строка
    }
    voice_messages.append(msg)
    emit('voice_message', msg, broadcast=True)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
