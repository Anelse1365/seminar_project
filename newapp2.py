from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired
from pymongo import MongoClient
import re
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'

# MongoClient
myclient = MongoClient('mongodb+srv://admin:1234@cluster0.dvcham8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
mydb = myclient["mydb"]
questions_template_collection = mydb["questions_template"]
p_name_collection = mydb["p_name"]

class NameForm(FlaskForm):
    quiz = TextAreaField('Quiz', validators=[DataRequired()])
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

        # บันทึก template ของคำถาม
        question_template = text

        # Process the template to extract and replace dynamic content
        question_text, num_dict, opt_dict, person_dict, numbers = process_question_template(question_template)

        print(f"Final question_text: {question_text}")
        print(f"Number dictionary: {num_dict}")
        print(f"Operator dictionary: {opt_dict}")
        print(f"Person dictionary: {person_dict}")

        # ตรวจสอบและแยก <rule.noMinus>
        rule_no_minus = '<rule.noMinus>' in answer
        if rule_no_minus:
            answer = answer.replace('<rule.noMinus>', '')

        # Evaluate the answer expression using the num_dict and opt_dict as local variables
        eval_context = {**num_dict, **opt_dict, **person_dict}
        evaluated_answer = safe_eval(answer, eval_context)

        # ถ้า answer ยังติดลบอยู่ ให้สุ่มตัวเลขใหม่จนกว่า answer จะไม่ติดลบ
        while rule_no_minus and evaluated_answer < 0:
            for num_tag, num_type, content in numbers:
                random_match = re.search(r'<random(?:\.(odd|even))?>(.*?)</random>', content)
                if random_match:
                    condition = random_match.group(1)
                    random_expr = random_match.group(2)
                    number = generate_random_number(random_expr, num_type, condition)
                else:
                    number = convert_to_type(content, num_type)

                # Replace <numX,type> with the value of number
                question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
                
                # Add number to the dictionary
                num_dict[f'num{num_tag}'] = number

            # Re-evaluate the answer expression using the updated num_dict
            eval_context = {**num_dict, **opt_dict, **person_dict}
            evaluated_answer = safe_eval(answer, eval_context)

        print(f"Evaluated answer: {evaluated_answer}")

        # Insert the question, question template, numbers dictionary, answer template, evaluated answer, and operator dictionary into the collection
        try:
            questions_template_collection.insert_one({
                'question_template': question_template,
                'question': question_text,
                'answer_template': answer + ('<rule.noMinus>' if rule_no_minus else ''),
                'answer': evaluated_answer,
                **num_dict,
                **opt_dict,
                **person_dict
            })
            print("Document inserted successfully")
            flash('Template saved successfully!', 'success')
        except Exception as e:
            print(f"An error occurred: {e}")
            flash('An error occurred while saving the template. Please try again.', 'error')

        return redirect(url_for('index'))
    return render_template('index.html', form=form)

@app.route('/quiz_maker', methods=['GET', 'POST'])
def quiz_maker():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1}))
    template_options = [(str(template['_id']), template['question_template'], template['answer_template']) for template in templates]
    
    collections = mydb.list_collection_names()
    collections.remove('questions_template')  # Exclude the template collection from the options

    if request.method == 'POST':
        template_id = request.form['template']
        num_sets = int(request.form['num_sets'])
        collection_name = request.form.get('collection')
        new_collection_name = request.form.get('new_collection')
        
        if new_collection_name:
            collection_name = new_collection_name
        
        collection = mydb[collection_name]

        selected_template = questions_template_collection.find_one({'_id': ObjectId(template_id)})
        
        if selected_template:
            question_template = selected_template['question_template']
            answer_template = selected_template['answer_template']

            for _ in range(num_sets):
                # Generate new question and answer based on the template
                question_text, num_dict, opt_dict, person_dict, numbers = process_question_template(question_template)
                rule_no_minus = '<rule.noMinus>' in answer_template
                if rule_no_minus:
                    answer_template = answer_template.replace('<rule.noMinus>', '')

                eval_context = {**num_dict, **opt_dict, **person_dict}
                evaluated_answer = safe_eval(answer_template, eval_context)
                
                # ถ้า answer ยังติดลบอยู่ ให้สุ่มตัวเลขใหม่จนกว่า answer จะไม่ติดลบ
                while rule_no_minus and evaluated_answer < 0:
                    for num_tag, num_type, content in numbers:
                        random_match = re.search(r'<random(?:\.(odd|even))?>(.*?)</random>', content)
                        if random_match:
                            condition = random_match.group(1)
                            random_expr = random_match.group(2)
                            number = generate_random_number(random_expr, num_type, condition)
                        else:
                            number = convert_to_type(content, num_type)

                        # Replace <numX,type> with the value of number
                        question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
                        
                        # Add number to the dictionary
                        num_dict[f'num{num_tag}'] = number

                    # Re-evaluate the answer expression using the updated num_dict
                    eval_context = {**num_dict, **opt_dict, **person_dict}
                    evaluated_answer = safe_eval(answer_template, eval_context)

                # Insert the newly generated question and answer into the specified collection
                collection.insert_one({
                    'question': question_text,
                    'answer': evaluated_answer,
                    **num_dict,
                    **opt_dict,
                    **person_dict
                })
            flash('Quizzes generated successfully!', 'success')
        else:
            flash('Selected template not found.', 'error')

        return redirect(url_for('quiz_maker'))

    return render_template('quiz_maker.html', templates=template_options, collections=collections)

