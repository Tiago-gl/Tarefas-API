import os
import decimal
import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from psycopg2 import errors
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

app = Flask(__name__)
WEB_ORIGIN = os.environ.get("WEB_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": WEB_ORIGIN}})

if load_dotenv is not None and os.path.exists(os.path.join(os.path.dirname(__file__), ".env")):
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurada")
    # Supabase Postgres geralmente requer SSL
    return psycopg2.connect(database_url, sslmode="require")

def serialize_task(row):
    return {
        "id": row["id"],
        "nome": row["nome"],
        "custo": float(row["custo"]) if row.get("custo") is not None else None,
        "data_limite": row["data_limite"].isoformat() if row.get("data_limite") else None,
        "ordem_apresentacao": row["ordem_apresentacao"],
    }


def parse_iso_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_decimal(value):
    try:
        return decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return None


def validate_payload(data, allow_order=False):
    errors = {}

    nome = data.get("nome")
    if not nome or not str(nome).strip():
        errors["nome"] = "Nome e obrigatorio."
    nome = str(nome).strip() if nome is not None else None

    custo_raw = data.get("custo")
    if custo_raw is None or str(custo_raw).strip() == "":
        errors["custo"] = "Custo e obrigatorio."
        custo = None
    else:
        custo = parse_decimal(custo_raw)
        if custo is None:
            errors["custo"] = "Custo deve ser um numero decimal."
        elif custo < 0:
            errors["custo"] = "Custo deve ser maior ou igual a zero."

    data_limite_raw = data.get("data_limite")
    if not data_limite_raw:
        errors["data_limite"] = "Data limite e obrigatoria."
        data_limite = None
    else:
        data_limite = parse_iso_date(data_limite_raw)
        if data_limite is None:
            errors["data_limite"] = "Data limite deve estar no formato yyyy-mm-dd."

    ordem_apresentacao = None
    if allow_order and "ordem_apresentacao" in data:
        ordem_raw = data.get("ordem_apresentacao")
        try:
            ordem_apresentacao = int(ordem_raw)
        except (TypeError, ValueError):
            errors["ordem_apresentacao"] = "Ordem de apresentacao deve ser um inteiro."

    return errors, nome, custo, data_limite, ordem_apresentacao


def handle_unique_violation(exc):
    message = "Registro com campo unico ja existente."
    constraint = None
    if getattr(exc, "diag", None) is not None:
        constraint = exc.diag.constraint_name
    if constraint and "nome" in constraint:
        message = "Nome ja existe."
    elif constraint and "ordem" in constraint:
        message = "Ordem de apresentacao ja existe."
    else:
        detail = str(exc)
        if "nome" in detail:
            message = "Nome ja existe."
        elif "ordem" in detail:
            message = "Ordem de apresentacao ja existe."
    return jsonify({"error": message}), 409

@app.get("/api/health")
def health():
    return {"ok": True}

@app.route("/api/tarefas", methods=["GET"])
def list_tarefas():
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, nome, custo, data_limite, ordem_apresentacao
                FROM tarefas
                ORDER BY ordem_apresentacao
                """
            )
            rows = cur.fetchall()
        return jsonify([serialize_task(row) for row in rows])
    finally:
        conn.close()


@app.route("/api/tarefas", methods=["POST"])
def create_tarefa():
    data = request.get_json(silent=True) or {}
    errors, nome, custo, data_limite, ordem_apresentacao = validate_payload(data, allow_order=True)
    if errors:
        return jsonify({"errors": errors}), 400

    conn = get_conn()
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if ordem_apresentacao is None:
                cur.execute("LOCK TABLE tarefas IN EXCLUSIVE MODE")
                cur.execute("SELECT COALESCE(MAX(ordem_apresentacao), 0) + 1 AS next_ordem FROM tarefas")
                ordem_apresentacao = cur.fetchone()["next_ordem"]

            cur.execute(
                """
                INSERT INTO tarefas (nome, custo, data_limite, ordem_apresentacao)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nome, custo, data_limite, ordem_apresentacao
                """,
                (nome, custo, data_limite, ordem_apresentacao),
            )
            row = cur.fetchone()
        conn.commit()
        return jsonify(serialize_task(row)), 201
    except errors.UniqueViolation as exc:
        conn.rollback()
        return handle_unique_violation(exc)
    finally:
        conn.close()


@app.route("/api/tarefas/<int:tarefa_id>", methods=["PUT"])
def update_tarefa(tarefa_id):
    data = request.get_json(silent=True) or {}
    errors_map, nome, custo, data_limite, _ = validate_payload(data)
    if errors_map:
        return jsonify({"errors": errors_map}), 400

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE tarefas
                SET nome = %s, custo = %s, data_limite = %s
                WHERE id = %s
                RETURNING id, nome, custo, data_limite, ordem_apresentacao
                """,
                (nome, custo, data_limite, tarefa_id),
            )
            row = cur.fetchone()
        conn.commit()
        if not row:
            return jsonify({"error": "Tarefa nao encontrada."}), 404
        return jsonify(serialize_task(row))
    except errors.UniqueViolation as exc:
        conn.rollback()
        return handle_unique_violation(exc)
    finally:
        conn.close()


@app.route("/api/tarefas/<int:tarefa_id>", methods=["DELETE"])
def delete_tarefa(tarefa_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tarefas WHERE id = %s RETURNING id", (tarefa_id,))
            row = cur.fetchone()
        conn.commit()
        if not row:
            return jsonify({"error": "Tarefa nao encontrada."}), 404
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route("/api/tarefas/<int:tarefa_id>/mover", methods=["PATCH"])
def move_tarefa(tarefa_id):
    data = request.get_json(silent=True) or {}
    direction = data.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"error": "Direction deve ser 'up' ou 'down'."}), 400

    conn = get_conn()
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, ordem_apresentacao FROM tarefas WHERE id = %s",
                (tarefa_id,),
            )
            current = cur.fetchone()
            if not current:
                conn.rollback()
                return jsonify({"error": "Tarefa nao encontrada."}), 404

            if direction == "up":
                cur.execute(
                    """
                    SELECT id, ordem_apresentacao
                    FROM tarefas
                    WHERE ordem_apresentacao < %s
                    ORDER BY ordem_apresentacao DESC
                    LIMIT 1
                    """,
                    (current["ordem_apresentacao"],),
                )
            else:
                cur.execute(
                    """
                    SELECT id, ordem_apresentacao
                    FROM tarefas
                    WHERE ordem_apresentacao > %s
                    ORDER BY ordem_apresentacao ASC
                    LIMIT 1
                    """,
                    (current["ordem_apresentacao"],),
                )

            neighbor = cur.fetchone()
            if not neighbor:
                conn.commit()
                return jsonify({"success": True, "swapped": False})

            # Use a temporary value to avoid unique constraint collisions during swap.
            cur.execute("SELECT COALESCE(MAX(ordem_apresentacao), 0) + 1 AS temp FROM tarefas")
            temp_ordem = cur.fetchone()["temp"]

            cur.execute(
                "UPDATE tarefas SET ordem_apresentacao = %s WHERE id = %s",
                (temp_ordem, current["id"]),
            )
            cur.execute(
                "UPDATE tarefas SET ordem_apresentacao = %s WHERE id = %s",
                (current["ordem_apresentacao"], neighbor["id"]),
            )
            cur.execute(
                "UPDATE tarefas SET ordem_apresentacao = %s WHERE id = %s",
                (neighbor["ordem_apresentacao"], current["id"]),
            )
        conn.commit()
        return jsonify({"success": True, "swapped": True})
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)
