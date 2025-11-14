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
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.image as mpimg
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
            session["mascot"] = user.mascot  # 로그인 시 마스코트 로드
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


# 채팅 페이지
@app.route("/")
@login_required
def chat_page():
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
    mascot_list = [f"mascot0{i}.png" for i in range(8)]
    if request.method == "POST":
        selected = request.form.get("mascot")
        if selected in mascot_list:
            current_user.mascot = selected
            db.session.commit()
            session["mascot"] = selected
            flash("프로필이 변경되었어! 🧸")
            return redirect(url_for("chat_page"))
    return render_template("customize.html", mascots=mascot_list)


# 챗봇 로직
# (chat_logic.py 파일이 별도로 존재한다고 가정)
from chat_logic import classify_and_respond


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = current_user.id
    message = request.form.get("message")

    # Import here to avoid circular imports
    from chat_logic import classify_and_respond

    bot_reply = classify_and_respond(message, user_id)

    # Use current app context
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


# --- 이모티콘 경로 매핑 ---
# 5개의 이모티콘 이미지는 'static/images/' 폴더 안에 있어야 합니다.
IMAGE_DIR = os.path.join("static", "result끼리")
EMOTION_IMAGES = {
    "정상": os.path.join(IMAGE_DIR, "환하게 웃는 끼리.png"),
    "경미한 저하": os.path.join(IMAGE_DIR, "미소짓는 끼리.png"),
    "약한 우울": os.path.join(IMAGE_DIR, "보통끼리.png"),
    "중등도 우울": os.path.join(IMAGE_DIR, "살짞 슬픈끼리.png"),
    "심한 우울": os.path.join(IMAGE_DIR, "우울한끼리.png"),
    "중증 우울": os.path.join(IMAGE_DIR, "우울한끼리.png"),
}


def get_emotion_image_path(score):
    if score == 0:
        return EMOTION_IMAGES["정상"]
    elif 1 <= score <= 4:
        return EMOTION_IMAGES["경미한 저하"]
    elif 5 <= score <= 9:
        return EMOTION_IMAGES["약한 우울"]
    elif 10 <= score <= 14:
        return EMOTION_IMAGES["중등도 우울"]
    elif 15 <= score <= 19:
        return EMOTION_IMAGES["심한 우울"]
    else:
        return EMOTION_IMAGES["중증 우울"]


# --- 감정 분석 및 리포트 생성 함수 (Y축 숨기기 적용) ---
def generate_emotion_report(user_id):
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

    # 최근 7일간의 모든 날짜를 포함하도록 daily_score 초기화
    daily_score = {
        (datetime.utcnow().date() - timedelta(days=i)): 0 for i in range(6, -1, -1)
    }  # 7일 전 ~ 오늘

    for log in logs:
        date = log.timestamp.date()
        if date in daily_score:  # 7일 이내의 로그만 집계
            score = sum(1 for kw in mood_keywords if kw in log.message)
            daily_score[date] = daily_score.get(date, 0) + score

    dates = sorted(daily_score.keys())
    scores = [daily_score[d] for d in dates]
    total_score = sum(scores)

    # PHQ-A 기반 해석 (이전과 동일)
    if total_score == 0:
        level, advice = (
            "정상 😊",
            "네가 한 말들을 보니 우울감이 없는 상태야. 지금처럼 잘 지내자!",
        )
    elif 1 <= total_score <= 4:
        level, advice = (
            "경미한 저하 😐",
            "잠깐 기분이 저하된 상태일 수도 있겠다. 가벼운 산책 추천해.",
        )
    elif 5 <= total_score <= 9:
        level, advice = (
            "약한 우울 😔",
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
    # 데이터가 아예 없거나(total_score == 0), 있더라도 모두 0인 경우(any(...) == False) 그래프를 그리지 않음
    if total_score > 0 or any(d in daily_score for d, s in zip(dates, scores)):
        try:
            fig, ax = plt.subplots(figsize=(8, 4))
            fig.patch.set_facecolor("white")  # Figure 배경색
            ax.set_facecolor("#f9f9f9")  # 그래프 배경색

            # 점수 연결선
            ax.plot(
                dates, scores, color="#2a6fb4", linestyle="-", linewidth=2, zorder=1
            )

            # 각 날짜별 이모티콘 표시
            for i, (date, score) in enumerate(zip(dates, scores)):
                emotion_image_path = get_emotion_image_path(score)

                if not os.path.exists(emotion_image_path):
                    print(f"Warning: Image file not found at {emotion_image_path}")
                    continue  # 이미지 없으면 스킵
                # Much smaller images
                fig_width, fig_height = fig.get_size_inches()
                num_points = len(dates)
                dynamic_zoom = (min(fig_width, fig_height) / 130) * (
                    7 / max(num_points, 1)
                )  # Changed from 30 to 100

                img = mpimg.imread(emotion_image_path)
                imagebox = OffsetImage(img, zoom=dynamic_zoom)
                ab = AnnotationBbox(
                    imagebox,
                    (date, score),
                    xybox=(0, 0),
                    xycoords="data",
                    boxcoords="offset points",
                    frameon=False,
                    zorder=2,
                )
                ax.add_artist(ab)

            # --- [수정됨] Y축 숨기기 ---
            ax.get_yaxis().set_visible(False)

            # --- [수정됨] X축 설정 (날짜만 남기기) ---
            ax.set_xlabel("")  # X축 레이블 제거
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m/%d"))
            plt.xticks(rotation=0, fontsize=10, color="#555555")  # X축 날짜 폰트
            ax.tick_params(
                axis="x", which="both", bottom=False, top=False
            )  # X축 눈금선 제거

            # --- [수정됨] Y축 관련 설정 제거 ---
            ax.set_ylabel("")  # Y축 레이블 제거
            ax.set_title("최근 7일 감정 변화", fontsize=14, color="#333333")

            # --- [수정됨] 그래프 테두리(spines) 모두 제거 ---
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["bottom"].set_visible(False)
            ax.spines["left"].set_visible(False)

            # --- [수정됨] 그리드 제거 ---
            # ax.grid(True, alpha=0.3, linestyle='--') # 그리드 라인 제거

            # --- [유지] Y축 범위 설정 ---
            # Y축이 보이지 않더라도, 이모티콘이 잘리지 않도록
            # 내부적으로 범위는 설정해 주어야 합니다.
            min_score = min(scores) - 1
            max_score = max(scores) + 2
            ax.set_ylim(min_score, max_score)
            ax.invert_yaxis()

            plt.tight_layout()
            os.makedirs("static", exist_ok=True)

            graph_filename = f"mood_graph_{user_id}.png"
            graph_full_path = os.path.join("static", graph_filename)
            plt.savefig(graph_full_path)
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
        "report.html",  # report.html 템플릿이 있다고 가정
        **report_data,
    )


# 앱 실행
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
