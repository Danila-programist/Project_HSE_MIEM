## @file
# @brief Начальная миграция схемы ИСУДО.
#
# Создаёт таблицы, индексы, типы ENUM и начальные справочники. Идентификатор ревизии: 0001_initial.
"""initial schema + dictionaries

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


## @brief Создаёт начальную схему и справочники.
#
# Создаёт ENUM, таблицы, внешние ключи и индексы; заполняет типы отправлений и документов.
#
# @note Возвращает None; схема и справочники изменяются в БД.
def upgrade() -> None:
    bind = op.get_bind()

    node_type = postgresql.ENUM("SERVICE_POINT", "SORTING_CENTER", name="node_type")
    employee_role = postgresql.ENUM("OPERATOR", "SORTING_EMPLOYEE", "ADMIN", name="employee_role")
    shipment_status = postgresql.ENUM(
        "CREATED", "ACCEPTED", "DISPATCHED", "ARRIVED", "READY_FOR_PICKUP", "ISSUED",
        name="shipment_status",
    )
    shipment_operation = postgresql.ENUM(
        "CREATE", "ACCEPT", "DISPATCH", "ARRIVE", "ISSUE",
        name="shipment_operation",
    )
    document_kind = postgresql.ENUM("SENDER", "RECIPIENT", name="document_kind")

    node_type.create(bind, checkfirst=True)
    employee_role.create(bind, checkfirst=True)
    shipment_status.create(bind, checkfirst=True)
    shipment_operation.create(bind, checkfirst=True)
    document_kind.create(bind, checkfirst=True)

    op.create_table(
        "nodes",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", postgresql.ENUM(name="node_type", create_type=False), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("login", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", postgresql.ENUM(name="employee_role", create_type=False), nullable=False),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("blocked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_employees_login", "employees", ["login"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("employee_id", sa.BigInteger, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "shipment_types",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
    )

    op.create_table(
        "document_types",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
    )

    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("track_number", sa.String(16), nullable=False, unique=True),
        sa.Column("status", postgresql.ENUM(name="shipment_status", create_type=False), nullable=False),
        sa.Column("shipment_type_id", sa.BigInteger, sa.ForeignKey("shipment_types.id"), nullable=False),
        sa.Column("origin_node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("destination_node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("current_node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("next_node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("delivery_address", sa.String(500), nullable=False),
        sa.Column("sender_full_name", sa.String(200), nullable=False),
        sa.Column("sender_phone", sa.String(20), nullable=False),
        sa.Column("recipient_full_name", sa.String(200), nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("weight_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("length_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("width_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("height_cm", sa.Numeric(10, 2), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_shipments_track_number", "shipments", ["track_number"], unique=True)
    op.create_index("ix_shipments_origin_node", "shipments", ["origin_node_id"])
    op.create_index("ix_shipments_current_node", "shipments", ["current_node_id"])
    op.create_index("ix_shipments_next_node", "shipments", ["next_node_id"])

    op.create_table(
        "shipment_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("shipment_id", sa.BigInteger, sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("operation", postgresql.ENUM(name="shipment_operation", create_type=False), nullable=False),
        sa.Column("resulting_status", postgresql.ENUM(name="shipment_status", create_type=False), nullable=False),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("next_node_id", sa.BigInteger, sa.ForeignKey("nodes.id"), nullable=True),
        sa.Column("employee_id", sa.BigInteger, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_events_shipment", "shipment_events", ["shipment_id"])

    op.create_table(
        "shipment_documents",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("shipment_id", sa.BigInteger, sa.ForeignKey("shipments.id"), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="document_kind", create_type=False), nullable=False),
        sa.Column("document_type_id", sa.BigInteger, sa.ForeignKey("document_types.id"), nullable=False),
        sa.Column("series", sa.String(20), nullable=True),
        sa.Column("number", sa.String(30), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("recorded_by_id", sa.BigInteger, sa.ForeignKey("employees.id"), nullable=False),
        sa.UniqueConstraint("shipment_id", "kind", name="uq_shipment_doc_kind"),
    )

    op.bulk_insert(
        sa.table(
            "shipment_types",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
        ),
        [
            {"code": "PARCEL", "name": "Посылка"},
            {"code": "LETTER", "name": "Письмо"},
            {"code": "BANDEROL", "name": "Бандероль"},
            {"code": "CARGO", "name": "Груз"},
            {"code": "EMS", "name": "EMS-отправление"},
        ],
    )
    op.bulk_insert(
        sa.table(
            "document_types",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
        ),
        [
            {"code": "PASSPORT_RF", "name": "Паспорт РФ"},
            {"code": "INT_PASSPORT", "name": "Загранпаспорт"},
            {"code": "DRIVER_LICENSE", "name": "Водительское удостоверение"},
            {"code": "BIRTH_CERT", "name": "Свидетельство о рождении"},
            {"code": "MILITARY_ID", "name": "Военный билет"},
        ],
    )


## @brief Удаляет объекты начальной миграции.
#
# Удаляет таблицы, индексы и ENUM в обратном порядке зависимостей. Откат уничтожает данные этих таблиц.
#
# @note Возвращает None; объекты схемы удаляются.
def downgrade() -> None:
    op.drop_table("shipment_documents")
    op.drop_index("ix_events_shipment", table_name="shipment_events")
    op.drop_table("shipment_events")
    op.drop_index("ix_shipments_next_node", table_name="shipments")
    op.drop_index("ix_shipments_current_node", table_name="shipments")
    op.drop_index("ix_shipments_origin_node", table_name="shipments")
    op.drop_index("ix_shipments_track_number", table_name="shipments")
    op.drop_table("shipments")
    op.drop_table("document_types")
    op.drop_table("shipment_types")
    op.drop_table("sessions")
    op.drop_index("ix_employees_login", table_name="employees")
    op.drop_table("employees")
    op.drop_table("nodes")

    for name in ("document_kind", "shipment_operation", "shipment_status", "employee_role", "node_type"):
        op.execute(f"DROP TYPE IF EXISTS {name}")