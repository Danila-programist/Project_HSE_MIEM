"""Фейковая сессия SQLAlchemy без базы данных.

Хранит ORM-объекты в словарях и исполняет в памяти то подмножество Core-выражений,
которое использует приложение: select().where().order_by().offset().limit(),
func.count() поверх таблицы или подзапроса, операторы ==, !=, is_, in_/notin_, and_/or_.
Имитирует поведение PostgreSQL, на которое опираются обработчики: автоинкремент
первичных ключей, значения по умолчанию, NOT NULL, UNIQUE и внешние ключи
(IntegrityError), загрузку связей many-to-one.
"""
import itertools
import operator as py_operator
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, UniqueConstraint, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import RelationshipDirection
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.sql import elements, operators, selectable
from sqlalchemy.sql.functions import count as sql_count

from app.db import Base

_TABLE_TO_CLASS = {m.local_table: m.class_ for m in Base.registry.mappers}

_COMPARATORS = {
    operators.eq: py_operator.eq,
    operators.ne: py_operator.ne,
    operators.lt: py_operator.lt,
    operators.le: py_operator.le,
    operators.gt: py_operator.gt,
    operators.ge: py_operator.ge,
    operators.is_: lambda a, b: a is b or a == b,
    operators.is_not: lambda a, b: not (a is b or a == b),
    operators.in_op: lambda a, b: a in b,
    operators.not_in_op: lambda a, b: a not in b,
}


def _integrity_error(message: str) -> IntegrityError:
    return IntegrityError(message, None, Exception(message))


def _attr_key(cls, column) -> str:
    try:
        return inspect(cls).get_property_by_column(column).key
    except Exception:
        return column.key


