import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    current_user,
    logout_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ===================== 기본 설정 =====================

app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-change-this"  # 바꿔도 됨
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat_history"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 업로드 이미지 저장 경로
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"  # @login_required일 때 여기로 보냄
login_manager.init_app(app)


# ===================== DB 모델 =====================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "user" or "bot"
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ===================== 로그인 매니저 =====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===================== 외부 로직 불러오기 =====================
# chat_logic.py 안에 classify_and_respond 함수가 이미 있다고 가정하고 사용한다.
# 주의: 기존 chat_logic.py는 안에서 db에 기록+commit을 해버렸는데
#       이제는 그 부분을 주석 처리하거나 제거해야 한다.
#       즉, 여기서는 "문자열 답장만 return" 해야 함.

from chat_logic import classify_and_respond


# ===================== 유틸: 감정 점수 추정 =====================

def estimate_mood_score_from_text(text: str) -> int:
    """
    아주 단순한 키워드 기반 감정 점수 예시.
    + 행복/안심 계열 단어 -> 가산
    + 힘듦/불안 계열 단어 -> 감산
    결과를 0~100 사이로 잘라서 반환.
    """
    positive_words = ["좋아", "괜찮", "편안", "행복", "고마워", "도와줘서", "안심", "나아졌"]
    negative_words = ["짜증", "불안", "힘들", "지쳤", "우울", "죽고", "불편", "걱정", "아파", "싫어"]

    score = 50  # 중립 기준

    low = text.lower()

    for w in positive_words:
        if w in text:
            score += 8
    for w in negative_words:
        if w in text:
            score -= 8

    # 너무 안 튀게 clamp
    if score < 0:
        score = 0
    if score > 100:
        score = 100
    return score


def summarize_mood_for_user(user_id: int):
    """
    최근 7일 간의 유저 메시지를 불러와 평균 점수, 레벨, 조언을 만든다.
    또한 일자별 평균 점수 리스트를 만들어 그래프용으로 돌려준다.
    """
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    logs = (
        ChatLog.query
        .filter(ChatLog.user_id == user_id)
        .filter(ChatLog.role == "user")
        .filter(ChatLog.timestamp >= seven_days_ago)
        .order_by(ChatLog.timestamp.asc())
        .all()
    )

    if not logs:
        # 대화가 없다면 중립값
        avg_score = 50
        daily_points = []
    else:
        # 각 user 발화마다 점수 추정
        scored = [(log.timestamp.date(), estimate_mood_score_from_text(log.message)) for log in logs]

        # 날짜별 평균
        day_to_scores = {}
        for day, s in scored:
            day_to_scores.setdefault(day, []).append(s)

        daily_points = []
        for day, arr in day_to_scores.items():
            daily_points.append((day, sum(arr)/len(arr)))

        # 전체 평균
        all_scores = [s for (_, s) in scored]
        avg_score = sum(all_scores)/len(all_scores)

    # 등급/메시지
    if avg_score >= 70:
        level = "안정 상태"
        advice = "요즘 비교적 안정적으로 잘 버티고 있어요. 이 기분을 유지하려면 잘 쉬는 시간도 계속 챙겨줘요 🌱"
    elif avg_score >= 40:
        level = "주의 상태"
        advice = "조금은 부담이 쌓이는 중일 수 있어요. 혼자 참고 지나가지 말고, 짧게라도 털어놓을 상대를 확보해보자구요."
    else:
        level = "고위험 주의"
        advice = "지금은 많이 힘들 수 있어요. 혼자 끌어안고 있기엔 너무 버거운 감정이에요. 신뢰할 사람이나 전문 도움을 꼭 권할게요."

    # 반올림해서 깔끔하게
    avg_score = int(round(avg_score))

    # 일자별 그래프 데이터를 mood_graph.png 로 그리고 저장
    # daily_points는 [(date, score), ...]
    if daily_points:
        try:
            import matplotlib
            matplotlib.use("Agg")  # 서버용 백엔드
            import matplotlib.pyplot as plt

            dates = [str(d) for (d, _) in daily_points]
            vals = [v for (_, v) in daily_points]

            plt.figure()
            plt.plot(dates, vals, marker="o")
            plt.ylim(0, 100)
            plt.xlabel("날짜")
            plt.ylabel("감정 점수(0~100)")
            plt.title("최근 7일 감정 변화")

            os.makedirs("static", exist_ok=True)
            plt.savefig(os.path.join("static", "mood_graph.png"))
            plt.close()
            graph_available = True
        except Exception:
            # matplotlib 실패하더라도 앱이 죽으면 안 되니까
            graph_available = False
    else:
        graph_available = False

    return {
        "score": avg_score,
        "level": level,
        "advice": advice,
        "graph": graph_available,
    }


