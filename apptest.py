from threading import Thread

from flask import Flask
from flask import render_template, redirect, url_for, session
from flask import request
from flask_security import UserMixin, RoleMixin
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_manager, login_user, logout_user
from flask_security import Security, SQLAlchemySessionUserDatastore


import argparse
import io
from PIL import Image
#import datetime
from datetime import datetime

import torch
import cv2
import numpy as np
# import tensorflow as tf
from re import DEBUG, sub
from flask import send_file, Response
from werkzeug.utils import secure_filename, send_from_directory
#from flask import send_from_directory
import os
import subprocess
from subprocess import Popen
import re
import requests
import shutil
import time

from ultralytics import  YOLO

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://_bd_:_password_@localhost:5432/_bdName_"
# needed for session cookies
app.config['SECRET_KEY'] = 'MY_SECRET'
# hashes the password and then stores in the database
app.config['SECURITY_PASSWORD_SALT'] = "MY_SECRET"
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy()
db.init_app(app)

# runs the app instance
app.app_context().push()

roles_users = db.Table('roles_users',
                       db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
                       db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))


# create table in database for storing users
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    email = db.Column(db.String, unique=True)
    password = db.Column(db.String(255), nullable=False, server_default='')
    active = db.Column(db.Boolean())
    roles = db.relationship('Role', secondary=roles_users, backref='roled')
    user_predictions = db.relationship('Predictions', backref='list', lazy=True)

class Predictions(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    url = db.Column(db.String)
    date = db.Column(db.DateTime, index=True) #datetime.today().replace(microsecond=0)
    active = db.Column(db.Boolean())
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Classes(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    className = db.Column(db.String)
    probability = db.Column(db.Float)
    frame = db.Column(db.Integer())
    parent_id = db.Column(db.Integer, db.ForeignKey('predictions.id'), nullable=False)

class Role(db.Model, RoleMixin):
    __tablename__ = 'role'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)

# creates all database tables
@app.before_first_request
def create_tables():
    db.create_all()
    # db.session.add(Role(name="Admin"))
    # db.session.add(Role(name="User"))
    # db.session.commit()


user_datastore = SQLAlchemySessionUserDatastore(db.session, User, Role)
security = Security(app, user_datastore)


@app.route('/ind')
def index():
    return render_template("index.html")


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    msg = ""
    # if the form is submitted
    if request.method == 'POST':
        # check if user already exists
        user = User.query.filter_by(email=request.form['email']).first()
        msg = ""
        # if user already exists render the msg
        if user:
            msg = "User already exist"
            return render_template('signup.html', msg=msg)

        # if user doesn't exist
        user = User(email=request.form['email'], active=1, password=request.form['password'])
        role = Role.query.filter_by(id=1).first()
        user.roles.append(role)

        # commit the changes to database
        db.session.add(user)
        db.session.commit()

        # login the user to the app
        login_user(user)
        session["email"] = request.form['email']
        return redirect(url_for('history'))

    # case other than submitting form, like loading the page itself
    else:
        return render_template("signup.html", msg=msg)


@app.route('/signin', methods=['GET', 'POST'])
def signin():
    msg = ""
    if request.method == 'POST':
        # Поиск пользователя в БД
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            if user.password == request.form['password']:
                login_user(user)
                session["email"] = request.form['email']
                return redirect(url_for('history'))
            else:
                msg = "Wrong password"

        else:
            msg = "User doesn't exist"
        return render_template('signin.html', msg=msg)

    else:
        return render_template("signin.html", msg=msg)

@app.route('/logout2', methods=["GET"])
def logout2():
    print("email" in session)
    if "email" in session:
        # pop the user out of session
        session.pop("email", None)
        logout_user()
        #flash("You have been logged out!")
        resp = app.make_response(render_template('signin.html', status="disabled"))
        resp.set_cookie('token', expires=0)
        print(session)
        return resp
    else:
        #flash("You have been already logged out")
        session.pop("email", None)
        logout_user()
        resp = app.make_response(render_template('signin.html', status="disabled"))
        # expire the user session
        resp.set_cookie('token', expires=0)
        print(session)
        return redirect(url_for("signin"))

def get_frame():
    folder_path = 'runs'
    subfolders = [f for f in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, f))]
    latest_subfolder = max(subfolders, key=lambda x: os.path.getctime(os.path.join(folder_path, x)))
    filename = predict_img.imgpath
    image_path = folder_path+'/'+latest_subfolder+'/'+filename
    print(image_path)
    video = cv2.VideoCapture(image_path)
    while True:
        success, image = video.read()
        if not success:
            break
        ret, jpeg = cv2.imencode('.jpg', image)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        time.sleep(0.1)  #control the frame rate to display one frame every 100 milliseconds:


