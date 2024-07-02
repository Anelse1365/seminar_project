from flask import Flask, render_template, request, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from pymongo import MongoClient
import re
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'

# MongoClient
myclient = MongoClient('mongodb+srv://admin:1234@cluster0.dvcham8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
mydb = myclient["mydb"]
questions_collection = mydb["questions"]

class NameForm(FlaskForm):
    quiz = StringField('Quiz', validators=[DataRequired()])
    answer = StringField('Answer', validators=[DataRequired()])
    submit = SubmitField('Submit')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = NameForm()
    if form.validate_on_submit():
        text = form.quiz.data
        answer = form.answer.data
        
        # ตรวจสอบและแยกข้อความที่ครอบด้วย <q></q>
        match_q = re.search(r'<q>(.*?)</q>', text)
        if match_q:
            question_text = match_q.group(1)
            
            # ตรวจสอบและแยกตัวเลขที่ครอบด้วย <numX></numX>
            num_pattern = re.compile(r'<num(\d+)>(.*?)</num\1>')
            numbers = num_pattern.findall(question_text)
            
            num_dict = {}  # Dictionary to store numX values
            
            for num_tag, number in numbers:
                if "random" in number:
                    params = number.split(',')
                    min_val = int(params[1])
                    max_val = int(params[2])
                    if len(params) == 4 and params[3] == 'odd':
                        number = random.choice([x for x in range(min_val, max_val + 1) if x % 2 != 0])
                    else:
                        number = random.randint(min_val, max_val)
                else:
                    number = int(number)
                
                # Replace <numX> with the value of number
                question_text = question_text.replace(f'<num{num_tag}>{number}</num{num_tag}>', str(number))
                
                # Add number to the dictionary
                num_dict[f'num{num_tag}'] = number

            # Insert the question and the numbers dictionary into the collection
            questions_collection.insert_one({'question': question_text, **num_dict})

        return redirect(url_for('index'))
    return render_template('index.html', form=form)

@app.route('/greet/<name>')
def greet(name):
    return render_template('greet.html', name=name)

if __name__ == '__main__':
    app.run(debug=True)
