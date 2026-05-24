from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

voice_messages = []

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('user_joined', {'msg': 'Кто-то присоединился'}, broadcast=True)
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
        'audio': data['audio']
    }
    voice_messages.append(msg)
    emit('voice_message', msg, broadcast=True)

# Для Render не нужен app.run(), он сам запустит через gunicorn
# Оставим, чтобы можно было тестировать локально
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
