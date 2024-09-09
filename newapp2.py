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
users = mydb["users"]
category_collection = mydb["ชุดข้อสอบ"]
active_questions_db = mydb['active_questions']

class NameForm(FlaskForm):
    quiz = TextAreaField('Quiz', validators=[DataRequired()])
    answer = StringField('Answer')
    submit = SubmitField('Submit')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('student_home'))
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/student_home')
def student_home():
    if 'username' not in session:
        return redirect(url_for('login'))

    student_id = session.get('username')

    # ดึงข้อมูล active_exercises ที่มีสถานะ 'กำลังใช้งาน' และ answer_history
    active_exercises = mydb['active_questions'].find({'status': 'กำลังใช้งาน'})
    completed_exercises = mydb['answer_history'].find({'student_id': student_id})

    completed_exercise_ids = [entry['exercise_id'] for entry in completed_exercises]

    exercises = []
    for exercise in active_exercises:
        quiz_id = exercise['quiz_set']
        quiz_name = exercise['quiz_name']
        expiration_date = exercise.get('expiration_date', None)

        # ตรวจสอบว่าหมดอายุหรือไม่
        expired = False
        if expiration_date:
            current_time = datetime.now(timezone(timedelta(hours=7)))  # ตั้งค่าเขตเวลา UTC+7
            expiration_date = expiration_date.astimezone(timezone(timedelta(hours=7)))
            expired = current_time > expiration_date

        # ตรวจสอบว่าผู้ใช้ทำ exercise เสร็จหรือยัง
        is_completed = quiz_id in completed_exercise_ids

        exercises.append({
            'quiz_name': quiz_name,
            'quiz_id': quiz_id,
            'expired': expired,
            'is_completed': is_completed,
            'expiration_date': expiration_date.strftime('%d/%m/%Y %H:%M') if expiration_date else None
        })

    return render_template('student_home.html', active_exercises=exercises)





@app.route('/', methods=['POST', 'GET'])
def login():
    error = None
    if request.method == 'POST':
        login_user = users.find_one({'username': request.form['username']})
        
        if login_user:
            if bcrypt.checkpw(request.form['password'].encode('utf-8'), login_user['password']):
                session['username'] = request.form['username']
                session['role'] = login_user.get('role', 'user')
                
                if session['role'] == 'admin':
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('student_home'))
        error = 'Invalid username/password'
    return render_template('login.html', error=error)


@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        existing_user = users.find_one({'username': request.form['username']})

        if existing_user is None:
            hashpass = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())
            users.insert_one({
                'username': request.form['username'],
                'password': hashpass,
                'role': 'admin' if request.form.get('is_admin') else 'user'
            })
            session['username'] = request.form['username']
            session['role'] = 'admin' if request.form.get('is_admin') else 'user'
            return redirect(url_for('student_home'))

        return 'That username already exists!'
    return render_template('register.html')

@app.route('/admin')
def admin():
    if 'username' in session and session['role'] == 'admin':
        return render_template('admin.html')
    return redirect(url_for('login'))

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
        # ตรวจสอบว่าหมวดหมู่ที่เลือกคือ 'new' หรือไม่
        selected_category = request.form.get('existing_category')
        new_category = request.form.get('new_category')

        if selected_category == 'new' and new_category:
            category = new_category
        else:
            category = selected_category

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
                    'answer_template': choices[correct_choice_index]
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
                    **obj_dict
                })
                flash('Written question saved successfully!', 'success')
            except Exception as e:
                flash('An error occurred while saving the question. Please try again.', 'error')

        return redirect(url_for('index'))

    return render_template('index.html', form=form, existing_categories=existing_categories)




