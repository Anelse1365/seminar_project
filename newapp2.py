import re
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash ,session, jsonify 
from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta
from bson import ObjectId, errors  # เพิ่ม errors สำหรับจัดการข้อผิดพลาด ObjectId
import random
import bcrypt
from functools import wraps



app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'
app.secret_key = 'secretkey'


# MongoClient
myclient = MongoClient('mongodb+srv://admin:1234@cluster0.dvcham8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
mydb = myclient["mydb"]
questions_template_collection = mydb["questions_template"]
p_name_collection = mydb["p_name"]
obj_db = mydb["obj"]
users = mydb["users"]
category_collection = mydb["ชุดข้อสอบ"]

active_questions_db = mydb['active_questions']
answer_history_db = mydb['answer_history']
answer_history = mydb['answer_history']

class NameForm(FlaskForm):
    quiz = TextAreaField('Quiz', validators=[DataRequired()])
    answer = StringField('Answer')
    submit = SubmitField('Submit')

# ฟังก์ชัน admin_required สำหรับหน้าที่ต้องการสิทธิ์ admin หรือ admin_0
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') not in ['admin']:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('student_home'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required_0(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') not in ['admin_0']:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('admin'))
        return f(*args, **kwargs)
    return decorated_function

def get_admin_id():
    """Helper function to retrieve the current admin's user_id from the session."""
    return session.get('user_id')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ตรวจสอบว่าผู้ใช้ล็อกอินหรือไม่ โดยเช็คจาก session
        if 'username' not in session:
            # ถ้าไม่ได้ล็อกอินให้ redirect ไปหน้า login
            flash('You need to log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
    


@app.route('/student_home')
@login_required  # ใช้ decorator เพื่อตรวจสอบการล็อกอิน
def student_home():
    student_id = session.get('username')

    # ดึงข้อมูลนักเรียนจากฐานข้อมูล
    student = mydb['users'].find_one({'username': student_id})
    if not student:
        return redirect(url_for('login'))  # ตรวจสอบว่ามีผู้ใช้หรือไม่

    student_grade_level = student.get('grade_level', 'Unknown')

    # ดึงข้อมูล active_exercises ที่มีสถานะ 'กำลังใช้งาน' และระดับชั้นตรงกับนักเรียน
    active_exercises = mydb['active_questions'].find({
        'status': 'กำลังใช้งาน',
        'grade_level': student_grade_level
    })
    
    # ดึงข้อมูลจาก answer_history โดยใช้ student_id
    completed_exercises = mydb['answer_history'].find({'student_id': student_id})

    # ตรวจสอบว่ามี active_questions_id หรือไม่ เพื่อป้องกัน KeyError
    completed_exercise_dict = {
        entry.get('active_questions_id'): entry for entry in completed_exercises if 'active_questions_id' in entry
    }

    exercises = []
    for exercise in active_exercises:
        quiz_id = exercise['_id']
        quiz_name = exercise['quiz_name']
        expiration_date = exercise.get('expiration_date', None)

        # ตรวจสอบว่าหมดอายุหรือไม่
        expired = False
        if expiration_date:
            current_time = datetime.now(timezone(timedelta(hours=7)))  # ตั้งค่าเขตเวลา UTC+7
            expiration_date = expiration_date.astimezone(timezone(timedelta(hours=7)))
            expired = current_time > expiration_date

        # ตรวจสอบว่าผู้ใช้ทำ exercise เสร็จหรือยัง
        is_completed = quiz_id in completed_exercise_dict
        score = None
        max_score = None

        # หากทำเสร็จแล้ว ดึงคะแนนจาก answer_history
        if is_completed:
            completed_exercise = completed_exercise_dict[quiz_id]
            score = completed_exercise.get('total_score', None)
            max_score = completed_exercise.get('max_score', None)

        exercises.append({
            'quiz_name': quiz_name,
            'quiz_id': quiz_id,
            'expired': expired,
            'is_completed': is_completed,
            'expiration_date': expiration_date.strftime('%d/%m/%Y %H:%M') if expiration_date else None,
            'score': score,
            'max_score': max_score
        })

    return render_template('student_home.html', active_exercises=exercises)

# ฟังก์ชัน login ที่เพิ่มการตรวจสอบบทบาท admin_0
@app.route('/', methods=['POST', 'GET'])
def login():
    error = None
    if request.method == 'POST':
        login_user = users.find_one({'username': request.form['username']})
        
        if login_user:
            if bcrypt.checkpw(request.form['password'].encode('utf-8'), login_user['password']):
                # บันทึก _id ของผู้ใช้ลงใน session
                session['user_id'] = str(login_user['_id'])
                session['username'] = request.form['username']
                session['role'] = login_user.get('role', 'user')
                
                if session['role'] in ['admin']:
                    return redirect(url_for('admin'))
                elif session['role'] == 'admin_0':
                    return redirect(url_for('admin0'))
                else:
                    return redirect(url_for('student_home'))
        error = 'Invalid username/password'
    return render_template('login.html', error=error)



# ฟังก์ชัน register ที่อนุญาตให้ admin_0 เข้าถึงเท่านั้น

@app.route('/register', methods=['POST', 'GET'])
@admin_required_0  # ตรวจสอบบทบาท admin_0
def register():
    # ดึงข้อมูลผู้ใช้ที่มีบทบาทเป็น 'admin'
    admins = users.find({'role': 'admin'})

    if request.method == 'POST':
        # Handle user creation
        if 'create_user' in request.form:
            existing_user = users.find_one({'username': request.form['username']})

            if existing_user is None:
                # เข้ารหัสรหัสผ่าน
                hashpass = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())

                # เพิ่มข้อมูลผู้ใช้ลงในฐานข้อมูล โดยระบุบทบาทเป็น 'admin'
                users.insert_one({
                    'username': request.form['username'],
                    'password': hashpass,
                    'role': 'admin',
                    'first_name': request.form['first_name'],
                    'last_name': request.form['last_name'],
                    'subject': request.form['subject'],
                    'subject_code': request.form['subject_code']
                })
                flash(f"Admin user {request.form['username']} created successfully.", 'success')
            else:
                flash('That username already exists!', 'error')

        # Handle user edit
        elif 'edit_user' in request.form:
            user_id = request.form['user_id']
            users.update_one(
                {'_id': ObjectId(user_id)},
                {
                    '$set': {
                        'username': request.form['username'],
                        'first_name': request.form['first_name'],
                        'last_name': request.form['last_name'],
                        'subject': request.form['subject'],
                        'subject_code': request.form['subject_code']
                    }
                }
            )
            flash(f"Admin user {request.form['username']} updated successfully.", 'success')

        # Handle user deletion
        elif 'delete_user' in request.form:
            user_id = request.form['user_id']
            users.delete_one({'_id': ObjectId(user_id)})
            flash("Admin user deleted successfully.", 'success')

        return redirect(url_for('register'))  # Redirect to the same page to refresh the admin list

    return render_template('register.html', admins=admins)




