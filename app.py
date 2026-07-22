import os
import secrets
from authlib.integrations.flask_client import OAuth
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'devi-computer-secret-key' # सेशन सुरक्षित रखने के लिए
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///institute.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Google Login Setup ---
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '867317038959-tg9dss8kn0dsgkbn4e7tmfelelh6noji.apps.googleusercontent.com')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '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')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- FLASK LOGIN SETUP ---
login_manager = LoginManager(app)
login_manager.login_view = 'login' # बिना लॉगिन के डैशबोर्ड खोलने पर यहाँ भेजेगा
login_manager.login_message = "Please log in to access this page."

@login_manager.user_loader
def load_user(user_id):
    return Institute.query.get(int(user_id))

# --- MODELS (मल्टी-यूजर / SaaS टेबल्स) ---
class Institute(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_name = db.Column(db.String(150), nullable=False)
    owner_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    subscription_plan = db.Column(db.String(50), default='Basic')
    is_whatsapp_enabled = db.Column(db.Boolean, default=False)
    
    courses = db.relationship('Course', backref='institute', lazy=True)
    students = db.relationship('Student', backref='institute', lazy=True)
    fees = db.relationship('FeeRecord', backref='institute', lazy=True)
    attendance = db.relationship('Attendance', backref='institute', lazy=True)

# --- 1. Course Model में बदलाव करें ---
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) 
    description = db.Column(db.Text, nullable=True) 
    duration = db.Column(db.String(50), nullable=True) # नया कॉलम
    total_fee = db.Column(db.Integer, nullable=False) 
    university_share = db.Column(db.Integer, nullable=False) 
    institute_share = db.Column(db.Integer, nullable=False)  
    institute_id = db.Column(db.Integer, db.ForeignKey('institute.id'), nullable=False)
    students = db.relationship('Student', backref='course', lazy=True)
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    admission_date = db.Column(db.DateTime, default=datetime.utcnow)
    institute_id = db.Column(db.Integer, db.ForeignKey('institute.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    fees = db.relationship('FeeRecord', backref='student', lazy=True)
    attendance = db.relationship('Attendance', backref='student', lazy=True)

class FeeRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount_paid = db.Column(db.Integer, nullable=False) 
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    institute_id = db.Column(db.Integer, db.ForeignKey('institute.id'), nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False) 
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    institute_id = db.Column(db.Integer, db.ForeignKey('institute.id'), nullable=False)

@app.route('/')
@login_required
def index():
    # 1. Total Students गिने
    total_students = Student.query.filter_by(institute_id=current_user.id).count()
    
    # 2. Total Pending Balance कैलकुलेट करें
    students = Student.query.filter_by(institute_id=current_user.id).all()
    total_pending_balance = 0
    
    for student in students:
        # अगर स्टूडेंट को कोर्स असाइन है, तो उसकी फीस निकालें
        if student.course:
            total_course_fee = student.course.total_fee
            total_paid = sum(fee.amount_paid for fee in student.fees)
            balance = total_course_fee - total_paid
            total_pending_balance += balance
            
    # डेटा को index.html पर भेजें
    return render_template('index.html', total_students=total_students, total_pending_balance=total_pending_balance)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
       return redirect(url_for('index'))
        
    if request.method == 'POST':
        i_name = request.form.get('institute_name')
        o_name = request.form.get('owner_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # चेक करें कि ईमेल पहले से मौजूद तो नहीं है
        user_exists = Institute.query.filter_by(email=email).first()
        if user_exists:
            flash('Email already registered! Please login.', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        # नया इंस्टीट्यूट बनाएँ
        new_institute = Institute(
            institute_name=i_name, 
            owner_name=o_name, 
            email=email, 
            password_hash=hashed_password,
            is_whatsapp_enabled=False # डिफ़ॉल्ट रूप से बंद
        )
        db.session.add(new_institute)
        db.session.commit()
        
        flash('Registration successful! You can now login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
     return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        institute = Institute.query.filter_by(email=email).first()
        
        # पासवर्ड चेक करें
        if institute and check_password_hash(institute.password_hash, password):
            login_user(institute)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password!', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- DASHBOARD ACTION ROUTES ---

# --- STUDENTS ADMISSION ROUTE ---
@app.route('/students', methods=['GET', 'POST'])
@login_required
def students():
    if request.method == 'POST':
        name = request.form.get('student_name')
        phone = request.form.get('phone')
        course_id = request.form.get('course_id')
        admission_date_str = request.form.get('admission_date') # फॉर्म से डेट निकालें
        
        # टेक्स्ट डेट ('YYYY-MM-DD') को Python की असली Date में बदलें
        if admission_date_str:
            admission_date = datetime.strptime(admission_date_str, '%Y-%m-%d')
        else:
            admission_date = datetime.utcnow()
            
        new_student = Student(
            name=name,
            phone=phone,
            course_id=course_id,
            admission_date=admission_date, # यहाँ बैक-डेट सेव होगी
            institute_id=current_user.id
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash('Student admitted successfully!', 'success')
        return redirect(url_for('students'))
        
    all_students = Student.query.filter_by(institute_id=current_user.id).all()
    all_courses = Course.query.filter_by(institute_id=current_user.id).all()
    
    # आज की डेट को फॉर्म में डिफ़ॉल्ट रूप से दिखाने के लिए
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('students.html', students=all_students, courses=all_courses, today_date=today_date)

# --- EDIT & DELETE STUDENTS ROUTES ---
@app.route('/edit_student/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)
    if student.institute_id != current_user.id:
        flash("You are not authorized to edit this student.", "error")
        return redirect(url_for('students'))
        
    if request.method == 'POST':
        student.name = request.form.get('student_name')
        student.phone = request.form.get('phone')
        student.course_id = request.form.get('course_id')
        
        admission_date_str = request.form.get('admission_date')
        if admission_date_str:
            student.admission_date = datetime.strptime(admission_date_str, '%Y-%m-%d')
            
        db.session.commit()
        flash('Student details updated successfully!', 'success')
        return redirect(url_for('students'))
        
    courses = Course.query.filter_by(institute_id=current_user.id).all()
    return render_template('edit_student.html', student=student, courses=courses)


@app.route('/delete_student/<int:id>')
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    if student.institute_id == current_user.id:
        db.session.delete(student)
        db.session.commit()
        flash('Student deleted successfully!', 'success')
    return redirect(url_for('students'))

# --- EDIT & DELETE COURSES ROUTES ---

@app.route('/edit_course/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_course(id):
    # डेटाबेस से वह कोर्स निकालें जिसे एडिट करना है
    course = Course.query.get_or_404(id)
    
    # सुरक्षा: चेक करें कि यह कोर्स इसी इंस्टिट्यूट का है
    if course.institute_id != current_user.id:
        flash("You are not authorized to edit this course.", "error")
        return redirect(url_for('courses'))
        
    if request.method == 'POST':
        course.name = request.form.get('course_name')
        course.description = request.form.get('description')
        course.duration = request.form.get('duration')
        course.total_fee = int(request.form.get('total_fee'))
        course.university_share = int(request.form.get('university_share'))
        course.institute_share = course.total_fee - course.university_share
        
        db.session.commit() # नए बदलाव सेव करें
        flash('Course updated successfully!', 'success')
        return redirect(url_for('courses'))
        
    return render_template('edit_course.html', course=course)

@app.route('/delete_course/<int:id>')
@login_required
def delete_course(id):
    course = Course.query.get_or_404(id)
    if course.institute_id == current_user.id:
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted successfully!', 'success')
    return redirect(url_for('courses'))

# --- FEES COLLECTION ROUTE ---
@app.route('/fees', methods=['GET', 'POST'])
@login_required
def fees():
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        amount_paid = int(request.form.get('amount_paid'))
        payment_date_str = request.form.get('payment_date')
        
        if payment_date_str:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
        else:
            payment_date = datetime.utcnow()
            
        new_fee = FeeRecord(
            student_id=student_id,
            amount_paid=amount_paid,
            payment_date=payment_date,
            institute_id=current_user.id
        )
        db.session.add(new_fee)
        db.session.commit()
        
        flash('Fee collected and receipt generated successfully!', 'success')
        return redirect(url_for('fees'))
        
    # GET रिक्वेस्ट के लिए:
    students_db = Student.query.filter_by(institute_id=current_user.id).all()
    
    # हर स्टूडेंट का बैलेंस कैलकुलेट करें ताकि हम उसे फॉर्म में दिखा सकें
    students_data = []
    for s in students_db:
        total_paid = sum(f.amount_paid for f in s.fees)
        balance = s.course.total_fee - total_paid
        students_data.append({
            'id': s.id,
            'name': s.name,
            'course_name': s.course.name,
            'total_fee': s.course.total_fee,
            'total_paid': total_paid,
            'balance': balance
        })
        
    # हाल ही में जमा हुई फीस का रिकॉर्ड (लेटेस्ट सबसे ऊपर)
    recent_fees = FeeRecord.query.filter_by(institute_id=current_user.id).order_by(FeeRecord.payment_date.desc()).all()
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('fees.html', students=students_data, recent_fees=recent_fees, today_date=today_date)

# --- 2. Courses Route में बदलाव करें ---
@app.route('/courses', methods=['GET', 'POST'])
@login_required
def courses():
    if request.method == 'POST':
        course_name = request.form.get('course_name')
        description = request.form.get('description')
        duration = request.form.get('duration') # <--- फॉर्म से ड्यूरेशन निकालें
        total_fee = int(request.form.get('total_fee'))
        university_share = int(request.form.get('university_share'))
        
        institute_share = total_fee - university_share
        
        new_course = Course(
            name=course_name,
            description=description,
            duration=duration, # <--- डेटाबेस में सेव करें
            total_fee=total_fee,
            university_share=university_share,
            institute_share=institute_share,
            institute_id=current_user.id
        )
        db.session.add(new_course)
        db.session.commit()
        
        flash('Course added successfully!', 'success')
        return redirect(url_for('courses'))
        
    all_courses = Course.query.filter_by(institute_id=current_user.id).all()
    return render_template('courses.html', courses=all_courses)

# --- ATTENDANCE ROUTE ---
@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    # डिफ़ॉल्ट रूप से आज की डेट दिखाएं, या URL से डेट लें
    selected_date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        form_date_str = request.form.get('attendance_date')
        form_date = datetime.strptime(form_date_str, '%Y-%m-%d').date()

        # सारे स्टूडेंट्स का लूप चलाकर उनका स्टेटस चेक करें
        students = Student.query.filter_by(institute_id=current_user.id).all()
        for student in students:
            # HTML फॉर्म से स्टेटस (Present/Absent) निकालें
            status = request.form.get(f'status_{student.id}')
            
            if status:
                # चेक करें कि क्या इस डेट की अटेंडेंस पहले से लगी हुई है
                existing_record = Attendance.query.filter_by(
                    student_id=student.id, 
                    date=form_date, 
                    institute_id=current_user.id
                ).first()

                if existing_record:
                    existing_record.status = status # अपडेट करें
                else:
                    new_attendance = Attendance(
                        student_id=student.id,
                        date=form_date,
                        status=status,
                        institute_id=current_user.id
                    )
                    db.session.add(new_attendance)

        db.session.commit()
        flash(f'Attendance saved successfully for {form_date_str}!', 'success')
        return redirect(url_for('attendance', date=form_date_str))

    # GET रिक्वेस्ट: स्टूडेंट्स और पहले से लगी अटेंडेंस निकालें
    students = Student.query.filter_by(institute_id=current_user.id).all()
    attendance_records = Attendance.query.filter_by(date=selected_date, institute_id=current_user.id).all()
    
    # एक डिक्शनरी बनाएं ताकि HTML में टिक (checked) दिखा सकें {student_id: 'Present'/'Absent'}
    attendance_map = {record.student_id: record.status for record in attendance_records}

    return render_template('attendance.html', 
                           students=students, 
                           selected_date=selected_date_str, 
                           attendance_map=attendance_map)

# --- PRINT RECEIPT ROUTE ---
@app.route('/print_receipt/<int:fee_id>')
@login_required
def print_receipt(fee_id):
    # डेटाबेस से वह फीस रिकॉर्ड निकालें
    fee = FeeRecord.query.get_or_404(fee_id)
    
    # सुरक्षा: चेक करें कि यह फीस इसी इंस्टिट्यूट की है
    if fee.institute_id != current_user.id:
        flash("You are not authorized to view this receipt.", "error")
        return redirect(url_for('fees'))
        
    return render_template('receipt.html', fee=fee)
# --- GOOGLE LOGIN ROUTES ---
@app.route('/login/google')
def google_login():
    # यह यूज़र को Google के लॉगिन पेज पर भेजेगा
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize/google')
def google_authorize():
    # Google लॉगिन होने के बाद वापस यहाँ डेटा भेजेगा
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    
    if not user_info:
        flash('Google login failed!', 'error')
        return redirect(url_for('login'))
        
    email = user_info['email']
    name = user_info.get('name', 'Google User')
    
    # चेक करें कि क्या यह ईमेल पहले से हमारे डेटाबेस में है
    institute = Institute.query.filter_by(email=email).first()
    
    if not institute:
        # अगर यूज़र नया है, तो उसका नया अकाउंट बना दें (Sign Up)
        # चूँकि पासवर्ड ज़रूरी है, हम एक रैंडम मजबूत पासवर्ड सेट कर देंगे
        random_password = secrets.token_hex(16)
        hashed_password = generate_password_hash(random_password, method='pbkdf2:sha256')
        
        institute = Institute(
            institute_name=name + "'s Institute", # डिफ़ॉल्ट नाम
            owner_name=name,
            email=email,
            password_hash=hashed_password,
            is_whatsapp_enabled=False
        )
        db.session.add(institute)
        db.session.commit()
    
    # यूज़र को लॉगिन कराएं
    login_user(institute)
    flash('Logged in successfully via Google!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