# function to display the detected objects video on html page
@app.route("/video_feed")
def video_feed():
    return Response(get_frame(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/<path:filename>')
def display(filename):
    folder_path = 'runs'
    subfolders = [f for f in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, f))]
    latest_subfolder = max(subfolders, key=lambda x: os.path.getctime(os.path.join(folder_path, x)))
    directory = folder_path+'/'+latest_subfolder
    print("printing directory: ",directory)
    print(predict_img)
    files = os.listdir(directory)
    latest_file = files[0]

    print(latest_file)
    print(filename)
    # filename = predict_img.imgpath
    file_extension = filename.rsplit('.', 1)[1].lower()
    #print("printing file extension from display function : ",file_extension)
    #print(directory,filename)
    environ = request.environ
    print("email" in session)
    if "email" in session:
        if file_extension == 'jpg' or file_extension == 'png' or file_extension == 'jpeg':
            return send_from_directory(directory,filename,environ)

    elif file_extension == 'mp4':
        return render_template('index2.html')

    else:
        return "Invalid file format"

@app.route('/image/<path:filename>')
def display_image(filename):
    folder_path = 'runs'
    file_extension = filename.rsplit('.', 1)[1].lower()
    #print("printing file extension from display function : ",file_extension)
    environ = request.environ
    #print(filename)
    if file_extension == 'jpg' or file_extension == 'png' or file_extension == 'jpeg':
        return send_from_directory(folder_path,filename,environ)

    else:
        return "Invalid file format"

@app.route('/video/<path:filename>', methods=["GET"])
def display_video(filename):
    folder_path = 'runs'
    directory = folder_path+'/'+ filename
    #print("printing directory: ",directory)
    file_extension = filename.rsplit('.', 1)[1].lower()
    environ = request.environ

    if file_extension == 'mp4':
        return send_from_directory(folder_path, filename, environ, as_attachment=True)
    else:
        return "Invalid file format"

@app.route("/")
def hello_world():
    return render_template('index2.html')

