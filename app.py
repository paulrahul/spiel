import os
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    from .spiel import DeutschesSpiel
except ImportError:
    # Support `uvicorn app:app` and `python app.py` from the project root.
    from spiel import DeutschesSpiel


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
spiel = DeutschesSpiel(use_semantic=False, use_multimode=True)


class InvalidSessionError(Exception):
    pass


def _generate_session_id():
    return str(uuid.uuid4())


def _validate_session_id(request: Request):
    session_id = request.query_params.get("session_id")
    if session_id and session_id != request.app.state.session_id:
        raise InvalidSessionError


def create_app():
    app = FastAPI(title="Deutsches Spiel")
    app.state.deepl_key = os.environ.get("DEEPL_KEY")
    app.state.spiel_mode = os.environ.get("SPIEL_MODE")
    app.state.session_id = _generate_session_id()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "static"),
        name="static")

    @app.exception_handler(InvalidSessionError)
    def invalid_session_handler(request: Request, exc: InvalidSessionError):
        return JSONResponse(
            status_code=408,
            content={"error": "Forbidden: Invalid session ID"})

    def is_prod_mode():
        return app.state.spiel_mode == "PROD"

    def lookup_words():
        return sorted(word.capitalize() for word in spiel.list())

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"prod_mode": is_prod_mode()})

    @app.post("/init")
    def initialize_session():
        return {"session_id": app.state.session_id}

    @app.get("/play")
    def play(request: Request):
        return RedirectResponse(
            url=str(request.url_for("next_question")),
            status_code=302)

    @app.get(
        "/next_question",
        response_class=HTMLResponse,
        dependencies=[Depends(_validate_session_id)])
    def next_question(request: Request):
        order = request.query_params.get("order")
        try:
            if order == "serial":
                next_entry = spiel.get_next_entry(
                    serial=True,
                    start=request.query_params.get("start"),
                    mode=request.query_params.get("question_type"))
            else:
                next_entry = spiel.get_next_entry(serial=False)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error: {e}") from e

        next_question = next_entry["value"]
        next_question["mode"] = next_entry["mode"]

        start = False
        response_mode = request.query_params.get("mode")
        if response_mode is not None:
            if response_mode == "json":
                return JSONResponse(content={"next_question": next_question})
            if response_mode == "start":
                start = True
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid query parameter value: {response_mode}")

        return templates.TemplateResponse(
            request=request,
            name="question.html",
            context={
                "start": start,
                "entry": next_question,
                "session_id": app.state.session_id,
            })

    @app.get("/lookup", response_class=HTMLResponse)
    def lookup(request: Request):
        is_list_mode = (
            "list" in request.query_params or
            request.query_params.get("mode") == "list")
        if is_list_mode:
            word_list = lookup_words()
            word = word_list[0] if word_list else None
            return templates.TemplateResponse(
                request=request,
                name="lookup.html",
                context={
                    "mode": "list",
                    "word": word,
                    "entry": spiel.lookup(word) if word else None,
                    "selected_word": word,
                })

        word = request.query_params.get("wort")
        result = spiel.lookup(word) if word else None

        if request.query_params.get("mode") == "json":
            return JSONResponse(
                content={"examples": result["examples"] if result else []})

        return templates.TemplateResponse(
            request=request,
            name="lookup.html",
            context={
                "mode": "wort",
                "word": word,
                "entry": result,
                "selected_word": word,
            })

    @app.get("/list")
    def list_words():
        return lookup_words()

    @app.get("/answer_score")
    def answer_score(request: Request):
        answer = request.query_params.get("answer")
        translation = request.query_params.get("translation")
        score_string, score = spiel.get_answer_score(answer, translation)
        return {"score_string": score_string, "score": score}

    @app.get("/exit")
    def exit_game(request: Request):
        return RedirectResponse(
            url=str(request.url_for("index")),
            status_code=302)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("SPIEL_PORT", "8000")))