# ฟังก์ชัน admin ที่อนุญาตให้ทั้ง admin และ admin_0 เข้าถึง
@app.route('/admin')
def admin():
    if 'username' in session and session['role'] in ['admin', 'admin_0']:
        return render_template('admin.html')
    return redirect(url_for('student_home'))

@app.route('/admin0')
def admin0():
    if 'username' in session and session['role'] in ['admin_0']:
        return render_template('admin0.html')
    return redirect(url_for('student_home'))


@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    
    response = redirect(url_for('login'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/index', methods=['GET', 'POST'])
@admin_required
def index():
    form = NameForm()

    # ดึงหมวดหมู่ทั้งหมดจาก MongoDB
    existing_categories = questions_template_collection.distinct('category')

    if form.validate_on_submit():
        text = form.quiz.data
        selected_category = request.form.get('existing_category')
        new_category = request.form.get('new_category')

        if selected_category == 'new' and new_category:
            category = new_category
        else:
            category = selected_category

        admin_id = session.get('user_id')  # ดึง admin_id จาก session

        # ตรวจสอบว่าเป็น Multiple-choice หรือ Written question
        if 'correct_choice' in request.form:
            # Multiple-choice question
            choices = request.form.getlist('choices[]')
            correct_choice_index = int(request.form.get('correct_choice'))

            # Process and save the choices
            question_template = text
            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            evaluated_choices = [evaluate_expression(choice, eval_context) for choice in choices]
            correct_answer = evaluated_choices[correct_choice_index]

            try:
                questions_template_collection.insert_one({
                    'category': category,  # Save the category
                    'question': question_text,
                    'question_template': text,
                    'question_type': 'multiple_choice',
                    'choices_template': choices[:],
                    'choices': evaluated_choices,
                    'correct_answer': correct_answer,
                    'answer_template': choices[correct_choice_index],
                    'admin_id': ObjectId(admin_id)  # บันทึก admin_id ของ admin ที่สร้างคำถาม
                })
                flash('Multiple-choice question saved successfully!', 'success')
            except Exception as e:
                flash('An error occurred while saving the question. Please try again.', 'error')

        else:
            # Written question
            answer = form.answer.data
            if not answer:
                flash('Answer is required for written questions.', 'error')
                return render_template('index.html', form=form, existing_categories=existing_categories)

            question_template = text
            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            evaluated_answer = evaluate_expression(answer, eval_context)

            try:
                questions_template_collection.insert_one({
                    'category': category,  # Save the category
                    'question_template': question_template,
                    'question_type': 'written',
                    'question': question_text,
                    'answer_template': answer,
                    'answer': evaluated_answer,
                    **num_dict,
                    **opt_dict,
                    **person_dict,
                    **obj_dict,
                    'admin_id': ObjectId(admin_id)  # บันทึก admin_id ของ admin ที่สร้างคำถาม
                })
                flash('Written question saved successfully!', 'success')
            except Exception as e:
                flash('An error occurred while saving the question. Please try again.', 'error')

        return redirect(url_for('index'))

    return render_template('index.html', form=form, existing_categories=existing_categories)


@app.route('/quiz_maker', methods=['GET', 'POST'])
@admin_required
def quiz_maker():
    admin_id = session.get('user_id')  # ดึง admin_id จาก session

    # ดึงข้อมูล templates ที่สร้างโดย admin นี้จากฐานข้อมูล
    templates = list(questions_template_collection.find(
        {'admin_id': ObjectId(admin_id)},  # กรองตาม admin_id
        {'_id': 1, 'question_template': 1, 'answer_template': 1, 'choices_template': 1, 'question_type': 1}
    ))
    template_options = [
        (str(template['_id']), template['question_template'], template.get('answer_template', ''), template.get('choices_template', []))
        for template in templates
    ]

    # ดึงหมวดหมู่ที่ admin นี้สร้างจากคอลเลกชัน "ชุดข้อสอบ"
    category_collection = mydb["ชุดข้อสอบ"]
    categories = category_collection.distinct('category', {'admin_id': ObjectId(admin_id)})

    if request.method == 'POST':
        quiz_name = request.form.get('quiz_name')
        category = request.form.get('category')
        new_category_name = request.form.get('new_category')
        explanation = request.form.get('explanation')

        # ถ้ามีการสร้างหมวดหมู่ใหม่
        if new_category_name:
            category = new_category_name

        # ใช้คอลเลกชัน "ชุดข้อสอบ"
        collection = mydb["ชุดข้อสอบ"]

        quiz_set = []
        question_index = 0
        while True:
            template_id = request.form.get(f'template_{question_index}')
            if template_id is None:
                break

            if template_id:
                # ดึง template ที่เลือกจากฐานข้อมูล
                selected_template = questions_template_collection.find_one({'_id': ObjectId(template_id), 'admin_id': ObjectId(admin_id)})
                if selected_template:
                    question_template = selected_template['question_template']
                    answer_template = selected_template.get('answer_template', '')
                    choices_template = selected_template.get('choices_template', [])

                    # ประมวลผล template คำถาม
                    question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
                    eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
                    evaluated_answer = evaluate_expression(answer_template, eval_context)

                    # สร้างตัวเลือกสำหรับคำถาม
                    evaluated_choices = []
                    choice_labels = ['a', 'b', 'c', 'd', 'e']
                    for i, choice_template in enumerate(choices_template):
                        evaluated_choice = evaluate_expression(choice_template, eval_context)
                        evaluated_choices.append(f"{choice_labels[i]}. {evaluated_choice}")

                    quiz_item = {
                        'type': 'question',
                        'question': question_template,
                        'answer': answer_template,
                    }

                    if selected_template.get('question_type') != 'written':
                        quiz_item['choices'] = choices_template  # บันทึก choices ถ้ามี

                    quiz_set.append(quiz_item)

            question_index += 1

        # สร้าง timestamp
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')

        # บันทึกชุดคำถามและคำอธิบายลงในฐานข้อมูล
        collection.insert_one({
            'quiz_name': quiz_name,
            'category': category,  # บันทึกหมวดหมู่ที่เลือกหรือสร้างใหม่
            'explanation': explanation,  # บันทึกคำอธิบายแยกออกจากคำถาม
            'questions': quiz_set,
            'created_at': timestamp,  # บันทึกเวลา
            'admin_id': ObjectId(admin_id)  # บันทึก admin_id เพื่อระบุตัว admin ที่สร้าง
        })

        flash('Quizzes generated successfully!', 'success')
        return redirect(url_for('quiz_maker'))

    return render_template('quiz_maker.html', templates=template_options, categories=categories)




@app.route('/active_exercise.html', methods=['GET', 'POST'])
@admin_required
def active_exercise():
    # ดึง id ของ admin ที่ล็อกอินอยู่
    admin_id = get_admin_id()

    # ดึงข้อมูลเฉพาะข้อสอบที่สร้างโดย admin คนนั้น
    active_exercises = list(active_questions_db.find({'created_by':admin_id}))

    return render_template('active_exercise.html', active_exercises=active_exercises)

@app.route('/update_status/<exercise_id>', methods=['POST'])
@admin_required
def update_status(exercise_id):
    admin_id = get_admin_id()

    # ตรวจสอบว่า exercise ถูกสร้างโดย admin ที่ล็อกอินอยู่
    exercise = active_questions_db.find_one({'_id': ObjectId(exercise_id), 'created_by': admin_id})
    
    if not exercise:
        return 'Unauthorized', 403

    data = request.get_json()
    new_status = data.get('status')

    result = active_questions_db.update_one(
        {'_id': ObjectId(exercise_id)},
        {'$set': {'status': new_status}}
    )

    if result.matched_count > 0:
        return 'OK'
    else:
        return 'Failed', 400

# เพิ่ม route สำหรับอัปเดตวันหมดอายุ
@app.route('/update_expiration_date/<exercise_id>', methods=['POST'])
@admin_required
def update_expiration_date(exercise_id):
    data = request.get_json()
    new_expiration_date = data.get('expiration_date')

    # แปลง string ที่ได้รับเป็น datetime object
    try:
        new_expiration_date = datetime.strptime(new_expiration_date, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'error': 'รูปแบบวันที่ไม่ถูกต้อง'}), 400

    # อัปเดตวันหมดอายุในฐานข้อมูล
    result = active_questions_db.update_one(
        {'_id': ObjectId(exercise_id)},
        {'$set': {'expiration_date': new_expiration_date}}
    )

    if result.matched_count > 0:
        return 'OK'
    else:
        return 'Failed', 400


@app.route('/view_submissions/<active_questions_id>', methods=['GET'])
@admin_required
def view_submissions(active_questions_id):
    # ดึงข้อมูลการส่งคำตอบจาก collection 'answer_history' โดยใช้ active_questions_id
    submissions = list(mydb['answer_history'].find({
        'active_questions_id': ObjectId(active_questions_id)  # ใช้ active_questions_id แทน grade_level
    }))

    # ส่งข้อมูลไปยัง template view_submissions.html
    return render_template('view_submissions.html', submissions=submissions)




@app.route('/view_submission_details/<submission_id>', methods=['GET'])
@admin_required
def view_submission_details(submission_id):
    # ดึงข้อมูลคำตอบของนักเรียนจาก collection 'answer_history'
    submission = mydb['answer_history'].find_one({'_id': ObjectId(submission_id)})

    # ส่งข้อมูลไปยัง template view_submission_details.html
    return render_template('view_submission_details.html', submission=submission)


@app.route('/create_exercise', methods=['GET', 'POST'])
@admin_required
def create_exercise():
    admin_id = session.get('user_id')  # ดึง admin_id จาก session

    # ดึงเฉพาะ quiz sets ที่สร้างโดย admin ที่ล็อกอินอยู่
    quiz_sets = list(mydb['ชุดข้อสอบ'].find(
        {'admin_id': ObjectId(admin_id)},  # กรอง quiz sets ตาม admin_id
        {'_id': 1, 'quiz_name': 1, 'category': 1, 'explanation': 1}
    ))

    # ดึงข้อมูลระดับชั้นจากคอลเลคชัน 'users'
    grade_levels = mydb['users'].distinct('grade_level', {'admin_id': ObjectId(admin_id)})
    
    quiz_set_options = [
        (
            str(quiz_set['_id']),
            quiz_set.get('quiz_name', 'Unknown Quiz Name'),
            quiz_set.get('category', 'Unknown Category'),
            quiz_set.get('explanation', 'Unknown Quiz Name')
        )
        for quiz_set in quiz_sets
    ]

    selected_quiz_set = None
    preview_questions = []
    shuffle_choices = False
    view_mode = 'template'
    default_score = int(request.form.get('default_score', 1))
    scores = []

    if request.method == 'POST':
        # รับค่าชั่วโมงและนาทีจากฟอร์ม
        hours = int(request.form.get('hours', 0))
        minutes = int(request.form.get('minutes', 0))
        
        # คำนวณระยะเวลาทั้งหมดในหน่วยนาที
        duration_minutes = (hours * 60) + minutes

        quiz_set_id = request.form.get('quiz_set')
        grade_level = request.form.get('grade_level')  # ระดับชั้นที่เลือก
        shuffle_choices = 'shuffle_choices' in request.form
        view_mode = request.form.get('view_mode', 'template')

        # ตรวจสอบการเลือกชุดข้อสอบ
        if not quiz_set_id or quiz_set_id == 'Select':
            flash('Please select a quiz set before proceeding.', 'error')
            return render_template('create_exercise.html', 
                                quiz_sets=quiz_set_options, 
                                preview_questions=preview_questions, 
                                selected_quiz_set=selected_quiz_set,
                                grade_levels=grade_levels,
                                shuffle_choices=shuffle_choices,
                                view_mode=view_mode)

        # ดึงข้อมูลชุดข้อสอบจาก MongoDB
        try:
            selected_quiz_set = mydb['ชุดข้อสอบ'].find_one({'_id': ObjectId(quiz_set_id), 'admin_id': ObjectId(admin_id)})
        except errors.InvalidId:
            flash('Invalid quiz set selected. Please try again.', 'error')
            return render_template('create_exercise.html', 
                                quiz_sets=quiz_set_options, 
                                preview_questions=preview_questions, 
                                selected_quiz_set=selected_quiz_set,
                                grade_levels=grade_levels,
                                shuffle_choices=shuffle_choices,
                                view_mode=view_mode)

    # ดึงคำถามและคำอธิบายจากชุดข้อสอบที่เลือก
    if selected_quiz_set:
        questions = selected_quiz_set.get('questions', [])
        explanation = selected_quiz_set.get('explanation', '')
        for index, question in enumerate(questions, start=1):
            score = int(request.form.get(f'score_{index}', default_score))
            scores.append(score)

            question_text = question['question']
            answer = question['answer']
            choices = question.get('choices', [])

            if view_mode == 'processed':
                question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question['question'])
                eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
                answer = evaluate_expression(question['answer'], eval_context)
                choices = [evaluate_expression(choice, eval_context) for choice in choices]

            if shuffle_choices and choices:
                random.shuffle(choices)

            preview_questions.append({
                'question': question_text,
                'choices': choices,
                'answer': answer,
                'score': score
            })

        expiration_date_str = request.form.get('expiration_date')

        if not expiration_date_str:
            return render_template('create_exercise.html', 
                                   quiz_sets=quiz_set_options, 
                                   preview_questions=preview_questions, 
                                   selected_quiz_set=selected_quiz_set,
                                   grade_levels=grade_levels,
                                   shuffle_choices=shuffle_choices,
                                   view_mode=view_mode)

        try:
            expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid expiration date format. Please try again.', 'error')
            return render_template('create_exercise.html', 
                                   quiz_sets=quiz_set_options, 
                                   preview_questions=preview_questions, 
                                   selected_quiz_set=selected_quiz_set,
                                   explanation=explanation,  # ส่งคำอธิบายไปยังเทมเพลต
                                   shuffle_choices=shuffle_choices,
                                   view_mode=view_mode)

        # ตรวจสอบการกดปุ่ม generate_exercise
        if 'generate_exercise' in request.form:
            exercise_data = {
                'quiz_set': selected_quiz_set['_id'],
                'quiz_name': selected_quiz_set['quiz_name'],
                'category': selected_quiz_set['category'],
                'grade_level': grade_level,  # เปลี่ยนจาก grade_levels เป็น grade_level ที่เลือก
                'created_date': datetime.now(),
                'expiration_date': expiration_date,
                'status': 'กำลังใช้งาน',
                'scores': scores,
                'submissions': 0,
                'duration_minutes': duration_minutes,  # บันทึกระยะเวลาในหน่วยนาที
                'created_by': admin_id  # เก็บ id ของ admin ที่สร้างข้อสอบ
            }
            mydb['active_questions'].insert_one(exercise_data)
            flash('Exercise created successfully!', 'success')
            return redirect(url_for('create_exercise'))

    return render_template('create_exercise.html', 
                           quiz_sets=quiz_set_options, 
                           preview_questions=preview_questions, 
                           selected_quiz_set=selected_quiz_set,
                           grade_levels=grade_levels,
                           shuffle_choices=shuffle_choices,
                           view_mode=view_mode)


