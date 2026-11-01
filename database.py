"""Banco de dados SQLite dos candidatos."""
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

# Para mudar o local do arquivo (ex.: disco persistente do Render), defina
# a variável de ambiente DATABASE_PATH. Exemplo: /var/data/candidatos.db
CAMINHO_BANCO = os.environ.get("DATABASE_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "candidatos.db"
)

FUSO_BRASILIA = timezone(timedelta(hours=-3))


@contextmanager
def conexao():
    """Abre o banco, confirma (commit) no fim e desfaz (rollback) se der erro."""
    con = sqlite3.connect(CAMINHO_BANCO)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def iniciar_banco():
    """Cria as tabelas se ainda não existirem."""
    pasta = os.path.dirname(CAMINHO_BANCO)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    with conexao() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidatos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nome        TEXT    NOT NULL,
                cpf         TEXT    NOT NULL UNIQUE,   -- somente dígitos
                telefone    TEXT    NOT NULL,
                email       TEXT    NOT NULL,
                experiencia TEXT    NOT NULL,
                cargo       TEXT    NOT NULL,
                acertos     INTEGER NOT NULL,
                total       INTEGER NOT NULL,
                criado_em   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS respostas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                candidato_id INTEGER NOT NULL
                             REFERENCES candidatos(id) ON DELETE CASCADE,
                numero       INTEGER NOT NULL,
                pergunta     TEXT    NOT NULL,
                tipo         TEXT    NOT NULL,         -- multipla | aberta
                resposta     TEXT    NOT NULL,
                acertou      INTEGER                   -- 1, 0 ou NULL (aberta)
            );

            CREATE INDEX IF NOT EXISTS idx_respostas_candidato
                ON respostas (candidato_id);
            """
        )


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_existe(cpf):
    with conexao() as con:
        linha = con.execute(
            "SELECT 1 FROM candidatos WHERE cpf = ?", (so_digitos(cpf),)
        ).fetchone()
    return linha is not None


def salvar_candidato(valores, cargo, acertos, total, respostas):
    """Grava o candidato e todas as respostas. Retorna o id do candidato.

    Levanta sqlite3.IntegrityError se o CPF já estiver cadastrado.
    """
    agora = datetime.now(FUSO_BRASILIA).isoformat(timespec="seconds")

    with conexao() as con:
        cursor = con.execute(
            """
            INSERT INTO candidatos
                (nome, cpf, telefone, email, experiencia, cargo, acertos, total, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                valores["nome"],
                so_digitos(valores["cpf"]),
                valores["telefone"],
                valores["email"],
                valores["experiencia"],
                cargo,
                acertos,
                total,
                agora,
            ),
        )
        candidato_id = cursor.lastrowid

        con.executemany(
            """
            INSERT INTO respostas
                (candidato_id, numero, pergunta, tipo, resposta, acertou)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    candidato_id,
                    r["numero"],
                    r["texto"],
                    r["tipo"],
                    r["resposta"],
                    (1 if r["acertou"] else 0) if r["tipo"] == "multipla" else None,
                )
                for r in respostas
            ],
        )

    return candidato_id


def listar_candidatos():
    with conexao() as con:
        return con.execute(
            """
            SELECT id, nome, cpf, telefone, email, experiencia, cargo,
                   acertos, total, criado_em
            FROM candidatos
            ORDER BY id DESC
            """
        ).fetchall()


def buscar_candidato(candidato_id):
    with conexao() as con:
        return con.execute(
            "SELECT * FROM candidatos WHERE id = ?", (candidato_id,)
        ).fetchone()


def listar_respostas(candidato_id):
    with conexao() as con:
        return con.execute(
            "SELECT * FROM respostas WHERE candidato_id = ? ORDER BY numero",
            (candidato_id,),
        ).fetchall()