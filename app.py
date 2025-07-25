from flask import Flask, render_template, url_for, request, redirect,flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from livereload import Server
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from flask import jsonify
import os
from functools import wraps
from dotenv import load_dotenv
# from livereload import Server  # Temporarily commented out

# Load environment variables
load_dotenv()

# ================================
# App & Config Setup
# ================================
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Limiter setup
# Temporary just for testing will swap with redis later
limiter = Limiter(
    key_func=get_remote_address,  # limits based on IP address
    app=app,
    default_limits=[]  # no global limits
)

# Custom error response
@app.errorhandler(RateLimitExceeded)
def handle_rate_limit(e):
    # Render the login page with a special error and a cooldown flag
    cooldown = True
    # You can pass a cooldown time if you want to display a timer (e.g., e.reset_at)
    return render_template("login.html", error="Too many login attempts. Try again later.", cooldown=cooldown), 429

# Database Configuration - Using POSTGRESQL
DATABASE_URL = os.environ.get('DATABASE_URL') 
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') 

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================================
# Admin Required Decorator
# This decorator checks if the current user is logged in and has an 'admin' role.
# ================================
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not hasattr(current_user, 'role') or current_user.role != 'admin':
            flash("Access denied: Admins only.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ================================
# User Model Only
# ================================


# User model
# This model represents a user in the application, including their role
# and authentication details
class Users(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user', 'editor', 'admin'

# quiz model
# This model represents a quiz with its basic attributes
class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False, default='easy')  # 'easy', 'medium', 'hard'
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# question model
# This model represents a question in a quiz, including its options and the correct answer
class Questions(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    question_text = db.Column(db.String(500), nullable=False)
    options = db.Column(db.ARRAY(db.String(255)), nullable=False)
    answer_index = db.Column(db.Integer, nullable=False)  # Index of the correct answer in options

    # Relationship to Quizzes
    quiz = db.relationship('Quiz', backref=db.backref('questions', lazy=True, cascade="all, delete-orphan"))

# quiz results model
# This model stores the results of each quiz attempt by a user
class QuizResults(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    selected_index = db.Column(db.Integer, nullable=False)  # Index of the user's selected answer
    is_correct = db.Column(db.Boolean, nullable=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('Users', backref=db.backref('quiz_results', lazy=True))
    quiz = db.relationship('Quiz', backref=db.backref('results', lazy=True))
    question = db.relationship('Questions', backref=db.backref('results', lazy=True))

# quiz progress model
# This model tracks the progress of a user through a quiz
class QuizProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    last_question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    score = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship('Users', backref=db.backref('quiz_progress', lazy=True))
    quiz = db.relationship('Quiz', backref=db.backref('progress', lazy=True))
    question = db.relationship('Questions', backref=db.backref('progress', lazy=True))



# ================================
# Login Loader
# ================================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Users, int(user_id))



# ================================
# Routes (Login/Logout/Register/Profile Only)
# ================================

@app.route('/')
@app.route('/index')
def index():
    quizzes = Quiz.query.all()
    return render_template('index.html', quizzes=quizzes)

@app.route('/signup')
def signup():
    return render_template('register.html')


@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Hi this is TP and welcome to my app
        if not username or not email or not password or not confirm_password:
            return render_template("register.html", error="All fields are required!")

        if len(username) < 3:
            return render_template("register.html", error="Username must be at least 3 characters long!")

        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters long!")

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match!")

        # the following 2 if's make sure that duplicate usernames and emails are not allowed
        # throws error if the username or email already exists
        if Users.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already taken!")

        if Users.query.filter_by(email=email).first():
            return render_template("register.html", error="Email already registered!")

        try:
            # hashes the password using PBKDF2 with SHA-256
            # this makes sure that the user passwords are proteceted
            hashed_password = generate_password_hash(password, method="pbkdf2:sha256")
            new_user = Users(email=email, username=username, password=hashed_password, role='user')
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login", success="Account created successfully! Please log in."))
        
        except Exception as e:
            db.session.rollback()
            return render_template("register.html", error="Registration failed. Please try again!")

    return render_template("register.html")


# login route
# This route handles user login, including password verification and session management
@app.route('/login', methods=["GET", "POST"])
@limiter.limit("5 per minute,10 per 10 minute,20 per hour")  # Limit login attempts to prevent brute force attacks
def login():
    success_msg = request.args.get('success')
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = Users.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password!")

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    return render_template("login.html", success=success_msg)

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)


@app.route('/logout', methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))



# ================================
# Admin Panel Route
# ================================
# Ensure only users with 'admin' role can access this route
@app.route('/admin')
@admin_required
def admin_panel():
    return render_template('admin_panel.html')

# ================================
# Admin Management Routes
# ================================

@app.route('/manage_users')
@admin_required
def manage_users():
    users = Users.query.all()
    users = Users.query.order_by(Users.id.asc()).all()
    return render_template('manage_users.html', users=users)



@app.route('/manage_quizzes')
@admin_required
def manage_quizzes():
    quizzes = Quiz.query.all()
    return render_template('manage_quizzes.html', quizzes=quizzes)


# create_quiz route
@app.route('/create_quiz', methods=["POST"])
@admin_required
def create_quiz():
    quiz_name = request.form.get("quiz_name")
    quizzes = Quiz.query.all()  # Get quizzes for all error cases
    
    if not quiz_name:
        return render_template("manage_quizzes.html", quizzes=quizzes, error="Quiz name is required!")
    
    if len(quiz_name) < 3:
        return render_template("manage_quizzes.html", quizzes=quizzes, error="Quiz name must be at least 3 characters long!")
    
    if Quiz.query.filter_by(name=quiz_name).first():
        return render_template("manage_quizzes.html", quizzes=quizzes, error="Quiz with this name already exists!")
    
    try:
        new_quiz = Quiz(name=quiz_name, difficulty="easy", created_by=current_user.id)
        db.session.add(new_quiz)
        db.session.commit()
        return redirect(url_for("edit_quiz", quiz_id=new_quiz.id))
    except Exception as e:
        db.session.rollback()
        return render_template("manage_quizzes.html", quizzes=quizzes, error="Quiz creation failed. Please try again!")

# Edit quiz route (admin only)
@app.route('/edit_quiz/<int:quiz_id>', methods=["GET", "POST"])
@admin_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    error = None
    success = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_name":
            new_name = request.form.get("quiz_name")
            if new_name and new_name.strip():
                quiz.name = new_name.strip()
                db.session.commit()
                return redirect(url_for("edit_quiz", quiz_id=quiz.id))
        elif action == "add_question":
            question_text = request.form.get("question_text")
            # Normalize whitespace for each option
            options_raw = [request.form.get(f"option{i}") for i in range(1, 6)]
            options = []
            for opt in options_raw:
                if opt:
                    # Remove leading/trailing whitespace and collapse internal spaces
                    normalized = ' '.join(opt.split())
                    if normalized:
                        options.append(normalized)
            answer_index = request.form.get("answer_index")
            if question_text and len(options) >= 2 and len(options) <= 5 and answer_index is not None:
                # Check for non-identical options (after normalization)
                if len(set(options)) != len(options):
                    error = "All options must be unique."
                else:
                    try:
                        answer_index = int(answer_index)
                        if answer_index < 0 or answer_index >= len(options):
                            error = "Invalid answer index."
                        else:
                            new_q = Questions(quiz_id=quiz.id, question_text=question_text, options=options, answer_index=answer_index)
                            db.session.add(new_q)
                            db.session.commit()
                            return redirect(url_for("edit_quiz", quiz_id=quiz.id))
                    except Exception as e:
                        db.session.rollback()
                        error = "Failed to add question."
            else:
                error = "A question must have 2-5 options and a correct answer."
    questions = Questions.query.filter_by(quiz_id=quiz.id).all()
    return render_template("edit_quiz.html", quiz=quiz, questions=questions, error=error, success=success)

# Delete quiz route (admin only)
@app.route('/delete_quiz/<int:quiz_id>', methods=["POST"])
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get(quiz_id)
    if quiz:
        db.session.delete(quiz)
        db.session.commit()
        return redirect(url_for("manage_quizzes"))
    return "Quiz not found", 404


# Edit a question (admin only)
@app.route('/edit_question/<int:question_id>', methods=["GET", "POST"])
@admin_required
def edit_question(question_id):
    question = Questions.query.get_or_404(question_id)
    quiz = Quiz.query.get_or_404(question.quiz_id)
    error = None
    success = None
    if request.method == "POST":
        question_text = request.form.get("question_text")
        options = [request.form.get(f"option{i}") for i in range(1, 6) if request.form.get(f"option{i}")]
        answer_index = request.form.get("answer_index")
        if question_text and len(options) >= 2 and len(options) <= 5 and answer_index is not None:
            try:
                answer_index = int(answer_index)
                if answer_index < 0 or answer_index >= len(options):
                    error = "Invalid answer index."
                else:
                    question.question_text = question_text
                    question.options = options
                    question.answer_index = answer_index
                    db.session.commit()
                    success = "Question updated."
            except Exception as e:
                db.session.rollback()
                error = "Failed to update question."
        else:
            error = "A question must have 2-5 options and a correct answer."
    return render_template("edit_question.html", question=question, quiz=quiz, error=error, success=success)

# Update a question inline Form submission with template rendering
@app.route('/update_question_inline/<int:question_id>', methods=["POST"])
@admin_required
def update_question_inline(question_id):
    question = Questions.query.get_or_404(question_id)
    quiz = Quiz.query.get_or_404(question.quiz_id)
    
    try:
        # Handle form submission
        question_text = request.form.get("question_text", "").strip()
        options = []
        
        # Collect dynamic options from form
        i = 0
        while True:
            option = request.form.get(f"option_{i}", "")
            if option and option.strip():
                options.append(option.strip())
            i += 1
            if i > 10:  # Safety limit
                break
        
        answer_index = request.form.get("answer_index")
        if answer_index is not None:
            try:
                answer_index = int(answer_index)
            except:
                answer_index = None
        
        # Validation with template rendering
        questions = Questions.query.filter_by(quiz_id=quiz.id).all()
        
        if not question_text:
            return render_template("edit_quiz.html", quiz=quiz, questions=questions, error="Question text is required.")
        
        if len(options) < 2:
            return render_template("edit_quiz.html", quiz=quiz, questions=questions, error="At least 2 options are required.")
        
        if len(options) > 5:
            return render_template("edit_quiz.html", quiz=quiz, questions=questions, error="Maximum 5 options allowed.")
        
        # Check for duplicate options
        if len(set(options)) != len(options):
            return render_template("edit_quiz.html", quiz=quiz, questions=questions, error="All options must be unique.")
        
        if answer_index is None or answer_index < 0 or answer_index >= len(options):
            return render_template("edit_quiz.html", quiz=quiz, questions=questions, error="Invalid correct answer selection.")
        
        # Update the question
        question.question_text = question_text
        question.options = options
        question.answer_index = answer_index
        db.session.commit()
        
        # Success response with template rendering
        success_msg = "Question updated successfully."
        questions = Questions.query.filter_by(quiz_id=quiz.id).all()
        return render_template("edit_quiz.html", quiz=quiz, questions=questions, success=success_msg)
    
    except Exception as e:
        db.session.rollback()
        error_msg = "Failed to update question."
        questions = Questions.query.filter_by(quiz_id=quiz.id).all()
        return render_template("edit_quiz.html", quiz=quiz, questions=questions, error=error_msg)

# Delete a question (admin only)
@app.route('/delete_question/<int:question_id>', methods=["POST"])
@admin_required
def delete_question(question_id):
    question = Questions.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for("edit_quiz", quiz_id=quiz_id))



# ===============================
# User Management Routes
# ===============================

@app.route('/edit_user/<int:user_id>', methods=["POST"])
@admin_required
def edit_user(user_id):
    new_role = request.form.get("role")
    user = Users.query.get(user_id)

    if user:
        user.role = new_role
        db.session.commit()
        return redirect(url_for("manage_users"))
    return "User not found", 404

@app.route('/delete_user/<int:user_id>', methods=["POST"])
@admin_required
def delete_user(user_id):
    user = Users.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return redirect(url_for("manage_users"))
    return "User not found", 404

# ================================
# Quiz Routes
# ================================

@app.route('/quiz/<int:quiz_id>')
@login_required  # Optional: remove if you want quizzes public
def quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    return render_template('quiz.html', quiz=quiz)



# ================================
# DB Init (Users table only)
# ================================
with app.app_context():
    db.create_all()
    print("✅ Users table created.")

# ================================
# Run Appit
# ================================
if __name__ == "__main__":
    # Using livereload server for live reloading
    server = Server(app.wsgi_app)
    server.serve(open_url_delay=True, debug=True)