@app.route('/exercise/<quiz_id>', methods=['GET', 'POST'])
@login_required
def exercise(quiz_id):
    expired = False
    

    # ดึงข้อมูล active_exercise โดยใช้ quiz_id (ซึ่งเป็น _id ของ active_exercise)
    active_exercise = mydb['active_questions'].find_one({'_id': ObjectId(quiz_id)})

    if not active_exercise:
        return "ไม่พบ active exercise สำหรับข้อสอบนี้"

    # ดึง quiz_set_id จาก active_exercise
    quiz_set_id = active_exercise.get('quiz_set')
    if not quiz_set_id:
        return "ไม่พบชุดข้อสอบที่เกี่ยวข้อง"

    # ดึงชุดข้อสอบจากคอลเล็กชัน 'ชุดข้อสอบ' โดยใช้ quiz_set_id
    selected_quiz_set = mydb['ชุดข้อสอบ'].find_one({'_id': quiz_set_id})

    if not selected_quiz_set:
        return "ไม่พบชุดข้อสอบที่คุณเลือก"

    # ดึง explanation จาก selected_quiz_set
    explanation = selected_quiz_set.get('explanation', None)  # เพิ่มการดึง explanation

    # ดึงข้อมูลนักเรียนจาก session หรือฐานข้อมูล
    student_id = session.get('username')
    student = mydb['users'].find_one({'username': student_id})

    if student:
        student_name = f"{student.get('first_name', 'Unknown')} {student.get('last_name', 'Unknown')}"
        student_grade_level = student.get('grade_level', 'Unknown')
    else:
        student_name = "Unknown"
        student_grade_level = "Unknown"

    # ตรวจสอบว่าระดับชั้นของนักเรียนตรงกับ active_exercise หรือไม่
    if active_exercise.get('grade_level') != student_grade_level:
        return "คุณไม่มีสิทธิ์ทำข้อสอบชุดนี้"

    # ตรวจสอบว่ามีการทำข้อสอบ active_exercise นี้ไปแล้วหรือไม่
    active_exercise_id = active_exercise.get('_id')

    existing_submission = mydb['answer_history'].find_one({
        'active_questions_id': active_exercise_id,
        'student_id': student_id
    })

    if existing_submission:
        return "คุณได้ทำข้อสอบชุดนี้ไปแล้ว"

    # ตรวจสอบวันหมดอายุ
    expiration_date = active_exercise.get('expiration_date')
    if expiration_date:
        expiration_date = expiration_date.astimezone(timezone(timedelta(hours=7)))

    current_time = datetime.now(timezone(timedelta(hours=7)))

    if expiration_date and current_time > expiration_date:
        expired = True

    if expired:
        return render_template('exercise.html',
                               quiz_id=quiz_id,
                               questions=[],
                               submitted=False,
                               results=[],
                               total_score=0,
                               max_score=0,
                               expired=expired,
                               explanation=explanation)  # ส่ง explanation ไปยัง template

    questions = []
    results = []
    submitted = False
    total_score = 0
    max_score = 0
    
     # ดึงค่าระยะเวลา (เช่น 15 นาที) จาก active_exercise (เก็บเป็นนาที)
    duration_minutes = active_exercise.get('duration_minutes', 0)
    remaining_time = duration_minutes * 60  # แปลงเป็นวินาที
    
    if selected_quiz_set and active_exercise:
        raw_questions = selected_quiz_set.get('questions', [])
        scores = active_exercise.get('scores', [])
        quiz_name = selected_quiz_set.get('quiz_name', 'Unknown')

        for index, question in enumerate(raw_questions):
            question_template = question['question']
            answer_template = question['answer']
            choices_template = question.get('choices', [])
            score = scores[index] if index < len(scores) else 1

            # ประมวลผลคำถามและตัวเลือก
            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            answer = evaluate_expression(answer_template, eval_context)

            choices = []
            if choices_template:
                for choice in choices_template:
                    choices.append(evaluate_expression(choice, eval_context))

            questions.append({
                'question': question_text,
                'choices': choices,
                'answer': str(answer),
                'score': score
            })
            max_score += score

    if request.method == 'POST':
        time_taken = request.form.get('time_taken', '0')  # รับเวลาที่ใช้ในการทำข้อสอบ
        try:
            take_time = int(time_taken)
        except ValueError:
            take_time = 0  # กรณีแปลงไม่ได้ให้ค่าเป็น 0
            time_taken = request.form.get('time_taken', 0)  # รับเวลาที่ใช้ในการทำข้อสอบ

        for i, question in enumerate(questions, start=1):
            if question['choices']:
                user_answer = request.form.get(f'question{i}')
            else:
                user_answer = request.form.get(f'answer_{i}')

            if user_answer is not None:
                correct_answer = question['answer']
                is_correct = user_answer == correct_answer
                result_score = question['score'] if is_correct else 0
                total_score += result_score
                results.append({
                    'question': question['question'],
                    'user_answer': user_answer,
                    'correct_answer': correct_answer,
                    'is_correct': is_correct,
                    'score': result_score
                })
        submitted = len(results) > 0

        if submitted:
            submission_data = {
                "exercise_id": quiz_set_id,  # ใช้ quiz_set_id แทน
                "active_questions_id": active_exercise_id,
                "quiz_name": quiz_name,
                "student_id": student_id,
                "student_name": student_name,
                "grade_level": student_grade_level,
                "submission_date": datetime.now().strftime('%d/%m/%Y %H:%M'),
                "total_score": total_score,
                "max_score": max_score,
                "results": results,
                "time":duration_minutes * 60,
                "take_time": take_time  # เวลาที่ใช้จริงในการทำข้อสอบ
            }

            mydb['answer_history'].insert_one(submission_data)

            mydb['active_questions'].update_one(
                {'_id': active_exercise_id},
                {'$inc': {'submissions': 1}}
            )

    return render_template('exercise.html',
                           quiz_id=quiz_id,
                           questions=questions,
                           submitted=submitted,
                           results=results,
                           total_score=total_score,
                           duration_minutes=duration_minutes,
                           max_score=max_score,
                           explanation=explanation,remaining_time=int(remaining_time)
                           )  # ส่ง explanation ไปยัง template