# ===================== 라우트 =====================

@app.route("/")
@login_required
def index():
    # 사용자별 최근 채팅 기록 불러오기
    from models import ChatLog  # 만약 app.py에 이미 있다면 생략
    user_logs = ChatLog.query.filter_by(user_id=current_user.id).order_by(ChatLog.timestamp.asc()).all()

    # JSON 변환용 리스트
    history = [{"role": log.role, "message": log.message} for log in user_logs]

    return render_template("index.html", username=current_user.username, history=history)



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("아이디와 비밀번호를 모두 입력해주세요.")
            return redirect(url_for("register"))

        # 중복 체크
        if User.query.filter_by(username=username).first() is not None:
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))

        new_user = User(username=username)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("가입 완료! 로그인 해주세요.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/chat", methods=["POST"])
@login_required
def chat():

    user_id = current_user.id

    # 폼에서 텍스트랑 이미지 둘 다 받을 수도 있으니까 안전하게 get()
    user_message = request.form.get("message", "").strip()

    # 이미지 업로드 처리
    image_file = request.files.get("image")
    bot_reply = ""

    if image_file and image_file.filename:
        # 파일명을 안전하게
        filename = secure_filename(image_file.filename)

        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(save_path)

        # 여기서는 단순히 "이미지 받았다" 라고만 응답.
        # 필요하면 classify_and_respond 안에 이미지 분석 붙일 수 있음.
        bot_reply = f"{filename} 이미지를 잘 받았어. (이미지 분석은 아직 준비 중이야)"
        # message 비어있을 수도 있으니 user_message가 완전 빈 문자열일 때는 로그용으로 대체 문자열 넣기
        if not user_message:
            user_message = f"[이미지 업로드: {filename}]"

    else:
        # 텍스트만 온 경우: 챗봇 응답 생성
        if user_message:
            bot_reply = classify_and_respond(user_message, user_id)
        else:
            # 아무것도 안 왔을 때 방어
            return jsonify({"response": "아무 내용도 받지 못했어 😥"}), 400

    # DB에 user / bot 로그 저장 (이제 여기서만)
    user_log = ChatLog(
        user_id=user_id,
        role="user",
        message=user_message,
        timestamp=datetime.utcnow(),
    )
    bot_log = ChatLog(
        user_id=user_id,
        role="bot",
        message=bot_reply,
        timestamp=datetime.utcnow(),
    )
    db.session.add(user_log)
    db.session.add(bot_log)
    db.session.commit()

    return jsonify({"response": bot_reply})


@app.route("/report")
@login_required
def report():

    mood_info = summarize_mood_for_user(current_user.id)

    return render_template(
        "result.html",
        username=current_user.username,
        score=mood_info["score"],
        level=mood_info["level"],
        advice=mood_info["advice"],
        graph=mood_info["graph"],
    )


# ===================== 초기화 편의 =====================
# 처음에 DB 없으면 생성 가능하게 해두는 옵션.
# Render 같은 곳에 올릴 땐 그냥 pass해도 되지만 로컬 디버깅에서는 편함.

with app.app_context():
    db.create_all()


# ===================== 엔트리포인트 =====================

if __name__ == "__main__":
    # 개발용 실행
    app.run(host="0.0.0.0", port=5000, debug=True)

