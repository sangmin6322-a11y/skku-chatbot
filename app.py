from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
from flask_cors import CORS
from werkzeug.utils import secure_filename
import random, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dotenv import load_dotenv
load_dotenv()

# ✅ Flask 설정
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv("SECRET_KEY", "secret-key")

# ✅ 세션 & 쿠키
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_DURATION=timedelta(days=7),
    REMEMBER_COOKIE_SAMESITE="None",
    REMEMBER_COOKIE_SECURE=True
)

# ✅ CORS 설정
CORS(app, resources={r"/*": {"origins": [
    "https://chatbot-rzw5.onrender.com",
    "https://skku-chatbot.onrender.com"
]}}, supports_credentials=True)

# ✅ DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///users.db")
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
db = SQLAlchemy(app)

# ✅ Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ✅ 모델
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(10))
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ✅ 회원가입
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_pw = generate_password_hash(password)
        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("회원가입 성공! 로그인 해주세요.")
        return redirect(url_for("login"))
    return render_template("register.html")

# ✅ 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for("chat_page"))
        else:
            flash("로그인 실패. 아이디나 비밀번호를 확인하세요.")
    return render_template("login.html")

# ✅ 로그아웃
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.")
    return redirect(url_for("login"))

# ✅ 채팅 페이지
@app.route("/")
@login_required
def chat_page():
    logs = ChatLog.query.filter_by(user_id=current_user.id).order_by(ChatLog.timestamp).all()
    chat_history = [{"role": log.role, "message": log.message} for log in logs]
    return render_template("index.html", username=current_user.username, history=chat_history)

# ✅ 챗봇 로직
from chat_logic import classify_and_respond

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = current_user.id
    message = request.form.get("message")
    bot_reply = classify_and_respond(message, user_id)
    db.session.add(ChatLog(user_id=user_id, role="user", message=message))
    db.session.add(ChatLog(user_id=user_id, role="bot", message=bot_reply))
    db.session.commit()
    return jsonify({"response": bot_reply})

# ✅ 감정 분석
@app.route("/analyze")
@login_required
def analyze():
    user_id = current_user.id
    logs = ChatLog.query.filter(
        ChatLog.user_id == user_id,
        ChatLog.role == "user",
        ChatLog.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).all()

    mood_keywords = ["힘들", "우울", "무기력", "짜증", "귀찮", "죽고 싶", "의욕없", "불안"]
    daily_score = {}
    for log in logs:
        date = log.timestamp.date()
        score = sum(1 for kw in mood_keywords if kw in log.message)
        daily_score[date] = daily_score.get(date, 0) + score

    total_score = sum(daily_score.values())

    # ✅ 기본값 0점으로 수정
    if total_score == 0:
        level, advice = "정상 😊", "최근 대화에서 부정적인 감정은 거의 보이지 않아요. 잘 지내고 있네요!"
    elif total_score <= 3:
        level, advice = "경도 우울 😐", "가벼운 스트레스나 피로가 느껴져요. 충분히 쉬고 좋아하는 걸 해보세요."
    elif total_score <= 6:
        level, advice = "중등도 우울 😔", "감정적 피로가 누적된 것 같아요. 가까운 사람에게 털어놓는 것도 좋아요."
    else:
        level, advice = "고위험 😢", "최근 대화에서 심한 무기력감이 보여요. 전문 상담사에게 도움을 받아보는 게 좋겠어요."

    if daily_score:
        dates = sorted(daily_score.keys())
        scores = [daily_score[d] for d in dates]
        plt.figure(figsize=(6, 3))
        plt.plot(dates, scores, marker='o', color='#2a6fb4')
        plt.title("최근 7일 감정 키워드 변화")
        plt.xlabel("날짜")
        plt.ylabel("감정 점수")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        os.makedirs("static", exist_ok=True)
        graph_path = os.path.join("static", "mood_graph.png")
        plt.savefig(graph_path)
        plt.close()
    else:
        graph_path = None

    return render_template("result.html",
                           username=current_user.username,
                           score=total_score,
                           level=level,
                           advice=advice,
                           graph=graph_path)

if __name__ == "__main__":
    app.run(debug=True)
