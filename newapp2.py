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
questions_collection = mydb["questions_template"]

class NameForm(FlaskForm):
    quiz = StringField('Quiz', validators=[DataRequired()])
    answer = StringField('Answer', validators=[DataRequired()])
    num_questions = StringField('Number of Questions', validators=[DataRequired()])
    submit = SubmitField('Submit')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = NameForm()
    if form.validate_on_submit():
        text = form.quiz.data
        answer = form.answer.data
        num_questions = int(form.num_questions.data)
        
        print(f"Received quiz: {text}")
        print(f"Received answer: {answer}")
        print(f"Number of questions: {num_questions}")

        for _ in range(num_questions):
            # บันทึก template ของคำถาม
            question_template = text

            # ตรวจสอบและแยกข้อความที่ครอบด้วย <q></q>
            match_q = re.search(r'<q>(.*?)</q>', text)
            if match_q:
                question_text = match_q.group(1)
                
                print(f"Extracted question_text: {question_text}")

                # ตรวจสอบและแยกตัวเลขที่ครอบด้วย <numX,type></numX>
                num_pattern = re.compile(r'<num(\d+),(int|float)>(.*?)</num\1>')
                numbers = num_pattern.findall(question_text)
                
                num_dict = {}  # Dictionary to store numX values

                for num_tag, num_type, content in numbers:
                    if '<random>' in content:
                        random_expr = re.search(r'<random>(.*?)</random>', content).group(1)
                        number = generate_random_number(random_expr, num_type)
                    else:
                        number = convert_to_type(content, num_type)

                    # Replace <numX,type> with the value of number
                    question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
                    
                    # Add number to the dictionary
                    num_dict[f'num{num_tag}'] = number

                # ตรวจสอบและแยก operator ที่ครอบด้วย <opt></opt>
                opt_pattern = re.compile(r'<opt>(.*?)</opt>')
                operators = opt_pattern.findall(question_text)
                
                opt_dict = {}  # Dictionary to store operators

                for idx, content in enumerate(operators):
                    if '<random>' in content:
                        random_expr = re.search(r'<random>(.*?)</random>', content).group(1)
                        operator = random.choice(random_expr.split(','))
                    else:
                        operator = content

                    # Replace <opt> with the value of operator
                    question_text = question_text.replace(f'<opt>{content}</opt>', operator)
                    
                    # Add operator to the dictionary
                    opt_dict[f'opt{idx}'] = operator

                print(f"Final question_text: {question_text}")
                print(f"Number dictionary: {num_dict}")
                print(f"Operator dictionary: {opt_dict}")

                # Evaluate the answer expression using the num_dict and opt_dict as local variables
                eval_context = {**num_dict, **opt_dict}
                evaluated_answer = safe_eval(answer, eval_context)

                print(f"Evaluated answer: {evaluated_answer}")

                # Insert the question, question template, numbers dictionary, answer template, evaluated answer, and operator dictionary into the collection
                questions_collection.insert_one({
                    'question_template': question_template,
                    'question': question_text,
                    'answer_template': answer,
                    'answer': evaluated_answer,
                    **num_dict,
                    **opt_dict
                })

        return redirect(url_for('index'))
    return render_template('index.html', form=form)

def generate_random_number(expression, num_type):
    """
    Generates a random number based on the expression.
    """
    choices = []
    if ',' in expression:
        # Handle lists of numbers
        parts = expression.split(',')
        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                choices.extend(range(start, end + 1))
            else:
                choices.append(int(part))
    elif '-' in expression:
        # Handle ranges
        start, end = map(int, expression.split('-'))
        choices = range(start, end + 1)
    else:
        # Single number
        choices = [int(expression)]

    number = random.choice(choices)
    return convert_to_type(number, num_type)

def convert_to_type(value, num_type):
    """
    Converts the value to the specified type (int or float).
    """
    if num_type == 'int':
        return int(value)
    elif num_type == 'float':
        return float(value)

def safe_eval(expression, eval_context):
    """
    Evaluates the expression using the provided eval_context in a safe manner.
    """
    # Evaluate expression in a restricted environment
    return eval(expression, {"__builtins__": None}, eval_context)

@app.route('/quiz_maker',methods=['GET', 'POST'] )
def quiz_maker():
    return render_template('quiz_maker.html')

if __name__ == '__main__':
    app.run(debug=True)
