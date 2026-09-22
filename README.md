isudo/
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py
├── alembic.ini
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── enums.py
│   ├── errors.py
│   ├── security.py
│   ├── deps.py
│   ├── utils.py
│   ├── schemas.py
│   ├── serializers.py
│   ├── seed.py
│   ├── web.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── dictionaries.py
│   │   ├── nodes.py
│   │   ├── shipments.py
│   │   ├── operations.py
│   │   ├── admin_users.py
│   │   ├── admin_nodes.py
│   │   └── public.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── tracking.html
│   │   ├── operator.html
│   │   ├── sorter.html
│   │   └── admin.html
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           ├── app.js
│           ├── operator.js
│           ├── sorter.js
│           └── admin.js
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
└── .env.example   (необязательно, всё через docker-compose)

http://localhost:8443/tracking — публичное отслеживание

http://localhost:8443/login — вход (admin / admin12345)

http://localhost:8443/docs — Swagger

http://localhost:8443/health — health

## Тесты

Тесты используют настоящий PostgreSQL (модели используют `ENUM`-типы и
`SELECT ... FOR UPDATE`, которые SQLite не поддерживает корректно).

    docker compose up -d db
    docker compose exec db createdb -U isudo isudo_test  # один раз

    pip install -r requirements.txt -r requirements-dev.txt
    TEST_DATABASE_URL=postgresql+psycopg://isudo:isudo@localhost:5432/isudo_test python -m pytest -v