@app.route('/submit_answer/<question_id>', methods=['POST'])
def submit_answer(question_id):
    user_answer = request.form['answer']
    return redirect(url_for('exercise', question_id=question_id, user_answer=user_answer))

@app.route('/view_templates', methods=['GET'])
@admin_required
def view_templates():
    # ดึง admin_id ของ admin ที่ล็อกอินอยู่จาก session
    admin_id = session.get('user_id')
    
    # ค้นหาเฉพาะ template ที่สร้างโดย admin คนนั้น
    templates = list(questions_template_collection.find(
        {'admin_id': ObjectId(admin_id)},  # กรองตาม admin_id
        {
            '_id': 1,
            'question_template': 1,
            'answer_template': 1,
            'choices_template': 1,
            'choices': 1,
            'category': 1  # Add category field
        }
    ))
    
    # ดึงเฉพาะ category ที่ admin คนนั้นสร้าง
    categories = questions_template_collection.distinct('category', {'admin_id': ObjectId(admin_id)})

    return render_template('view_templates.html', templates=templates, categories=categories)



@app.route('/edit_template/<template_id>', methods=['GET', 'POST'])
def edit_template(template_id):
    template = questions_template_collection.find_one({'_id': ObjectId(template_id)})

    if request.method == 'POST':
        question_template = request.form['question_template']
        answer_template = request.form['answer_template']
        choices_template = request.form.getlist('choices_template')
        choices = request.form.getlist('choices')

        questions_template_collection.update_one(
            {'_id': ObjectId(template_id)},
            {'$set': {
                'question_template': question_template,
                'answer_template': answer_template,
                'choices_template': choices_template,
                'choices': choices
            }}
        )
        flash('Template updated successfully!', 'success')
        return redirect(url_for('view_templates'))

    return render_template('edit_template.html', template=template)


