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
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

# Flask 설정
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# 세션 & 쿠키 보안 강화
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_DURATION=timedelta(days=7),
    REMEMBER_COOKIE_SAMESITE="None",
    REMEMBER_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)

# CORS 설정
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

# DB 설정
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# 모델 정의
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


# 회원가입
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")

        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))

        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("회원가입 성공! 로그인 해주세요.")
        return redirect(url_for("login"))
    return render_template("register.html")


# 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            session.permanent = True
            session["mascot"] = user.mascot
            return redirect(url_for("chat_page"))
        else:
            flash("로그인 실패. 아이디나 비밀번호를 확인하세요.")
    return render_template("login.html")


# 로그아웃
@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("login"))


# 🆕 브라우저 세션 시작 시 인사 메시지 자동 추가 함수
def add_greeting_if_needed(user_id):
    """브라우저를 새로 열어서 접속한 경우에만 라리의 인사 메시지를 추가"""
    # 이번 세션에서 이미 인사했는지 확인
    if session.get('greeted'):
        return  # 이미 인사함
    
    # 기존 인사 메시지
    greeting_message = "안녕~ 오늘 뭐 했어?"
    
    # 챗봇 인사 메시지 추가
    new_greeting = ChatLog(
        user_id=user_id,
        role="bot",
        message=greeting_message
    )
    db.session.add(new_greeting)
    db.session.commit()
    
    # 이번 세션에서 인사했다고 표시
    session['greeted'] = True


# 채팅 페이지
@app.route("/")
@login_required
def chat_page():
    # 🆕 브라우저를 새로 열었을 때만 인사 추가
    add_greeting_if_needed(current_user.id)
    
    logs = (
        ChatLog.query.filter_by(user_id=current_user.id)
        .order_by(ChatLog.timestamp)
        .all()
    )
    chat_history = [{"role": log.role, "message": log.message} for log in logs]
    return render_template(
        "index.html", username=current_user.username, history=chat_history
    )


# 꾸미기 (마스코트 선택)
@app.route("/customize", methods=["GET", "POST"])
@login_required
def customize():
    all_mascots = [f"mascot{i:02d}.png" for i in range(20)] 

    acc_emojis = [
        "🎀", "🎉", "🌟", "🧢", "👑", "🕶", "🌿", "🎵", 
        "👽", "✨", "👾", "🧣", "📕", "🥖", "🛟"
    ]
    clothes_emojis = ["🧥", "🧑🏻‍🎄", "👩", "👩","👨"]

    acc_list = [f"mascot{i:02d}.png" for i in range(15)]
    clothes_list = [f"mascot{i:02d}.png" for i in range(15, 20)]

    acc_data = list(zip(acc_list, acc_emojis))
    clothes_data = list(zip(clothes_list, clothes_emojis))

    if request.method == "POST":
        selected = request.form.get("mascot")
        
        if selected in all_mascots:
            current_user.mascot = selected
            db.session.commit()
            session["mascot"] = selected
            
            return jsonify({"success": True, "message": "저장 완료!"})
        
        return jsonify({"success": False, "message": "잘못된 파일입니다."}), 400

    return render_template(
        "customize.html",
        acc_data=acc_data,
        clothes_data=clothes_data)


# 챗봇 로직
from chat_logic import classify_and_respond


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = current_user.id
    message = request.form.get("message")

    from chat_logic import classify_and_respond

    bot_reply = classify_and_respond(message, user_id)

    db.session.add(ChatLog(user_id=user_id, role="user", message=message))
    db.session.add(ChatLog(user_id=user_id, role="bot", message=bot_reply))
    db.session.commit()

    return jsonify({"response": bot_reply})


# 새로고침(대화 초기화)
@app.route("/reset", methods=["POST"])
@login_required
def reset_chat():
    ChatLog.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"message": "Chat history cleared."})