@app.route("/", methods=["GET", "POST"])
def predict_img():
    if request.method == "POST":
        if 'file' in request.files:
            f = request.files['file']
            basepath = os.path.dirname(__file__)
            filepath = os.path.join(basepath, 'uploads', f.filename)
            print("upload folder: ", filepath)
            f.save(filepath)

            predict_img.imgpath = f.filename
            print("img ::: ", predict_img)
            print("img ::: ", predict_img.imgpath)

            file_extension = f.filename.rsplit('.', 1)[1].lower()

            if file_extension == 'jpg':
                # img = cv2.imread(filepath)
                # frame = cv2.imencode('.jpg', cv2.UMat(img))[1].tobytes()
                #
                # image = Image.open(io.BytesIO(frame))
                #
                yolo = YOLO('best20.pt')
                detections = yolo.predict(filepath, save=True, project="runs")
                names = yolo.names

            if file_extension == 'mp4':
                video_path = filepath
                cap = cv2.VideoCapture(video_path)

                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height= int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter('output.mp4', fourcc, 30.0, (frame_width, frame_height))

                model = YOLO('bestv20.pt')
                detections = model.predict(video_path, save=True, project="runs")
                names = model.names

                # while cap.isOpened():
                #     ret,frame = cap.read()
                #     if not ret:
                #         break
                #     results = model(frame, save=True, project="runs")
                #     print(results)
                #     cv2.waitKey(1)
                #
                #     res_plotted = results[0].plot()
                #     cv2.imshow("result", res_plotted)
                #
                #     out.write(res_plotted)
                #
                #     if cv2.waitKey(1) == ord('q'):
                #         break

    folder_path = 'runs'
    subfolders = [f for f in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, f))]
    latest_subfolder = max(subfolders, key=lambda x: os.path.getctime(os.path.join(folder_path, x)))
    image_path = folder_path + '/' + latest_subfolder + '/' + f.filename
    print(image_path)
    email = session["email"]
    user_id = db.session.query(User.id).filter_by(email=email).scalar()
    predict = Predictions(url=latest_subfolder + '/' + f.filename, date=datetime.today().replace(microsecond=0),active=1,parent_id=user_id )
    db.session.add(predict)
    db.session.commit()

    last_id = db.session.query(Predictions.id).order_by(Predictions.id.desc()).first().id
    print("====================")
    print(last_id)
    cou1 = 0
    cou2 = 0
    for r in detections:
        cou1 = cou1 + 1
        for c, v in zip(r.boxes.cls, r.boxes.conf):
            print(c)
            print(names[int(c)], float(v))
            myclass = Classes(className=names[int(c)], probability=float(v), frame=cou1, parent_id=last_id)
            db.session.add(myclass)
            db.session.commit()
            cou2 = cou2 + 1
    print("===========")
    print(cou1, cou2)

    db.session.commit()
    if file_extension == 'jpg':
        return render_template('index2.html', image_path=image_path)
    if file_extension == 'mp4':
        return video_feed()
    else:
        return render_template('index2.html')
    # return "done"

myclass = ""
myprobability = ""

@app.route('/history', methods=["POST", "GET"])
def history():
    # если пользователь авторизован
    session.permanent = False
    print("email" in session)
    print(session)
    if "email" in session:
        email = session["email"]
        page = request.args.get('page', 1, type=int)
        myclass = request.form.get('myclass')
        myprobability = request.form.get('probability')
        print(myclass, myprobability)
        user_id = db.session.query(User.id).filter_by(email=email).scalar()
        loaded = False
        global user_posts
        if myclass != "" and myclass != None:
            if myprobability != "" and myprobability != None:
                user_posts = db.session.query(Predictions).join(Classes, Predictions.id == Classes.parent_id).filter(
                    Predictions.parent_id == user_id, Classes.className == myclass, Classes.probability >= myprobability).group_by(Predictions.id).order_by(
                    Predictions.date.desc()).paginate(page=page, per_page=100)
                loaded = True
            else:
                user_posts = db.session.query(Predictions).join(Classes, Predictions.id==Classes.parent_id).filter(Predictions.parent_id==user_id, Classes.className==myclass).group_by(Predictions.id).order_by(Predictions.date.desc()).paginate(page=page, per_page=100)
                loaded = True
        else:
            user_posts = db.session.query(Predictions).filter_by(parent_id=user_id).order_by(Predictions.date.desc()).paginate(page=page, per_page=100)
        print(loaded)
        if loaded == False:
            user_posts = db.session.query(Predictions).filter_by(parent_id=user_id).order_by(
                Predictions.date.desc()).paginate(page=page, per_page=100)
        return render_template('history.html', predictions=user_posts)
    else:
        return redirect(url_for("signin", status="disabled"))

#Delete Post
@app.route('/delete_post/<string:id>', methods=['POST'])
def delete_post(id):
    if "email" in session:
        db.session.query(Classes).filter_by(parent_id = id).delete()
        db.session.commit()

        db.session.query(Predictions).filter_by(id = id).delete()
        db.session.commit()
        return redirect(url_for("history"))
    else:
        return redirect(url_for("signin", status="disabled"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flask app yolo model")
    parser.add_argument("--port", default=5000, type=int, help="port number")
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port, threaded = True, debug = False)  # debug=True causes Restarting with stat