@app.route('/delete_template/<template_id>', methods=['POST'])
def delete_template(template_id):
    questions_template_collection.delete_one({'_id': ObjectId(template_id)})
    flash('Template deleted successfully!', 'success')
    return redirect(url_for('view_templates'))
from itertools import groupby
from operator import itemgetter


@app.route('/view_user', methods=['GET', 'POST'])
@admin_required  # ให้เฉพาะ admin เท่านั้นที่เข้าถึงได้
def view_user():
    admin_id = session.get('user_id')  # ดึงค่า _id ของ admin จาก session

    # ตรวจสอบว่า admin_id มีค่าหรือไม่
    if not admin_id:
        flash('Admin ID not found. Please log in again.', 'error')
        return redirect(url_for('login'))

    # ค้นหาผู้ใช้ที่ไม่ได้เป็น admin และถูกสร้างโดย admin คนนี้
    all_users = list(users.find({"role": {"$ne": "admin"}, "admin_id": ObjectId(admin_id)}))

    if request.method == 'POST':
        if 'edit_user' in request.form:
            # แก้ไขข้อมูลผู้ใช้
            user_id = request.form['user_id']
            users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'username': request.form['username'],
                    'first_name': request.form['first_name'],
                    'last_name': request.form['last_name'],
                    'grade_level': request.form['grade_level'],
                    'number': request.form['number']
                }}
            )
            flash('User updated successfully!', 'success')
        elif 'delete_user' in request.form:
            # ลบผู้ใช้
            user_id = request.form['user_id']
            users.delete_one({'_id': ObjectId(user_id)})
            flash('User deleted successfully!', 'success')
        else:
            # ตรวจสอบว่ามี username นี้อยู่แล้วหรือไม่
            existing_user = users.find_one({'username': request.form['username']})
            if existing_user is None:
                # เข้ารหัสรหัสผ่านก่อนบันทึก
                hashpass = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())
                # สร้างผู้ใช้ใหม่
                users.insert_one({
                    'username': request.form['username'],
                    'password': hashpass,
                    'first_name': request.form['first_name'],
                    'last_name': request.form['last_name'],
                    'grade_level': request.form['grade_level'],
                    'number': int(request.form['number']),
                    'role': 'user',
                    'admin_id': ObjectId(admin_id)  # กำหนด admin_id ของผู้ใช้ใหม่ให้ตรงกับ admin ที่สร้าง
                })
                flash('User created successfully!', 'success')
            else:
                flash('That username already exists!', 'error')
                return redirect(url_for('view_user'))

        return redirect(url_for('view_user'))

    # จัดกลุ่มผู้ใช้ตาม grade_level
    all_users = sorted(all_users, key=itemgetter('grade_level'))  # ต้องจัดเรียงก่อนใช้ groupby
    users_by_grade = {k: list(g) for k, g in groupby(all_users, key=itemgetter('grade_level'))}

    return render_template('view_user.html', users_by_grade=users_by_grade)



