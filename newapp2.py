from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, NumberRange
from pymongo import MongoClient
import re
import random


app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'

# MongoClient
myclient = MongoClient('mongodb+srv://admin:1234@cluster0.dvcham8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
mydb = myclient["mydb"]
questions_collection = mydb["questions"]
templates_collection = mydb["questions_template"]

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
            question_template = text

            match_q = re.search(r'<q>(.*?)</q>', text)
            if match_q:
                question_text = match_q.group(1)
                
                num_pattern = re.compile(r'<num(\d+),(int|float)>(.*?)</num\1>')
                numbers = num_pattern.findall(question_text)
                
                num_dict = {}

                for num_tag, num_type, content in numbers:
                    if '<random>' in content:
                        random_expr = re.search(r'<random>(.*?)</random>', content).group(1)
                        number = generate_random_number(random_expr, num_type)
                    else:
                        number = convert_to_type(content, num_type)

                    question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
                    num_dict[f'num{num_tag}'] = number

                opt_pattern = re.compile(r'<opt>(.*?)</opt>')
                operators = opt_pattern.findall(question_text)
                
                opt_dict = {}

                for idx, content in enumerate(operators):
                    if '<random>' in content:
                        random_expr = re.search(r'<random>(.*?)</random>', content).group(1)
                        operator = random.choice(random_expr.split(','))
                    else:
                        operator = content

                    question_text = question_text.replace(f'<opt>{content}</opt>', operator)
                    opt_dict[f'opt{idx}'] = operator

                eval_context = {**num_dict, **opt_dict}
                evaluated_answer = safe_eval(answer, eval_context)

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

@app.route('/quiz_maker', methods=['GET', 'POST'])
def quiz_maker():
    if request.method == 'POST':
        selected_template = request.form.get('template')
        num_sets = int(request.form.get('num_sets'))
        selected_collection = request.form.get('collection')
        new_collection_name = request.form.get('new_collection').strip()

        collection_name = selected_collection
        if new_collection_name:
            collection_name = new_collection_name

        if not collection_name:
            # Handle the case where no collection name is provided
            flash('Please select or enter a collection name.', 'error')
            return redirect(url_for('quiz_maker'))

        collection = mydb[collection_name]

        template = templates_collection.find_one({'_id': selected_template})
        if template:
            for _ in range(num_sets):
                question_text = template['question']
                num_dict = {k: generate_random_number(v, k.split('_')[1]) for k, v in template.items() if k.startswith('num')}
                opt_dict = {k: random.choice(v.split(',')) for k, v in template.items() if k.startswith('opt')}

                eval_context = {**num_dict, **opt_dict}
                evaluated_answer = safe_eval(template['answer_template'], eval_context)

                collection.insert_one({
                    'question_template': template['question_template'],
                    'question': question_text,
                    'answer_template': template['answer_template'],
                    'answer': evaluated_answer,
                    **num_dict,
                    **opt_dict
                })
            return redirect(url_for('quiz_maker'))

    templates = templates_collection.find()
    collections = mydb.list_collection_names()
    template_list = [(str(template['_id']), template['question_template'], template['answer_template']) for template in templates]
    return render_template('quiz_maker.html', templates=template_list, collections=collections)



def generate_random_number(expression, num_type):
    choices = []
    if ',' in expression:
        parts = expression.split(',')
        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                choices.extend(range(start, end + 1))
            else:
                choices.append(int(part))
    elif '-' in expression:
        start, end = map(int, expression.split('-'))
        choices = range(start, end + 1)
    else:
        choices = [int(expression)]

    number = random.choice(choices)
    return convert_to_type(number, num_type)

def convert_to_type(value, num_type):
    if num_type == 'int':
        return int(value)
    elif num_type == 'float':
        return float(value)

def safe_eval(expression, eval_context):
    return eval(expression, {"__builtins__": None}, eval_context)

if __name__ == '__main__':
    app.run(debug=True)