class FakeResult:
    """Минимальный аналог Result/ScalarResult."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self.first()

    def scalar_one(self):
        if len(self._rows) != 1:
            raise LookupError(f"Ожидалась одна строка, получено {len(self._rows)}")
        return self._rows[0]

    def scalar_one_or_none(self):
        if len(self._rows) > 1:
            raise LookupError(f"Ожидалась максимум одна строка, получено {len(self._rows)}")
        return self.first()

    one = scalar_one
    one_or_none = scalar_one_or_none

    def __iter__(self):
        return iter(self._rows)


class FakeQuery:
    """Поддержка legacy-вызова db.query(Model).filter(...).update({...})."""

    def __init__(self, session, cls):
        self._session = session
        self._cls = cls
        self._criteria = []

    def filter(self, *criteria):
        self._criteria.extend(criteria)
        return self

    def _rows(self):
        return [
            o
            for o in self._session._all(self._cls)
            if all(self._session._eval(c, o) for c in self._criteria)
        ]

    def all(self):
        return self._rows()

    def first(self):
        rows = self._rows()
        return rows[0] if rows else None

    def count(self):
        return len(self._rows())

    def update(self, values, synchronize_session=None):
        rows = self._rows()
        for o in rows:
            for key, value in values.items():
                setattr(o, key if isinstance(key, str) else key.key, value)
        return len(rows)


class FakeSession:
    """Сессия, хранящая «таблицы» в памяти процесса."""

    def __init__(self):
        self._storage = defaultdict(dict)  # класс модели -> {pk: объект}
        self._ids = defaultdict(lambda: itertools.count(1))
        self._new = []
        self._deleted = []

    # --- API сессии ---------------------------------------------------------

    def add(self, obj):
        if obj not in self._new and not self._is_persistent(obj):
            self._new.append(obj)

    def add_all(self, objs):
        for obj in objs:
            self.add(obj)

    def delete(self, obj):
        if obj in self._new:
            self._new.remove(obj)
        elif self._is_persistent(obj) and obj not in self._deleted:
            self._deleted.append(obj)

    def get(self, cls, pk):
        obj = self._storage[cls].get(pk)
        if obj is not None:
            self._load_relationships(obj)
        return obj

    def flush(self):
        new, deleted = list(self._new), list(self._deleted)
        for obj in new:
            self._apply_defaults(obj)

        inserted, removed = [], []
        try:
            for obj in new:
                self._check_not_null(obj)
                self._check_unique(obj)
                self._storage[type(obj)][self._pk(obj)] = obj
                inserted.append(obj)
            for obj in deleted:
                removed.append(self._storage[type(obj)].pop(self._pk(obj)))
            self._check_foreign_keys()
        except IntegrityError:
            for obj in inserted:
                self._storage[type(obj)].pop(self._pk(obj), None)
            for obj in removed:
                self._storage[type(obj)][self._pk(obj)] = obj
            raise

        self._new.clear()
        self._deleted.clear()
        self._load_all_relationships()

    def commit(self):
        self.flush()

    def rollback(self):
        self._new.clear()
        self._deleted.clear()

    def refresh(self, obj):
        self._load_relationships(obj)

    def expire(self, obj, attribute_names=None):
        pass

    def expire_all(self):
        pass

    def close(self):
        pass

    def query(self, cls):
        return FakeQuery(self, cls)

    def execute(self, stmt, params=None):
        return FakeResult(self._run_select(stmt))

    def scalars(self, stmt, params=None):
        return self.execute(stmt).scalars()

    def scalar(self, stmt, params=None):
        return self.execute(stmt).first()

    # --- Исполнение select() -----------------------------------------------

    def _run_select(self, stmt):
        if not isinstance(stmt, selectable.Select):
            raise NotImplementedError(f"FakeSession не поддерживает {type(stmt).__name__}")

        columns = list(stmt.selected_columns)
        if len(columns) == 1 and isinstance(columns[0], sql_count):
            return [len(self._rows_from(stmt))]
        return self._rows_from(stmt)

    def _rows_from(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is not None:
            cls, rows = entity, self._all(entity)
        else:
            froms = stmt.get_final_froms()
            if len(froms) != 1:
                raise NotImplementedError("FakeSession поддерживает выборку только из одного источника")
            source = froms[0]
            if isinstance(source, selectable.Subquery):
                return self._rows_from(source.element)
            cls = _TABLE_TO_CLASS[source]
            rows = self._all(cls)

        if stmt.whereclause is not None:
            rows = [o for o in rows if self._eval(stmt.whereclause, o)]

        for clause in reversed(stmt._order_by_clauses):
            descending = False
            if isinstance(clause, elements.UnaryExpression):
                descending = clause.modifier is operators.desc_op
                clause = clause.element
            key = _attr_key(cls, clause)
            rows.sort(key=lambda o: (getattr(o, key) is None, getattr(o, key)), reverse=descending)

        offset = stmt._offset or 0
        limit = stmt._limit
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    def _eval(self, clause, obj):
        if isinstance(clause, elements.Grouping):
            return self._eval(clause.element, obj)
        if isinstance(clause, elements.BooleanClauseList):
            results = (self._eval(c, obj) for c in clause.clauses)
            return all(results) if clause.operator is operators.and_ else any(results)
        if isinstance(clause, elements.BinaryExpression):
            compare = _COMPARATORS.get(clause.operator)
            if compare is None:
                raise NotImplementedError(f"FakeSession не поддерживает оператор {clause.operator}")
            return compare(self._value(clause.left, obj), self._value(clause.right, obj))
        if isinstance(clause, elements.UnaryExpression) and clause.operator is operators.inv:
            return not self._eval(clause.element, obj)
        if isinstance(clause, (elements.True_, elements.False_)):
            return isinstance(clause, elements.True_)
        if isinstance(clause, elements.ColumnElement) and hasattr(clause, "table"):
            return bool(self._value(clause, obj))
        raise NotImplementedError(f"FakeSession не поддерживает выражение {type(clause).__name__}")

    def _value(self, expr, obj):
        if isinstance(expr, elements.Grouping):
            return self._value(expr.element, obj)
        if isinstance(expr, elements.BindParameter):
            return expr.effective_value
        if isinstance(expr, elements.True_):
            return True
        if isinstance(expr, elements.False_):
            return False
        if isinstance(expr, elements.Null):
            return None
        if isinstance(expr, elements.ExpressionClauseList):
            return [self._value(c, obj) for c in expr.clauses]
        if hasattr(expr, "table"):
            return getattr(obj, _attr_key(type(obj), expr))
        raise NotImplementedError(f"FakeSession не поддерживает значение {type(expr).__name__}")

    # --- Имитация ограничений и умолчаний БД -------------------------------

    def _all(self, cls):
        rows = list(self._storage[cls].values())
        for obj in rows:
            self._load_relationships(obj)
        return rows

    def _is_persistent(self, obj):
        pk = self._pk(obj)
        return pk is not None and self._storage[type(obj)].get(pk) is obj

    @staticmethod
    def _pk(obj):
        mapper = inspect(type(obj))
        return getattr(obj, _attr_key(type(obj), mapper.primary_key[0]))

    def _apply_defaults(self, obj):
        cls = type(obj)
        mapper = inspect(cls)
        for column in mapper.columns:
            key = _attr_key(cls, column)
            if getattr(obj, key) is not None:
                continue
            if column.primary_key and column.autoincrement in (True, "auto"):
                if column.type.python_type is int:
                    setattr(obj, key, next(self._ids[cls]))
            elif column.default is not None and column.default.is_scalar:
                setattr(obj, key, column.default.arg)
            elif column.server_default is not None and isinstance(column.type, DateTime):
                setattr(obj, key, datetime.now(timezone.utc))

    def _check_not_null(self, obj):
        cls = type(obj)
        for column in inspect(cls).columns:
            if not column.nullable and getattr(obj, _attr_key(cls, column)) is None:
                raise _integrity_error(
                    f'null value in column "{column.name}" of relation "{column.table.name}" '
                    "violates not-null constraint"
                )

    def _check_unique(self, obj):
        cls = type(obj)
        table = inspect(cls).local_table
        unique_sets = [[c] for c in table.primary_key.columns]
        unique_sets += [[c] for c in table.columns if c.unique]
        unique_sets += [list(c.columns) for c in table.constraints if isinstance(c, UniqueConstraint)]
        unique_sets += [list(i.columns) for i in table.indexes if isinstance(i, Index) and i.unique]

        for cols in unique_sets:
            keys = [_attr_key(cls, c) for c in cols]
            values = tuple(getattr(obj, k) for k in keys)
            if None in values:
                continue
            for other in self._storage[cls].values():
                if other is not obj and tuple(getattr(other, k) for k in keys) == values:
                    raise _integrity_error(
                        f'duplicate key value violates unique constraint on "{table.name}" '
                        f"({', '.join(c.name for c in cols)})={values}"
                    )

    def _check_foreign_keys(self):
        for cls, rows in self._storage.items():
            table = inspect(cls).local_table
            for fk in table.foreign_keys:
                key = _attr_key(cls, fk.parent)
                target_cls = _TABLE_TO_CLASS[fk.column.table]
                for obj in rows.values():
                    value = getattr(obj, key)
                    if value is not None and value not in self._storage[target_cls]:
                        raise _integrity_error(
                            f'insert or update on table "{table.name}" violates foreign key constraint '
                            f'on "{fk.parent.name}": key ({value}) is not present in "{fk.column.table.name}"'
                        )

    def _load_relationships(self, obj):
        cls = type(obj)
        for rel in inspect(cls).relationships:
            if rel.direction is not RelationshipDirection.MANYTOONE:
                continue
            (local, _remote), = rel.local_remote_pairs
            fk_value = getattr(obj, _attr_key(cls, local))
            target = self._storage[rel.mapper.class_].get(fk_value) if fk_value is not None else None
            set_committed_value(obj, rel.key, target)

    def _load_all_relationships(self):
        for rows in self._storage.values():
            for obj in rows.values():
                self._load_relationships(obj)
