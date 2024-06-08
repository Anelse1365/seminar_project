from flask import Flask, render_template, request, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from pymongo import MongoClient
import random
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'

# MongoClient
myclient = MongoClient('localhost', 27017)
mydb = myclient["mydb"]

# Collection
questions_col = mydb["questions"]
things = mydb["things"]
x = mydb["x"]

class MyForm(FlaskForm):
    ans = StringField("คำตอบ", validators=[DataRequired()])
    submit = SubmitField("ส่ง")

@app.route('/', methods=['GET', 'POST'])
def test02():
    form = MyForm()
    correct_answer = None
    question = None
    if form.validate_on_submit():
        ans = form.ans.data
        question = request.form.get('question')  # รับคำถามจากฟอร์ม
        correct_answer = request.form.get('correct_answer')  # รับคำตอบที่ถูกต้องจากฟอร์ม
        if ans == correct_answer:
            return 'ถูกต้อง'
        else:
            return f"ไม่ถูกต้อง คำตอบที่ถูกต้องคือ {correct_answer}"
    else:
        # สุ่มคำถามเมื่อไม่มีการส่งคำตอบหรือการส่งคำตอบที่ผิด
        if not question:
            question = random.choice(list(questions_col.find()))
        return render_template('test02.html.html', form=form, question=question, correct_answer=question['correct_answer'])



@app.route('/add_question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        # Receive data from the form
        question_text = request.form['question_text']
        correct_answer_formula = request.form['correct_answer']

        # Random data
        things_name_cursor = things.find({}, {"name": 1, "_id": 0})
        things_names = [things['name'] for things in things_name_cursor]       
        x_name_cursor = x.find({}, {"name": 1, "_id": 0})
        x_name = [x['name'] for x in x_name_cursor]      
        obj = random.choice(things_names)
        p_name = random.choice(x_name)
        n1 = random.randint(1, 100)
        n2 = random.randint(1, n1)
        n3 = random.randint(1, n1)

        question_original = question_text

        # Add variables to the question text
        question_text = question_text.replace('<obj>', str(obj))
        question_text = question_text.replace('<n1>', str(n1))
        question_text = question_text.replace('<n2>', str(n2))
        question_text = question_text.replace('<n3>', str(n3))
        question_text = question_text.replace('<p_name>', str(p_name))

        # Parse and evaluate the correct answer formula
        parsed_formula = correct_answer_formula
        for var in re.findall(r'<\w+>', parsed_formula):
            if var == '<n1>':
                parsed_formula = parsed_formula.replace(var, str(n1))
            elif var == '<n2>':
                parsed_formula = parsed_formula.replace(var, str(n2))
            elif var == '<n3>':
                parsed_formula = parsed_formula.replace(var, str(n3))
        
        # Calculate correct answer
        correct_answer = eval(parsed_formula)


        # Add data to the database
        data_to_insert = {
            'question_text': question_text,
            'correct_answer': correct_answer
        }

        # ตรวจสอบว่าตัวแปร n1 และ n2 ถูกใช้ในคำถามหรือไม่
        if '<n1>' in question_original:
            data_to_insert['n1'] = n1
        if '<n2>' in question_original:
            data_to_insert['n2'] = n2
        if '<n3>' in question_original:
            data_to_insert['n3'] = n2

        # ตรวจสอบว่าตัวแปร obj และ p_name ถูกใช้ในคำถามหรือไม่
        if '<obj>' in question_original:
            data_to_insert['obj'] = obj
        if '<p_name>' in question_original:
            data_to_insert['p_name'] = p_name

        # แทรกข้อมูลลงในฐานข้อมูล
        questions_col.insert_one(data_to_insert)

        # questions_col.insert_one({
        #     'n1': n1,
        #     'obj': obj,
        #     'p_name': p_name,
        #     'n2': n2,
        #     'n3': n3,
        #     'question_text': question_text,
        #     'correct_answer': correct_answer
        # })

        return redirect(url_for('test02.html'))

    return render_template('add_question.html')

@app.route('/test01', methods=['GET', 'POST'])
def test01():

    return render_template('test01.html')

if __name__ == '__main__':
    app.run(debug=True)
