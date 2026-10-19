import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
import portalocker
from app.core.config import DATA_DIR, ORIGINS, ROOT
from app.database.session import Base, engine, SessionLocal
from app.models import entities  # register tables
from app.routers.api import router
from app.services.queue import recover, queue_engine

@asynccontextmanager
async def lifespan(app):
    lock = portalocker.Lock(str(DATA_DIR / 'instance.lock'), timeout=0)
    with lock:
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            recover(db)
        scheduler = BackgroundScheduler()
        scheduler.add_job(queue_engine.tick, 'interval', seconds=2, max_instances=1, coalesce=True)
        scheduler.start()
        yield
        scheduler.shutdown(wait=True)

app = FastAPI(title='PFE Mail Agent', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount('/docs-assets', StaticFiles(directory=ROOT / 'frontend/node_modules/swagger-ui-dist', check_dir=False), name='docs-assets')

@app.get('/docs', include_in_schema=False)
def swagger_docs():
    return get_swagger_ui_html(openapi_url='/openapi.json', title='PFE Mail Agent · API',
        swagger_js_url='/docs-assets/swagger-ui-bundle.js', swagger_css_url='/docs-assets/swagger-ui.css',
        swagger_favicon_url='/docs-assets/favicon-32x32.png', swagger_ui_parameters={'validatorUrl': None})
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-PFE-Client'])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

@app.middleware('http')
async def local_guard(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and (request.headers.get('X-PFE-Client') != 'local-app' or (origin and origin not in ORIGINS)):
        return JSONResponse({'detail': 'Requête locale non autorisée.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

@app.exception_handler(Exception)
async def unhandled(request, exc):
    logging.getLogger('pfe').error('Erreur interne : %s', type(exc).__name__)
    return JSONResponse({'detail': 'Une erreur interne est survenue. Vérifiez les fichiers locaux et réessayez.'}, status_code=500)

app.include_router(router)