@app.route('/quiz_storage', methods=['GET'])
@admin_required
def quiz_storage():
    # ดึง id ของ admin ที่ล็อกอินอยู่
    admin_id = get_admin_id()

    # ดึงข้อมูลเฉพาะข้อสอบที่สร้างโดย admin คนนั้น
    quizzes = list(mydb["ชุดข้อสอบ"].find({'admin_id': ObjectId(admin_id)}, {
        '_id': 1,
        'quiz_name': 1,
        'category': 1,
        'created_at': 1
    }))
    
    return render_template('quiz_storage.html', quizzes=quizzes)


@app.route('/quiz/<quiz_id>', methods=['GET', 'POST'])
def view_quiz(quiz_id):
    quiz = category_collection.find_one({'_id': ObjectId(quiz_id)})
    
    if request.method == 'POST':
        # Handle form submission to update quiz questions
        for i, question in enumerate(quiz['questions']):
            updated_question = request.form.get(f'question_{i}')
            updated_answer = request.form.get(f'answer_{i}')
            quiz['questions'][i]['question'] = updated_question
            quiz['questions'][i]['answer'] = updated_answer
            
            if 'choices' in question:
                updated_choices = request.form.getlist(f'choices_{i}')
                quiz['questions'][i]['choices'] = updated_choices
        
        category_collection.update_one({'_id': ObjectId(quiz_id)}, {'$set': quiz})
        return redirect(url_for('quiz_storage'))

    return render_template('view_quiz.html', quiz=quiz)

@app.route('/edit_quiz_name/<quiz_id>', methods=['POST'])
def edit_quiz_name(quiz_id):
    new_name = request.form['quiz_name']
    category_collection.update_one(
        {'_id': ObjectId(quiz_id)},
        {'$set': {'quiz_name': new_name}}
    )
    flash('Quiz name updated successfully!', 'success')
    return redirect(url_for('quiz_storage'))

