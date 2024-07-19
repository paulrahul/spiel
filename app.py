import os, sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from flask import Flask, abort, redirect, render_template, request, url_for, jsonify
from functools import wraps
from werkzeug.utils import redirect
import uuid

from .spiel import DeutschesSpiel
from .translation_compiler import Compiler

spiel = DeutschesSpiel(use_semantic=False, use_multimode=True)

# Generate a unique session ID when the server starts
def _generate_session_id():
    return str(uuid.uuid4())

def create_app():
    app = Flask(__name__)

    app.config.from_mapping(
        DEEPL_KEY = os.environ.get("DEEPL_KEY"),
        SPIEL_MODE = os.environ.get("SPIEL_MODE"),
        SESSION_ID = _generate_session_id()
    )

    def is_prod_mode():
        mode = app.config["SPIEL_MODE"]
        return mode is not None and mode == "PROD"

    def validate_session_id():
        session_id = request.args.get('session_id')
        if session_id and session_id != app.config["SESSION_ID"]:
            return False
        return True
    
    def dec_validate_session_id(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not validate_session_id():
                return jsonify(error="Forbidden: Invalid session ID"), 408
            return f(*args, **kwargs)
        return decorated_function  

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            prod_mode=is_prod_mode())

    @app.route("/reload")
    def reload():
        compiler = Compiler(app.config["DEEPL_KEY"])
        compiler.scrape_new(reload=True)
        return render_template(
            "index.html",
            reloaded=True)
        
    @app.route('/init', methods=['POST'])
    def init():
        # Receive the data sent in the POST request
        data = request.json
        
        # # convert to map
        # scores = {}
        # for row in data:
        #     scores[row[0]] = row[1]
        
        # # Call the Python method to process the data
        # get_spiel().sort_words(scores)
        
        # if "type" in data and "key_" + data["type"] in data:
        #     response = jsonify({'redirect_url': url_for('next_question', **{
        #         "mode": "start",
        #         "question_type": data["type"],
        #         "start": data["key_" + data["type"]],
        #         "order": "serial"
        #     })})
        # else:
        #     response = jsonify({'redirect_url': url_for('next_question', **{
        #         "mode": "start"
        #     })})
        
        data = {'session_id': app.config["SESSION_ID"]}
        return jsonify(data), 200
        
    @app.route("/play")
    def play():
        return redirect(url_for('next_question'))
    
    @app.route("/next_question")
    @dec_validate_session_id
    def next_question():
        query_param = request.args.get('order')
        try:
            if query_param is not None and query_param == "serial":
                start_param = request.args.get('start')
                question_type_param = request.args.get('question_type')
                next_entry = spiel.get_next_entry(serial=True, start=start_param, mode=question_type_param)
            else:
                next_entry = spiel.get_next_entry(serial=False)
        except Exception as e:
            abort(400, description=f"Error: {e}")            
        
        next_question = next_entry["value"]
        next_question["mode"] = next_entry["mode"]
        
        start = False
        query_param = request.args.get('mode')
        if query_param is not None:
            if query_param == "json":                
                data = {'next_question': next_question}
                return jsonify(data), 200
            elif query_param == "start":
                start = True
            else:
                abort(400, description=f"Invalid query parameter value: {query_param}")

        return render_template(
            "question.html",
            start=start,
            entry=next_question,
            session_id=app.config["SESSION_ID"])
        
    @app.route("/lookup")
    def lookup():
        query_param = request.args.get('wort')
        result = None
        if query_param:
            result = spiel.lookup(query_param)

        return render_template(
            "lookup.html",
            word=query_param,
            entry=result)
        
    @app.route("/list")
    def list():
        word_list = spiel.list()
        word_list = [word.capitalize() for word in word_list]
        return jsonify(sorted(word_list)), 200
        
    @app.route("/answer_score")
    def answer_score():
        user_answer = request.args.get('answer')
        translation = request.args.get('translation')
        (score_string, score) = get_spiel().get_answer_score(
            user_answer, translation)
        data = {'score_string': score_string, 'score': score}
        return jsonify(data), 200

    @app.route("/exit")
    def exit():
        # get_spiel().exit_game()
        return redirect(url_for('index'))
    
    def get_spiel():
        return spiel

    return app

if __name__ == "__main__":
    create_app().run(port=os.environ.get("SPIEL_PORT"))
