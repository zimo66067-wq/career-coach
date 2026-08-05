# -*- coding: utf-8 -*-
"""conftest.py · pytest 公共 fixtures"""
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures-synthetic")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)


def read_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def fix_dir():
    return FIX


@pytest.fixture(scope="session")
def root_dir():
    return ROOT


@pytest.fixture(scope="session")
def resume_txts():
    d = os.path.join(FIX, "resumes")
    return {fn: read_text(os.path.join(d, fn)) for fn in os.listdir(d) if fn.endswith(".txt")}


@pytest.fixture(scope="session")
def score_input():
    return read_json(os.path.join(FIX, "abilities", "score-input-01.json"))


@pytest.fixture(scope="session", autouse=True)
def _isolated_db(tmp_path_factory):
    """Point the SQLite session store at a per-run temp file."""
    db_dir = tmp_path_factory.mktemp("career_coach_db")
    db_path = os.path.join(str(db_dir), "test.db")
    os.environ["RESUME_DB_PATH"] = db_path
    from tools import database
    database.init_db()
    return db_path