@app.route('/delete_quiz/<quiz_id>', methods=['POST'])
def delete_quiz(quiz_id):
    category_collection.delete_one({'_id': ObjectId(quiz_id)})
    flash('Quiz deleted successfully!', 'success')
    return redirect(url_for('quiz_storage'))

# Route สำหรับลบชุดข้อสอบ
@app.route('/delete_exercise/<exercise_id>', methods=['POST'])
def delete_exercise(exercise_id):
    try:
        # ลบชุดข้อสอบโดยใช้ exercise_id
        result = active_questions_db.delete_one({"_id": ObjectId(exercise_id)})
        
        if result.deleted_count > 0:
            # ถ้าลบชุดข้อสอบสำเร็จ ให้ลบข้อมูลคำตอบใน answer_history ที่เชื่อมกับ active_questions_id นี้
            answer_history_db.delete_many({"active_questions_id": ObjectId(exercise_id)})
            
            return jsonify({"success": True, "message": "ชุดข้อสอบและคำตอบที่เกี่ยวข้องถูกลบสำเร็จ"})
        else:
            return jsonify({"success": False, "message": "ไม่พบชุดข้อสอบที่ต้องการลบ"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": f"เกิดข้อผิดพลาด: {str(e)}"}), 500
    
@app.route('/view_user_score', methods=['GET'])
@admin_required  # Only admin can access
def view_user_score():
    admin_id = session.get('user_id')  # Get admin ID from session

    # Get all users created by this admin
    all_users = list(users.find({"role": {"$ne": "admin"}, "admin_id": ObjectId(admin_id)}))

    # Get all quizzes created by this admin from active_questions
    active_quizzes = list(active_questions_db.find({'created_by': admin_id}))

    # Initialize a dictionary to store scores by student username
    scores_by_student = {}

    # Get the scores from answer_history and group them by student (using username)
    all_scores = list(answer_history.find({
        "active_questions_id": {"$in": [quiz['_id'] for quiz in active_quizzes]}
    }))

    # Create a dictionary to map each student's score for each quiz
    for score in all_scores:
        student_username = score['student_id']  # Use student_id (which is username in 'users')
        active_questions_id = score['active_questions_id']

        # Initialize the student's score dictionary if not exists
        if student_username not in scores_by_student:
            scores_by_student[student_username] = {}
        
        # Store the score for the corresponding quiz
        scores_by_student[student_username][str(active_questions_id)] = {
            "total_score": score['total_score'],
            "max_score": score['max_score']
        }

    # Group users by grade level
    users_by_grade = {}
    for user in all_users:
        grade_level = user['grade_level']
        if grade_level not in users_by_grade:
            users_by_grade[grade_level] = []
        users_by_grade[grade_level].append(user)

    # Pass both users and quizzes to the template
    return render_template('view_user_score.html', 
                           users_by_grade=users_by_grade,  
                           active_quizzes=active_quizzes, 
                           scores_by_student=scores_by_student)

@app.route('/data_variables', methods=['GET'])
def data_variables():
    # ดึงข้อมูลจาก MongoDB collections ทั้ง p_name และ obj
    p_name_data = list(p_name_collection.find())  # ดึงข้อมูล p_name ทั้งหมด
    obj_data = list(obj_db.find())  # ดึงข้อมูล obj ทั้งหมด
    
    return render_template('data_variables.html', p_name=p_name_data, obj=obj_data)

@app.route('/get_data/<data_type>', methods=['GET'])
def get_data(data_type):
    if data_type == 'person':
        # Fetch all documents from p_name_collection
        data = list(p_name_collection.find())  # Convert cursor to list
    elif data_type == 'object':
        # Fetch all documents from obj_db
        data = list(obj_db.find())  # Convert cursor to list
    else:
        return jsonify({"error": "Invalid data type"}), 400

    if data:
        # Remove the '_id' field from each document (if not needed)
        for doc in data:
            doc.pop('_id', None)
        return jsonify(data)
    
    return jsonify({"error": "No data found"}), 404

@app.route('/add_person', methods=['POST'])
def add_person():
    data = request.get_json()
    p_name_collection.insert_one({
        "name": data['name'],
        "gender": data['gender']
    })
    return jsonify({"success": True}), 200

@app.route('/add_object', methods=['POST'])
def add_object():
    data = request.get_json()
    obj_db.insert_one({
        "name": data['name'],
        "type": data['type'],
        "unit": data['unit']
    })
    return jsonify({"success": True}), 200

@app.route('/delete_person/<person_id>', methods=['DELETE'])
def delete_person(person_id):
    result = p_name_collection.delete_one({"_id": ObjectId(person_id)})
    if result.deleted_count > 0:
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 404

@app.route('/delete_object/<object_id>', methods=['DELETE'])
def delete_object(object_id):
    result = obj_db.delete_one({"_id": ObjectId(object_id)})
    if result.deleted_count > 0:
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 404

# Route สำหรับแก้ไขข้อมูล Person
@app.route('/update_person/<person_id>', methods=['PUT'])
def edit_person(person_id):
    data = request.get_json()
    updated_data = {
        "name": data['name'],
        "gender": data['gender']
    }
    result = p_name_collection.update_one({"_id": ObjectId(person_id)}, {"$set": updated_data})
    if result.modified_count > 0:
        return jsonify({"success": True})
    return jsonify({"success": False})

# Route สำหรับแก้ไขข้อมูล Object
@app.route('/update_object/<object_id>', methods=['PUT'])
def edit_object(object_id):
    data = request.get_json()
    updated_data = {
        "name": data['name'],
        "type": data['type'],
        "unit": data['unit']
    }
    result = obj_db.update_one({"_id": ObjectId(object_id)}, {"$set": updated_data})
    if result.modified_count > 0:
        return jsonify({"success": True})
    return jsonify({"success": False})



def process_question_template(template):
    question_text = template
    
    # Patterns for numbers, operators, persons, and objects
    num_pattern = re.compile(r'<num(\d+),(int|float)>(.*?)</num\1>')
    opt_pattern = re.compile(r'<opt>(.*?)</opt>')
    person_pattern = re.compile(r'<person(\d+)>')
    obj_pattern = re.compile(r'<obj(\d+),(.*?)>')

    # Dictionaries to store extracted values
    num_dict = {}
    opt_dict = {}
    person_dict = {}
    obj_dict = {}

    # Process numbers
    numbers = num_pattern.findall(question_text)
    for num_tag, num_type, content in numbers:
        random_match = re.search(r'<r(?:\.(odd|even))?>(.*?)</r>', content)
        if random_match:
            condition = random_match.group(1)
            random_expr = random_match.group(2)
            number = generate_random_number(random_expr, num_type, condition)
        else:
            number = convert_to_type(content, num_type)
        question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
        num_dict[f'num{num_tag}'] = number

    # Process operators
    operators = opt_pattern.findall(question_text)
    for idx, content in enumerate(operators):
        if '<r>' in content:
            random_expr = re.search(r'<r>(.*?)</r>', content).group(1)
            operator = random.choice(random_expr.split(','))
        else:
            operator = content
        question_text = question_text.replace(f'<opt>{content}</opt>', operator)
        opt_dict[f'opt{idx}'] = operator

    # Process persons
    persons = person_pattern.findall(question_text)
    used_names = {}
    for person_tag in persons:
        if person_tag not in used_names:
            person_name = get_random_person_name(used_names.values())
            used_names[person_tag] = person_name
        else:
            person_name = used_names[person_tag]
        question_text = question_text.replace(f'<person{person_tag}>', person_name)
        person_dict[f'person{person_tag}'] = person_name

    # Process objects
    objs = obj_pattern.findall(question_text)
    obj_names = {}  # Keep track of used object names to ensure unique selection
    for obj_tag, obj_type in objs:
        if obj_tag not in obj_dict:
            obj_doc = get_random_object_from_collection(obj_type, obj_names)
            obj_dict[obj_tag] = obj_doc
        else:
            obj_doc = obj_dict[obj_tag]
        
        obj_name = obj_doc['name']
        obj_unit = obj_doc['unit']
        question_text = question_text.replace(f'<obj{obj_tag},{obj_type}>', obj_name)
        question_text = question_text.replace(f'<obj{obj_tag}.last>', obj_unit)

    return question_text, num_dict, opt_dict, person_dict, obj_dict, numbers
    
def get_random_object_from_collection(obj_type, used_names):
    """
    Fetches a random document from the 'obj' collection where type == obj_type
    and the name has not been used yet.
    """
    query = {"type": obj_type}
    docs = list(mydb['obj'].find(query))
    if not docs:
        return {"name": "Unknown", "unit": "Unknown"}
    
    available_docs = [doc for doc in docs if doc['name'] not in used_names]
    if not available_docs:
        return {"name": "Unknown", "unit": "Unknown"}
    
    selected_doc = random.choice(available_docs)
    used_names[selected_doc['name']] = True  # Mark this object name as used
    return selected_doc


def generate_random_number(expression, num_type, condition=None):
    """
    Generates a random number based on the expression and the specified condition.
    """
    choices = []
    if ',' in expression:
        # Handle lists of numbers
        parts = expression.split(',')
        for part in parts:
            if '-' in part:
                start, end = map(float, part.split('-'))
                if num_type == 'int':
                    start, end = int(start), int(end)
                    choices.extend(range(start, end + 1))
                else:
                    choices.extend([start, end])  # For float, we just use start and end directly
            else:
                choices.append(float(part) if num_type == 'float' else int(part))
    elif '-' in expression:
        # Handle ranges
        start, end = map(float, expression.split('-'))
        if num_type == 'int':
            start, end = int(start), int(end)
            choices = range(start, end + 1)
        else:
            choices = [start, end]  # For float, we just use start and end directly
    else:
        # Single number
        choices = [float(expression) if num_type == 'float' else int(expression)]
    
    if condition:
        if condition == 'even':
            choices = [num for num in choices if int(num) % 2 == 0]
        elif condition == 'odd':
            choices = [num for num in choices if int(num) % 2 != 0]

    number = random.choice(choices)
    return convert_to_type(number, num_type)

def convert_to_type(value, num_type):
    """
    Converts the value to the specified type (int or float).
    """
    if num_type == 'int':
        return int(float(value))  # Ensure conversion to float first to handle cases like '1.5'
    elif num_type == 'float':
        return float(value)


def get_random_person_name(used_names):
    """
    Fetches a random name from the p_name collection that hasn't been used yet.
    """
    names = list(p_name_collection.find({}, {'_id': 0, 'name': 1}))
    available_names = [name['name'] for name in names if name['name'] not in used_names]
    
    if available_names:
        return random.choice(available_names)
    return "Unknown"

def evaluate_expression(expression, eval_context):
    """
    Evaluates the expression using the provided eval_context in a safe manner,
    processing any nested expressions like <num1+num2>.
    """
    def eval_nested_expr(match):
        nested_expr = match.group(1)
        return str(safe_eval(nested_expr, eval_context))

    # Check for number formatting
    nf_match = re.search(r'<nf\((\d+)\)>(.*?)</nf>', expression)
    if (nf_match):
        decimal_places = int(nf_match.group(1))
        inner_expr = nf_match.group(2)
        evaluated_inner_expr = evaluate_expression(inner_expr, eval_context)
        formatted_number = f"{float(evaluated_inner_expr):.{decimal_places}f}"
        expression = expression.replace(nf_match.group(0), formatted_number)
    
    return re.sub(r'<(.+?)>', eval_nested_expr, expression)

def safe_eval(expression, eval_context):
    """
    Evaluates the expression using the provided eval_context in a safe manner.
    """
    return eval(expression, {"__builtins__": None}, eval_context)



if __name__ == '__main__':
    app.run(debug=True)
    # app.run(host='0.0.0.0', port=5000)