@app.route('/quiz_maker', methods=['GET', 'POST'])
@admin_required
def quiz_maker():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1, 'choices_template': 1, 'question_type': 1}))
    template_options = [
        (str(template['_id']), template['question_template'], template.get('answer_template', ''), template.get('choices_template', []))
        for template in templates
    ]

    # Query distinct categories from the "ชุดข้อสอบ" collection
    category_collection = mydb["ชุดข้อสอบ"]
    categories = category_collection.distinct('category')

    if request.method == 'POST':
        quiz_name = request.form.get('quiz_name')
        category = request.form.get('category')
        new_category_name = request.form.get('new_category')

        if new_category_name:
            category = new_category_name

        # Use the "ชุดข้อสอบ" collection directly
        collection = mydb["ชุดข้อสอบ"]

        quiz_set = []

        question_index = 0
        while True:
            template_id = request.form.get(f'template_{question_index}')
            if template_id is None:
                break

            selected_template = questions_template_collection.find_one({'_id': ObjectId(template_id)})
            if selected_template:
                question_template = selected_template['question_template']
                answer_template = selected_template.get('answer_template', '')  # ใช้ .get() เพื่อป้องกัน KeyError
                choices_template = selected_template.get('choices_template', [])  # ดึงข้อมูล choices_template ถ้ามี

                question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
                eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
                evaluated_answer = evaluate_expression(answer_template, eval_context)

                # สร้างข้อมูลของ choices พร้อมแทนค่า
                evaluated_choices = []
                choice_labels = ['a', 'b', 'c', 'd', 'e']  # ป้ายกำกับตัวเลือก (ขึ้นอยู่กับจำนวน)
                for i, choice_template in enumerate(choices_template):
                    evaluated_choice = evaluate_expression(choice_template, eval_context)
                    evaluated_choices.append(f"{choice_labels[i]}. {evaluated_choice}")

                # สร้าง item ของ quiz
                quiz_item = {
                    'question': question_template,
                    'answer': answer_template,
                }

                # ตรวจสอบว่า question_type ไม่ใช่ 'written'
                if selected_template.get('question_type') != 'written':
                    quiz_item['choices'] = choices_template  # บันทึก choices ถ้าไม่ใช่ 'written'

                quiz_set.append(quiz_item)
            else:
                flash('Please select a template for each question.', 'error')
                return redirect(url_for('quiz_maker'))

            question_index += 1

        # Generate timestamp
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')

        collection.insert_one({
            'quiz_name': quiz_name,
            'category': category,  # Store the selected or created category
            'questions': quiz_set,
            'created_at': timestamp  # Add the timestamp here
        })

        flash('Quizzes generated successfully!', 'success')
        return redirect(url_for('quiz_maker'))

    return render_template('quiz_maker.html', templates=template_options, categories=categories)

@app.route('/active_exercise.html', methods=['GET', 'POST'])
def active_exercise():
    # ดึงข้อมูลจาก active_questions ทุกโจทย์
    active_exercises = list(active_questions_db.find())

    return render_template('active_exercise.html', active_exercises=active_exercises)
@app.route('/update_status/<exercise_id>', methods=['POST'])
def update_status(exercise_id):
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


@app.route('/view_submissions/<exercise_id>', methods=['GET'])
def view_submissions(exercise_id):
    # ดึงข้อมูลการส่งคำตอบจาก collection 'answer_history' โดยใช้ exercise_id
    submissions = list(mydb['answer_history'].find({'exercise_id': ObjectId(exercise_id)}))

    # ส่งข้อมูลไปยัง template view_submissions.html
    return render_template('view_submissions.html', submissions=submissions)

@app.route('/view_submission_details/<submission_id>', methods=['GET'])
def view_submission_details(submission_id):
    # ดึงข้อมูลคำตอบของนักเรียนจาก collection 'answer_history'
    submission = mydb['answer_history'].find_one({'_id': ObjectId(submission_id)})

    # ส่งข้อมูลไปยัง template view_submission_details.html
    return render_template('view_submission_details.html', submission=submission)

