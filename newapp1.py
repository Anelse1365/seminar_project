from flask import Flask, render_template, request, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from pymongo import MongoClient
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'

# MongoClient
myclient = MongoClient('localhost', 27017)
mydb = myclient["mydb"]
questions_collection = mydb["questions"]
numbers_collection = mydb["numbers"]

class NameForm(FlaskForm):
    name = StringField('Quiz', validators=[DataRequired()])
    submit = SubmitField('Submit')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = NameForm()
    if form.validate_on_submit():
        text = form.name.data
        
        # ตรวจสอบและแยกข้อความที่ครอบด้วย <q></q>
        match_q = re.search(r'<q>(.*?)</q>', text)
        if match_q:
            question_text = match_q.group(1)
            
            # ตรวจสอบและแยกตัวเลขที่ครอบด้วย <numX></numX>
            num_pattern = re.compile(r'<num(\d+)>(.*?)</num\1>')
            numbers = num_pattern.findall(question_text)
            
            for num_tag, number in numbers:
                # แทนที่ <numX> ด้วยค่าของ number
                question_text = question_text.replace(f'<num{num_tag}>{number}</num{num_tag}>', number)
                numbers_collection.insert_one({'number': int(number)})

            questions_collection.insert_one({'question': question_text})

        return redirect(url_for('index', name=text))
    return render_template('index.html', form=form)

@app.route('/greet/<name>')
def greet(name):
    return render_template('greet.html', name=name)

if __name__ == '__main__':
    app.run(debug=True)
