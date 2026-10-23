"""Declarative base that all future ORM models inherit from."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
