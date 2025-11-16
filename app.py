from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
from flask_cors import CORS
import random, os
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------
# Flask 기본 설정
# ------------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# Secure Session Settings
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_DURATION=timedelta(days=7),
    REMEMBER_COOKIE_SAMESITE="None",
    REMEMBER_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)

# CORS
CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://chatbot-rzw5.onrender.com",
                "https://skku-chatbot.onrender.com",
            ]
        }
    },
    supports_credentials=True,
)

# ------------------------------------------------------
# DB
# ------------------------------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ------------------------------------------------------
# 로그인 시스템
# ------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ------------------------------------------------------
# 모델 정의
# ------------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    mascot = db.Column(db.String(50), default="mascot00.png")


class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    role = db.Column(db.String(10))
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------------------------------------
# 회원가입
# ------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
        user = User(username=username, password=hashed_pw)

        db.session.add(user)
        db.session.commit()

        flash("회원가입 성공!")
        return redirect(url_for("login"))

    return render_template("register.html")


# ------------------------------------------------------
# 로그인
# ------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            session["mascot"] = user.mascot
            return redirect(url_for("chat_page"))

        flash("로그인 실패!")

    return render_template("login.html")


# ------------------------------------------------------
# 로그아웃
# ------------------------------------------------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("login"))


# ------------------------------------------------------
# 채팅 페이지
# ------------------------------------------------------
@app.route("/")
@login_required
def chat_page():
    logs = (
        ChatLog.query.filter_by(user_id=current_user.id)
        .order_by(ChatLog.timestamp)
        .all()
    )
    history = [{"role": log.role, "message": log.message} for log in logs]
    return render_template("index.html", username=current_user.username, history=history)


# ------------------------------------------------------
# 마스코트 커스터마이징
# ------------------------------------------------------
@app.route("/customize", methods=["GET", "POST"])
@login_required
def customize():

    all_mascots = [f"mascot{i:02d}.png" for i in range(20)]

    acc_emojis = [
        "🎀", "🎉", "🌟", "🧢", "👒", "🕶", "🌿", "🎵",
        "👽", "✨", "👾", "🧣", "📕", "🥖", "🛟"
    ]
    clothes_emojis = ["🧥", "🧑🏻‍🎄", "💩", "👩", "👨"]

    acc_files = [f"mascot{i:02d}.png" for i in range(15)]
    clothes_files = [f"mascot{i:02d}.png" for i in range(15, 20)]

    acc_data = list(zip(acc_files, acc_emojis))
    clothes_data = list(zip(clothes_files, clothes_emojis))

    if request.method == "POST":
        selected = request.form.get("mascot")

        if selected in all_mascots:
            current_user.mascot = selected
            session["mascot"] = selected
            db.session.commit()
            return jsonify({"success": True})

        return jsonify({"success": False}), 400

    return render_template(
        "customize.html",
        acc_data=acc_data,
        clothes_data=clothes_data,
    )


# ------------------------------------------------------
# 챗봇 로직
# ------------------------------------------------------
from chat_logic import classify_and_respond


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = current_user.id
    text = request.form.get("message")

    reply = classify_and_respond(text, user_id)

    db.session.add(ChatLog(user_id=user_id, role="user", message=text))
    db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
    db.session.commit()

    return jsonify({"response": reply})


# ------------------------------------------------------
# 새로고침(대화 기록 삭제)
# ------------------------------------------------------
@app.route("/reset", methods=["POST"])
@login_required
def reset_chat():
    ChatLog.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"message": "초기화 완료"})


# ------------------------------------------------------
# 📊 Chart.js 기반 감정 분석 (matplotlib 제거됨)
# ------------------------------------------------------
def generate_emotion_report(user_id):
    kst_offset = timedelta(hours=9)
    now_kst = datetime.utcnow() + kst_offset

    logs = ChatLog.query.filter(
        ChatLog.user_id == user_id,
        ChatLog.role == "user",
        ChatLog.timestamp >= datetime.utcnow() - timedelta(days=7),
    ).all()

    mood_keywords = [
        "힘들", "우울", "무기력", "짜증",
        "귀찮", "죽고 싶", "의욕없", "불안"
    ]

    daily_score = {
        (now_kst.date() - timedelta(days=i)): 0
        for i in range(6, -1, -1)
    }

    for log in logs:
        local_time = log.timestamp + kst_offset
        d = local_time.date()

        if d in daily_score:
            daily_score[d] += sum(kw in log.message for kw in mood_keywords)

    # 날짜 / 점수 리스트
    days_sorted = sorted(daily_score.keys())
    dates = [d.strftime("%m/%d") for d in days_sorted]
    scores = [daily_score[d] for d in days_sorted]
    total = sum(scores)

    # PHQ 레벨
    if total == 0:
        level = "정상 😊"
        advice = "지금처럼 잘 지내자!"
    elif 1 <= total <= 4:
        level = "경미한 저하 😐"
        advice = "조금 지친 것 같아. 산책 어떨까?"
    elif 5 <= total <= 9:
        level = "약한 우울 😔"
        advice = "기분이 좀 가라앉아 보여. 생활 리듬을 챙겨보자."
    elif 10 <= total <= 14:
        level = "중등도 우울 😞"
        advice = "꽤 힘들어 보이네. 스트레칭이나 음악 추천해."
    elif 15 <= total <= 19:
        level = "심한 우울 😢"
        advice = "힘이 많이 빠진 것 같아. 주변에 이야기해봐."
    else:
        level = "중증 우울 ⚠️"
        advice = "정말 힘든 상태야. 꼭 주변 도움을 요청해줘."

    return {
        "username": current_user.username,
        "level": level,
        "advice": advice,
        "dates": dates,
        "scores": scores,
        "has_logs": total > 0
    }


# ------------------------------------------------------
# 리포트 페이지
# ------------------------------------------------------
@app.route("/analyze")
@login_required
def analyze():
    return render_template("result.html", **generate_emotion_report(current_user.id))


@app.route("/report")
@login_required
def report():
    return render_template("result.html", **generate_emotion_report(current_user.id))


# ------------------------------------------------------
# 실행
# ------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