@app.route('/create_exercise', methods=['GET', 'POST'])
def create_exercise():
    quiz_sets = list(mydb['ชุดข้อสอบ'].find({}, {'_id': 1, 'quiz_name': 1, 'category': 1}))
    quiz_set_options = [
        (
            str(quiz_set['_id']),
            quiz_set.get('quiz_name', 'Unknown Quiz Name'),
            quiz_set.get('category', 'Unknown Category')
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
        quiz_set_id = request.form.get('quiz_set')
        shuffle_choices = 'shuffle_choices' in request.form
        view_mode = request.form.get('view_mode', 'template')

        # ตรวจสอบว่า quiz_set_id มีค่าและไม่เป็นค่า 'Select'
        if not quiz_set_id or quiz_set_id == 'Select':
            flash('Please select a quiz set before proceeding.', 'error')
            return render_template('create_exercise.html', 
                                   quiz_sets=quiz_set_options, 
                                   preview_questions=preview_questions, 
                                   selected_quiz_set=selected_quiz_set,
                                   shuffle_choices=shuffle_choices,
                                   view_mode=view_mode)

        try:
            selected_quiz_set = mydb['ชุดข้อสอบ'].find_one({'_id': ObjectId(quiz_set_id)})
        except errors.InvalidId:
            flash('Invalid quiz set selected. Please try again.', 'error')
            return render_template('create_exercise.html', 
                                   quiz_sets=quiz_set_options, 
                                   preview_questions=preview_questions, 
                                   selected_quiz_set=selected_quiz_set,
                                   shuffle_choices=shuffle_choices,
                                   view_mode=view_mode)

        if selected_quiz_set:
            questions = selected_quiz_set.get('questions', [])
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

            # ตรวจสอบว่ามี expiration_date ในฟอร์ม
            #แต่เดะกลับมาแก้สวนนี้ที่หลัง โคตรเลอะเทอะเลย
            expiration_date_str = request.form.get('expiration_date')
            if not expiration_date_str:
                return render_template('create_exercise.html', 
                                       quiz_sets=quiz_set_options, 
                                       preview_questions=preview_questions, 
                                       selected_quiz_set=selected_quiz_set,
                                       shuffle_choices=shuffle_choices,
                                       view_mode=view_mode)

            try:
                # แปลง expiration_date เป็น datetime ออบเจกต์
                expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Invalid expiration date format. Please try again.', 'error')
                return render_template('create_exercise.html', 
                                       quiz_sets=quiz_set_options, 
                                       preview_questions=preview_questions, 
                                       selected_quiz_set=selected_quiz_set,
                                       shuffle_choices=shuffle_choices,
                                       view_mode=view_mode)

            if 'generate_exercise' in request.form:
                exercise_data = {
                    'quiz_set': selected_quiz_set['_id'],
                    'quiz_name': selected_quiz_set['quiz_name'],
                    'category': selected_quiz_set['category'],
                    'created_date': datetime.now(),  # ใช้ `datetime` ออบเจกต์
                    'expiration_date': expiration_date,  # ใช้ `datetime` ออบเจกต์
                    'status': 'กำลังใช้งาน',
                    'scores': scores,
                    'submissions': 0  
                }
                mydb['active_questions'].insert_one(exercise_data)
                flash('Exercise created successfully!', 'success')
                return redirect(url_for('create_exercise'))

    return render_template('create_exercise.html', 
                           quiz_sets=quiz_set_options, 
                           preview_questions=preview_questions, 
                           selected_quiz_set=selected_quiz_set,
                           shuffle_choices=shuffle_choices,
                           view_mode=view_mode)


@app.route('/exercise/<quiz_id>', methods=['GET', 'POST'])
def exercise(quiz_id):
    # กำหนดค่าเริ่มต้นให้กับ expired
    expired = False
    # ดึงชุดข้อสอบที่เลือกจากฐานข้อมูล
    selected_quiz_set = mydb['ชุดข้อสอบ'].find_one({'_id': ObjectId(quiz_id)})

    # ดึงข้อมูล active exercise ที่เกี่ยวข้องกับ quiz_id
    active_exercise = mydb['active_questions'].find_one({'quiz_set': ObjectId(quiz_id)})

    
    # ตรวจสอบเวลาหมดอายุของข้อสอบ
    if active_exercise:
        expiration_date = active_exercise.get('expiration_date')
        if expiration_date:
            expiration_date = expiration_date.astimezone(timezone(timedelta(hours=7)))  # ตั้งเขตเวลาเป็น UTC+7

        current_time = datetime.now(timezone(timedelta(hours=7)))  # ตั้งเขตเวลาเป็น UTC+7

        # ตรวจสอบว่าข้อสอบหมดเวลาหรือยัง
        if expiration_date and current_time > expiration_date:
            expired = True  # ตั้ง expired เป็น True เมื่อหมดเวลา

    # เงื่อนไขเมื่อหมดอายุ ให้ส่งค่า expired ไปยัง template
    if expired:
        return render_template('exercise.html', 
                               quiz_id=quiz_id, 
                               questions=[], 
                               submitted=False, 
                               results=[], 
                               total_score=0, 
                               max_score=0, 
                               expired=expired)  # ส่งค่า expired=True

    questions = []
    results = []
    submitted = False
    total_score = 0
    max_score = 0

    if selected_quiz_set and active_exercise:
        raw_questions = selected_quiz_set.get('questions', [])
        scores = active_exercise.get('scores', [])  # ดึงคะแนนจาก active_exercises
        quiz_name = selected_quiz_set.get('quiz_name', 'Unknown')  # ดึงชื่อชุดข้อสอบ

        for index, question in enumerate(raw_questions):
            question_template = question['question']
            answer_template = question['answer']
            choices_template = question.get('choices', [])
            score = scores[index] if index < len(scores) else 1  # ใช้คะแนนจาก active_exercises ถ้ามี

            # ประมวลผลคำถาม
            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            answer = evaluate_expression(answer_template, eval_context)

            # ประมวลผลตัวเลือกหากมี
            choices = []
            if choices_template:
                for choice in choices_template:
                    choices.append(evaluate_expression(choice, eval_context))

            # เพิ่มคำถามพร้อมกับคะแนนไปยัง list
            questions.append({
                'question': question_text,
                'choices': choices,
                'answer': str(answer),
                'score': score
            })
            max_score += score  # เพิ่มคะแนนสูงสุดรวม

    # การจัดการการส่งคำตอบและคำนวณคะแนน
    if request.method == 'POST':
        student_id = session.get('username')  # ใช้ username จาก session
        student = mydb['users'].find_one({'username': student_id})  # ดึงข้อมูลนักเรียน
        
        # ตรวจสอบว่ามีข้อมูลของนักเรียนหรือไม่
        if student:
            student_name = f"{student.get('first_name', 'Unknown')} {student.get('last_name', 'Unknown')}"
            grade_level = student.get('grade_level', 'Unknown')
        else:
            student_name = "Unknown"
            grade_level = "Unknown"

        for i, question in enumerate(questions, start=1):
            # ดึงคำตอบของผู้ใช้
            if question['choices']:
                user_answer = request.form.get(f'question{i}')
            else:
                user_answer = request.form.get(f'answer_{i}')

            # ตรวจสอบคำตอบและคำนวณคะแนน
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

        # บันทึกผลการทำข้อสอบของนักเรียนลงใน answer_history
        if submitted:
            submission_data = {
                "exercise_id": ObjectId(quiz_id),  # อ้างอิงไปยัง active_questions
                "quiz_name": quiz_name,  # บันทึกชื่อของชุดข้อสอบ
                "student_id": student_id,
                "student_name": student_name,
                "grade_level": grade_level,
                "submission_date": datetime.now().strftime('%d/%m/%Y %H:%M'),
                "total_score": total_score,
                "max_score": max_score,
                "results": results
            }

            # ตรวจสอบว่าเป็นการส่งครั้งแรกของนักเรียนคนนั้นสำหรับข้อสอบนี้หรือไม่
            existing_submission = mydb['answer_history'].find_one({
                'exercise_id': ObjectId(quiz_id),
                'student_id': student_id
            })

            # หากยังไม่มี submission นี้ใน answer_history ให้บันทึกข้อมูลใหม่ และอัปเดต submissions
            if existing_submission is None:
                # บันทึกข้อมูล submission ลงใน answer_history
                mydb['answer_history'].insert_one(submission_data)
                
                # เพิ่มค่า submissions ใน active_questions ขึ้น 1
                mydb['active_questions'].update_one(
                    {'quiz_set': ObjectId(quiz_id)},
                    {'$inc': {'submissions': 1}}
                )


    return render_template('exercise.html',
                           quiz_id=quiz_id,
                           questions=questions,
                           submitted=submitted,
                           results=results,
                           total_score=total_score,
                           max_score=max_score)

@app.route('/submit_answer/<question_id>', methods=['POST'])
def submit_answer(question_id):
    user_answer = request.form['answer']
    return redirect(url_for('exercise', question_id=question_id, user_answer=user_answer))
@app.route('/view_templates', methods=['GET'])
def view_templates():
    templates = list(questions_template_collection.find({}, {
        '_id': 1,
        'question_template': 1,
        'answer_template': 1,
        'choices_template': 1,
        'choices': 1,
        'category': 1  # Add category field
    }))
    
    categories = questions_template_collection.distinct('category')  # Fetch distinct categories

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

@app.route('/view_user', methods=['GET', 'POST'])
def view_user():
    all_users = users.find({"role": {"$ne": "admin"}})  # Exclude admins

    if request.method == 'POST':
        if 'edit_user' in request.form:
            user_id = request.form['user_id']
            users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'username': request.form['username'],
                    'first_name': request.form['first_name'],
                    'last_name': request.form['last_name'],
                    'grade_level': request.form['grade_level']
                }}
            )
        elif 'delete_user' in request.form:
            user_id = request.form['user_id']
            users.delete_one({'_id': ObjectId(user_id)})
        else:
            existing_user = users.find_one({'username': request.form['username']})
            if existing_user is None:
                hashpass = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())
                users.insert_one({
                    'username': request.form['username'],
                    'password': hashpass,
                    'first_name': request.form['first_name'],
                    'last_name': request.form['last_name'],
                    'grade_level': request.form['grade_level'],
                    'role': 'user'
                })
            else:
                return 'That username already exists!'
        
        return redirect(url_for('view_user'))

    return render_template('view_user.html', users=all_users)

@app.route('/quiz_storage', methods=['GET'])
def quiz_storage():
    quizzes = list(mydb["ชุดข้อสอบ"].find({}, {
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
            return jsonify({"success": True, "message": "ชุดข้อสอบถูกลบสำเร็จ"})
        else:
            return jsonify({"success": False, "message": "ไม่พบชุดข้อสอบที่ต้องการลบ"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": f"เกิดข้อผิดพลาด: {str(e)}"}), 500
    






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
