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
        
        print(f"Received quiz: {text}")
        print(f"Received answer: {answer}")

        # ตรวจสอบและแยกข้อความที่ครอบด้วย <q></q>
        match_q = re.search(r'<q>(.*?)</q>', text)
        if match_q:
            question_text = match_q.group(1)
            
            print(f"Extracted question_text: {question_text}")

            # ตรวจสอบและแยกตัวเลขที่ครอบด้วย <numX,int></numX> หรือ <numX,int><random>...</random></numX>
            num_pattern = re.compile(r'<num(\d+),(\w+)>(.*?)</num\1>')
            numbers = num_pattern.findall(question_text)
            
            num_dict = {}  # Dictionary to store numX values

            for num_tag, num_type, content in numbers:
                if '<random>' in content:
                    random_expr = re.search(r'<random>(.*?)</random>', content).group(1)
                    if ',' in random_expr:
                        choices = list(map(int, random_expr.split(',')))
                    elif '-' in random_expr:
                        start, end = map(int, random_expr.split('-'))
                        choices = list(range(start, end + 1))
                    else:
                        choices = [int(random_expr)]
                    
                    number = random.choice(choices)
                else:
                    number = int(content)

                # Replace <numX,int> or <numX,int><random>...</random></numX> with the value of number
                question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
                
                # Add number to the dictionary
                num_dict[f'num{num_tag}'] = number

            print(f"Final question_text: {question_text}")
            print(f"Number dictionary: {num_dict}")

            # Evaluate the answer expression
            answer_expr = answer
            for num_tag, value in num_dict.items():
                answer_expr = answer_expr.replace(f'num{num_tag}', str(value))
            evaluated_answer = eval(answer_expr)

            print(f"Evaluated answer: {evaluated_answer}")

            # Insert the question, numbers dictionary, answer template, and evaluated answer into the collection
            questions_collection.insert_one({
                'question': question_text,
                'answer_template': answer,
                'answer': evaluated_answer,
                **num_dict
            })

        return redirect(url_for('index'))
    return render_template('index.html', form=form)

@app.route('/greet/<name>')
def greet(name):
    return render_template('greet.html', name=name)

if __name__ == '__main__':
    app.run(debug=True)