@app.route('/create_exercise', methods=['GET', 'POST'])
def exercise():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1}))
    template_options = [(str(template['_id']), template['question_template'], template['answer_template']) for template in templates]
    
    collections = mydb.list_collection_names()
    collections.remove('questions_template')  # Exclude the template collection from the options
    
    return render_template('create_exercise.html', templates=template_options, collections=collections)


def process_question_template(template):
    """
    Process the question template to generate a new question and return the question text, num_dict, opt_dict, and person_dict.
    """
    question_text = template
    
    print(f"Extracted question_text: {question_text}")

    # Extract and replace <numX,type></numX> tags
    num_pattern = re.compile(r'<num(\d+),(int|float)>(.*?)</num\1>')
    numbers = num_pattern.findall(question_text)
    
    num_dict = {}  # Dictionary to store numX values

    for num_tag, num_type, content in numbers:
        random_match = re.search(r'<random(?:\.(odd|even))?>(.*?)</random>', content)
        if random_match:
            condition = random_match.group(1)
            random_expr = random_match.group(2)
            number = generate_random_number(random_expr, num_type, condition)
        else:
            number = convert_to_type(content, num_type)

        # Replace <numX,type> with the value of number
        question_text = question_text.replace(f'<num{num_tag},{num_type}>{content}</num{num_tag}>', str(number))
        
        # Add number to the dictionary
        num_dict[f'num{num_tag}'] = number

    # Extract and replace <opt></opt> tags
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

    # Extract and replace <personX> tags
    person_pattern = re.compile(r'<person(\d+)>')
    persons = person_pattern.findall(question_text)
    
    person_dict = {}  # Dictionary to store personX values
    used_names = {}  # Dictionary to keep track of assigned names

    for person_tag in persons:
        if person_tag not in used_names:
            person_name = get_random_person_name(used_names.values())
            used_names[person_tag] = person_name
        else:
            person_name = used_names[person_tag]

        # Replace <personX> with the value of person_name
        question_text = question_text.replace(f'<person{person_tag}>', person_name)
        
        # Add person to the dictionary
        person_dict[f'person{person_tag}'] = person_name

    print(f"Final question_text: {question_text}")
    print(f"Number dictionary: {num_dict}")
    print(f"Operator dictionary: {opt_dict}")
    print(f"Person dictionary: {person_dict}")

    return question_text, num_dict, opt_dict, person_dict, numbers

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
    
    if condition:
        if condition == 'even':
            choices = [num for num in choices if num % 2 == 0]
        elif condition == 'odd':
            choices = [num for num in choices if num % 2 != 0]

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

def get_random_person_name(used_names):
    """
    Fetches a random name from the p_name collection that hasn't been used yet.
    """
    names = list(p_name_collection.find({}, {'_id': 0, 'name': 1}))
    available_names = [name['name'] for name in names if name['name'] not in used_names]
    
    if available_names:
        return random.choice(available_names)
    return "Unknown"

def safe_eval(expression, eval_context):
    """
    Evaluates the expression using the provided eval_context in a safe manner.
    """
    # Evaluate expression in a restricted environment
    return eval(expression, {"__builtins__": None}, eval_context)


if __name__ == '__main__':
    app.run(debug=True)
