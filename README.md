# spiel
Mein eigenes Deutsches Vokabeln Spiel - http://bit.ly/jein

## Run the web service

```sh
.venv/bin/python -m uvicorn app:app --reload
```

The FastAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Backfill DWDS grammar

To refresh the grammar in all existing scrape files and in `_dump.txt` without
calling DeepL or retranslating examples, run:

```sh
.venv/bin/python translation_compiler.py --backfill-grammar
```