# 감정 분석 및 리포트 생성 함수
def generate_emotion_report(user_id):
    kst_offset = timedelta(hours=9)
    now_kst = datetime.utcnow() + kst_offset
    
    logs = (
        ChatLog.query.filter(
            ChatLog.user_id == user_id,
            ChatLog.role == "user",
            ChatLog.timestamp >= datetime.utcnow() - timedelta(days=7),
        )
        .order_by(ChatLog.timestamp)
        .all()
    )

    mood_keywords = [
        "힘들",
        "우울",
        "무기력",
        "짜증",
        "귀찮",
        "죽고 싶",
        "의욕없",
        "불안",
    ]

    daily_score = {
        (now_kst.date() - timedelta(days=i)): 0 for i in range(6, -1, -1)
    }

    for log in logs:
        log_time_kst = log.timestamp + kst_offset
        date = log_time_kst.date()
        
        if date in daily_score:
            score = sum(1 for kw in mood_keywords if kw in log.message)
            daily_score[date] = daily_score.get(date, 0) + score

    dates = sorted(daily_score.keys())
    scores = [daily_score[d] for d in dates]
    total_score = sum(scores)

    if total_score == 0:
        level, advice = (
            "정상 😊",
            "네가 한 말들을 보니 우울감이 없는 상태야. 지금처럼 잘 지내자!",
        )
    elif 1 <= total_score <= 4:
        level, advice = (
            "경미한 저하 😀",
            "잠깐 기분이 저하된 상태일 수도 있겠다. 가벼운 산책 추천해.",
        )
    elif 5 <= total_score <= 9:
        level, advice = (
            "약한 우울 😐",
            "약간 우울한 기분이 느껴져. 수면이나 식습관을 규칙적으로 해보자.",
        )
    elif 10 <= total_score <= 14:
        level, advice = (
            "중등도 우울 😞",
            "꽤 우울감이 느껴지는 상태야. 음악 듣거나 스트레칭 해보자.",
        )
    elif 15 <= total_score <= 19:
        level, advice = (
            "심한 우울 😢",
            "우울감이 심해 보여. 주변에 이야기하거나 상담 도움을 받아보자.",
        )
    else:
        level, advice = "중증 우울 ⚠️", "심한 우울감이 보여. 꼭 주변에 도움을 요청하자."

    graph_filename = None
    if total_score > 0 or any(d in daily_score for d, s in zip(dates, scores)):
        try:
            # 우울 점수를 6단계로 변환하는 함수
            def score_to_level(score):
                if score == 0:
                    return 0  # 정상
                elif 1 <= score <= 4:
                    return 1  # 경미한 저하
                elif 5 <= score <= 9:
                    return 2  # 약한 우울
                elif 10 <= score <= 14:
                    return 3  # 중등도 우울
                elif 15 <= score <= 19:
                    return 4  # 심한 우울
                else:
                    return 5  # 중증 우울
            
            # 점수를 레벨로 변환
            level_scores = [score_to_level(s) for s in scores]
            
            fig, ax = plt.subplots(figsize=(8, 4))
            fig.patch.set_facecolor("white")
            ax.set_facecolor("#f9f9f9")

            # 선 그래프 그리기
            ax.plot(
                dates, level_scores, color="#2a6fb4", linestyle="-", linewidth=2, 
                marker='o', markersize=8, markerfacecolor='#2a6fb4', 
                markeredgecolor='white', markeredgewidth=2, zorder=2
            )

            # Y축 범위 설정 (0~5, 6단계)
            ax.set_ylim(-0.5, 5.5)
            ax.invert_yaxis()  # Y축 반전 (0이 위, 5가 아래)

            # Y축에 텍스트 이모티콘 추가
            # 환하게 웃는 이모지 (Y축 상단, level=0)
            ax.text(-0.15, 0, '😊', transform=ax.get_yaxis_transform(), 
                   fontsize=30, ha='center', va='center')
            
            # 슬프게 우는 이모지 (Y축 하단, level=5)
            ax.text(-0.15, 5, '😢', transform=ax.get_yaxis_transform(), 
                   fontsize=30, ha='center', va='center')

            # Y축 눈금 설정 (0~5)
            ax.set_yticks([0, 1, 2, 3, 4, 5])
            ax.set_yticklabels([])  # 숫자는 숨기기
            
            # X축 설정
            ax.set_xlabel("")
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m/%d"))
            plt.xticks(rotation=0, fontsize=10, color="#555555")
            ax.tick_params(axis="x", which="both", bottom=False, top=False)
            ax.tick_params(axis="y", which="both", left=False, right=False)

            # 테두리 제거
            ax.set_ylabel("")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["bottom"].set_visible(False)
            ax.spines["left"].set_visible(False)

            plt.tight_layout()
            os.makedirs("static", exist_ok=True)

            graph_filename = f"mood_graph_{user_id}.png"
            graph_full_path = os.path.join("static", graph_filename)
            plt.savefig(graph_full_path, dpi=100, bbox_inches='tight')
            plt.close()

        except Exception as e:
            print(f"Error generating graph: {e}")
            graph_filename = None

    return {
        "username": current_user.username,
        "score": total_score,
        "level": level,
        "advice": advice,
        "graph": graph_filename,
    }


# 감정 분석
@app.route("/analyze")
@login_required
def analyze():
    report_data = generate_emotion_report(current_user.id)
    return render_template("result.html", **report_data)


# 리포트
@app.route("/report")
@login_required
def report():
    report_data = generate_emotion_report(current_user.id)
    return render_template(
        "report.html",
        **report_data,
    )


# 앱 실행
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

