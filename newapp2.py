import re
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired
from pymongo import MongoClient
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
        
        if 'correct_choice' in request.form:
            # Handle multiple-choice question
            choices = request.form.getlist('choices[]')
            correct_choice_index = int(request.form.get('correct_choice'))
            correct_answer = choices[correct_choice_index]
            
            try:
                questions_template_collection.insert_one({
                    'question_template': text,
                    'question_type': 'multiple_choice',
                    'choices': choices,
                    'correct_answer': correct_answer
                })
                flash('Multiple-choice question saved successfully!', 'success')
            except Exception as e:
                flash('An error occurred while saving the question. Please try again.', 'error')
        else:
            # Handle written question
            answer = form.answer.data
            question_template = text
            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)

            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            evaluated_answer = evaluate_expression(answer, eval_context)

            try:
                questions_template_collection.insert_one({
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

    return render_template('index.html', form=form)


@app.route('/quiz_maker', methods=['GET', 'POST'])
def quiz_maker():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1}))
    template_options = [(str(template['_id']), template['question_template'], template['answer_template']) for template in templates]
    
    collections = mydb.list_collection_names()
    collections.remove('questions_template')

    # Query distinct categories from the "ชุดข้อสอบ" collection
    category_collection = mydb["ชุดข้อสอบ"]
    categories = category_collection.distinct('category')

    if request.method == 'POST':
        quiz_name = request.form.get('quiz_name')
        num_sets = int(request.form['num_sets'])
        collection_name = request.form.get('collection')
        new_collection_name = request.form.get('new_collection')
        
        category = request.form.get('category')
        new_category_name = request.form.get('new_category')
        
        if new_collection_name:
            collection_name = new_collection_name
        
        if new_category_name:
            category = new_category_name
        
        collection = mydb[collection_name]

        quiz_set = []

        question_index = 0
        while True:
            template_id = request.form.get(f'template_{question_index}')
            if template_id is None:
                break

            selected_template = questions_template_collection.find_one({'_id': ObjectId(template_id)})
            if selected_template:
                question_template = selected_template['question_template']
                answer_template = selected_template['answer_template']

                for _ in range(num_sets):
                    question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
                    eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
                    evaluated_answer = evaluate_expression(answer_template, eval_context)

                    quiz_set.append({
                        'question': question_text,
                        'answer': evaluated_answer,
                        **num_dict,
                        **opt_dict,
                        **person_dict,
                        **obj_dict
                    })
            else:
                flash('Please select a template for each question.', 'error')
                return redirect(url_for('quiz_maker'))

            question_index += 1

        collection.insert_one({
            'quiz_name': quiz_name,
            'category': category,  # Store the selected or created category
            'questions': quiz_set,
            'num_sets': num_sets,
        })

        flash('Quizzes generated successfully!', 'success')
        return redirect(url_for('quiz_maker'))

    return render_template('quiz_maker.html', templates=template_options, collections=collections, categories=categories)





@app.route('/create_exercise', methods=['GET', 'POST'])
def create_exercise():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1}))
    template_options = [(str(template['_id']), template['question_template'], template['answer_template']) for template in templates]
    
    if request.method == 'POST':
        template_id = request.form['template']
        selected_template = questions_template_collection.find_one({'_id': ObjectId(template_id)})

        if selected_template:
            question_template = selected_template['question_template']
            answer_template = selected_template['answer_template']

            question_text, num_dict, opt_dict, person_dict, obj_dict, numbers = process_question_template(question_template)
            rule_no_minus = '<rule.noMinus>' in answer_template
            if rule_no_minus:
                answer_template = answer_template.replace('<rule.noMinus>', '')

            eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
            evaluated_answer = evaluate_expression(answer_template, eval_context)

            while rule_no_minus and evaluated_answer < 0:
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

                eval_context = {**num_dict, **opt_dict, **person_dict, **obj_dict}
                evaluated_answer = evaluate_expression(answer_template, eval_context)

            generated_question = {
                'question': question_text,
                'answer': evaluated_answer,
                **num_dict,
                **opt_dict,
                **person_dict,
                **obj_dict
            }

            result = mydb['generated_questions'].insert_one(generated_question)

            return redirect(url_for('exercise', question_id=str(result.inserted_id)), code=303)
        
        flash('Selected template not found.', 'error')
        return redirect(url_for('create_exercise'))
    
    return render_template('create_exercise.html', templates=template_options)


@app.route('/exercise/<question_id>', methods=['GET', 'POST'])
def exercise(question_id):
    question = mydb['generated_questions'].find_one({'_id': ObjectId(question_id)})
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('index'))

    submitted = False
    user_answer = None
    correct_answer = None
    is_correct = False

    if request.method == 'POST':
        user_answer = request.form['answer']
        correct_answer = question['answer']
        is_correct = str(user_answer) == str(correct_answer)
        submitted = True

    return render_template('exercise.html', question=question, submitted=submitted, user_answer=user_answer, correct_answer=correct_answer, is_correct=is_correct)


@app.route('/submit_answer/<question_id>', methods=['POST'])
def submit_answer(question_id):
    user_answer = request.form['answer']
    return redirect(url_for('exercise', question_id=question_id, user_answer=user_answer))
@app.route('/view_templates', methods=['GET'])
def view_templates():
    templates = list(questions_template_collection.find({}, {'_id': 1, 'question_template': 1, 'answer_template': 1}))
    return render_template('view_templates.html', templates=templates)

@app.route('/edit_template/<template_id>', methods=['GET', 'POST'])
def edit_template(template_id):
    template = questions_template_collection.find_one({'_id': ObjectId(template_id)})

    if request.method == 'POST':
        question_template = request.form['question_template']
        answer_template = request.form['answer_template']
        
        questions_template_collection.update_one(
            {'_id': ObjectId(template_id)},
            {'$set': {'question_template': question_template, 'answer_template': answer_template}}
        )
        flash('Template updated successfully!', 'success')
        return redirect(url_for('view_templates'))

    return render_template('edit_template.html', template=template)

@app.route('/delete_template/<template_id>', methods=['POST'])
def delete_template(template_id):
    questions_template_collection.delete_one({'_id': ObjectId(template_id)})
    flash('Template deleted successfully!', 'success')
    return redirect(url_for('view_templates'))




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
