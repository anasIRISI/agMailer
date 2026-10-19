import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.database.session import Base, get_db
from app.models import entities
from app.main import app

@pytest.fixture
def factory():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()

@pytest.fixture
def db(factory):
    with factory() as session:
        yield session

@pytest.fixture
def client(factory):
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    client = TestClient(app, headers={'X-PFE-Client': 'local-app'})
    yield client
    client.close()
    app.dependency_overrides.clear()
