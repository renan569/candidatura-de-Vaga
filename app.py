import csv
import io
import os
import re
import sqlite3
from datetime import datetime
from functools import wraps
from hmac import compare_digest

from flask import Flask, Response, abort, render_template, request

import database

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # recusa envios acima de 64 KB

# ----------------------------------------------------------------------
# CONFIGURAÇÃO (troque pelos dados da sua empresa e da vaga)
# ----------------------------------------------------------------------
EMPRESA = "Sua Empresa"

VAGA = {
    "cargo": "Gerente",
    "horario": "9h às 18h",
    "salario": 8000.00,
}

# Acesso à área administrativa (/admin). Defina no Render, em Environment:
#   ADMIN_SENHA   -> senha de acesso (sem ela, a área admin fica desativada)
#   ADMIN_USUARIO -> usuário (opcional, padrão: admin)
ADMIN_USUARIO = os.environ.get("ADMIN_USUARIO", "admin")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA", "")

# ----------------------------------------------------------------------
# PROVA (exemplo: troque pelas suas 8 perguntas)
# tipo "multipla": precisa de "opcoes" e "correta"; tipo "aberta": só texto
# ----------------------------------------------------------------------
PERGUNTAS = [
    {
        "id": "q1",
        "texto": "Qual é a capital do Brasil?",
        "tipo": "multipla",
        "opcoes": {"A": "Rio de Janeiro", "B": "São Paulo", "C": "Brasília", "D": "Salvador"},
        "correta": "C",
    },
    {
        "id": "q2",
        "texto": "Quanto é 15% de 200?",
        "tipo": "multipla",
        "opcoes": {"A": "20", "B": "25", "C": "30", "D": "35"},
        "correta": "C",
    },
    {
        "id": "q3",
        "texto": "Quem escreveu o romance Dom Casmurro?",
        "tipo": "multipla",
        "opcoes": {"A": "José de Alencar", "B": "Machado de Assis", "C": "Clarice Lispector", "D": "Graciliano Ramos"},
        "correta": "B",
    },
    {
        "id": "q4",
        "texto": "Qual é o maior planeta do Sistema Solar?",
        "tipo": "multipla",
        "opcoes": {"A": "Saturno", "B": "Terra", "C": "Júpiter", "D": "Marte"},
        "correta": "C",
    },
    {
        "id": "q5",
        "texto": "Em que ano foi proclamada a República no Brasil?",
        "tipo": "multipla",
        "opcoes": {"A": "1822", "B": "1889", "C": "1930", "D": "1964"},
        "correta": "B",
    },
    {
        "id": "q6",
        "texto": "Quanto é 12 × 12?",
        "tipo": "multipla",
        "opcoes": {"A": "124", "B": "132", "C": "144", "D": "156"},
        "correta": "C",
    },
    {
        "id": "q7",
        "texto": "Qual é o gás mais abundante na atmosfera terrestre?",
        "tipo": "multipla",
        "opcoes": {"A": "Oxigênio", "B": "Nitrogênio", "C": "Gás carbônico", "D": "Hidrogênio"},
        "correta": "B",
    },
    {
        "id": "q8",
        "texto": "Descreva uma situação em que você liderou uma equipe ou resolveu um conflito no trabalho.",
        "tipo": "aberta",
    },
]

# Cria as tabelas do banco ao iniciar o aplicativo
database.iniciar_banco()


# ----------------------------------------------------------------------
# FILTROS DE TEMPLATE
# ----------------------------------------------------------------------
@app.template_filter("brl")
def formatar_brl(valor):
    """8000 -> R$ 8.000,00"""
    try:
        texto = f"{float(valor):,.2f}"
    except (TypeError, ValueError):
        return str(valor)
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@app.template_filter("cpf")
def formatar_cpf(valor):
    d = database.so_digitos(valor)
    if len(d) != 11:
        return valor
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


@app.template_filter("cpf_oculto")
def cpf_oculto(valor):
    d = database.so_digitos(valor)
    if len(d) != 11:
        return valor
    return f"***.***.***-{d[9:]}"


@app.template_filter("data_br")
def data_br(valor):
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return valor


# ----------------------------------------------------------------------
# VALIDAÇÕES
# ----------------------------------------------------------------------
def cpf_valido(cpf):
    d = re.sub(r"\D", "", cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(d[n]) * (i + 1 - n) for n in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(d[i]):
            return False
    return True


MSG_CPF_REPETIDO = "Já existe uma candidatura enviada com este CPF."


def validar(valores):
    erros = []

    nome = valores.get("nome", "")
    if len(nome.split()) < 2:
        erros.append("Informe seu nome completo.")
    elif len(nome) > 120:
        erros.append("O nome está muito longo.")

    cpf = valores.get("cpf", "")
    if not cpf_valido(cpf):
        erros.append("CPF inválido.")
    elif database.cpf_existe(cpf):
        erros.append(MSG_CPF_REPETIDO)

    telefone = re.sub(r"\D", "", valores.get("telefone", ""))
    if len(telefone) not in (10, 11):
        erros.append("Telefone inválido. Informe o DDD e o número.")

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", valores.get("email", "")):
        erros.append("E-mail inválido.")

    experiencia = valores.get("experiencia", "")
    if not experiencia:
        erros.append("Descreva sua experiência profissional.")
    elif len(experiencia) > 2000:
        erros.append("A experiência profissional deve ter no máximo 2000 caracteres.")

    for numero, p in enumerate(PERGUNTAS, start=1):
        resposta = valores.get(p["id"], "")
        if not resposta:
            erros.append(f"Responda a questão {numero}.")
        elif p["tipo"] == "multipla" and resposta not in p["opcoes"]:
            erros.append(f"Alternativa inválida na questão {numero}.")
        elif p["tipo"] == "aberta" and len(resposta) > 2000:
            erros.append(f"A resposta da questão {numero} deve ter no máximo 2000 caracteres.")

    return erros


# ----------------------------------------------------------------------
# CORREÇÃO DA PROVA
# ----------------------------------------------------------------------
def corrigir(valores):
    respostas = []
    acertos = 0
    total = 0

    for numero, p in enumerate(PERGUNTAS, start=1):
        resposta = valores.get(p["id"], "")

        if p["tipo"] == "multipla":
            total += 1
            acertou = resposta == p["correta"]
            if acertou:
                acertos += 1
            respostas.append({
                "numero": numero,
                "texto": p["texto"],
                "tipo": "multipla",
                "resposta": f'{resposta}) {p["opcoes"][resposta]}',
                "acertou": acertou,
                "correta": f'{p["correta"]}) {p["opcoes"][p["correta"]]}',
            })
        else:
            respostas.append({
                "numero": numero,
                "texto": p["texto"],
                "tipo": "aberta",
                "resposta": resposta,
            })

    return respostas, acertos, total


# ----------------------------------------------------------------------
# ROTAS DO CANDIDATO
# ----------------------------------------------------------------------
def pagina_formulario(valores=None, erros=None, status=200):
    html = render_template(
        "index.html",
        empresa=EMPRESA,
        vaga=VAGA,
        perguntas=PERGUNTAS,
        valores=valores or {},
        erros=erros or [],
    )
    return html, status


@app.route("/")
def index():
    return pagina_formulario()


@app.route("/enviar", methods=["POST"])
def enviar():
    valores = {chave: valor.strip() for chave, valor in request.form.items()}

    erros = validar(valores)
    if erros:
        return pagina_formulario(valores, erros, status=400)

    respostas, acertos, total = corrigir(valores)

    try:
        database.salvar_candidato(valores, VAGA["cargo"], acertos, total, respostas)
    except sqlite3.IntegrityError:
        # dois envios ao mesmo tempo com o mesmo CPF
        return pagina_formulario(valores, [MSG_CPF_REPETIDO], status=400)
    except sqlite3.Error:
        # não impede o candidato de ver o resultado, mas registra o problema
        app.logger.exception("Falha ao salvar o candidato no banco de dados")

    candidato = {
        "nome": valores["nome"],
        "cargo": VAGA["cargo"],
        "salario": VAGA["salario"],
        "horario_de_trabalho": VAGA["horario"],
    }

    return render_template(
        "resultado.html",
        empresa=EMPRESA,
        candidato=candidato,
        acertos=acertos,
        total=total,
        respostas=respostas,
    )


# ----------------------------------------------------------------------
# ÁREA ADMINISTRATIVA (protegida por usuário e senha)
# ----------------------------------------------------------------------
def exige_admin(funcao):
    @wraps(funcao)
    def interna(*args, **kwargs):
        if not ADMIN_SENHA:
            abort(404)  # sem senha configurada, a área admin não existe

        auth = request.authorization
        usuario_ok = auth and compare_digest(
            (auth.username or "").encode(), ADMIN_USUARIO.encode()
        )
        senha_ok = auth and compare_digest(
            (auth.password or "").encode(), ADMIN_SENHA.encode()
        )
        if not (usuario_ok and senha_ok):
            return Response(
                "Acesso restrito.",
                401,
                {"WWW-Authenticate": 'Basic realm="Area administrativa"'},
            )
        return funcao(*args, **kwargs)

    return interna


@app.route("/admin")
@exige_admin
def admin():
    candidatos = database.listar_candidatos()
    notas = [c["acertos"] / c["total"] for c in candidatos if c["total"]]
    media = round(sum(notas) / len(notas) * 100) if notas else 0
    return render_template(
        "admin.html", empresa=EMPRESA, candidatos=candidatos, media=media
    )


@app.route("/admin/<int:candidato_id>")
@exige_admin
def admin_candidato(candidato_id):
    candidato = database.buscar_candidato(candidato_id)
    if candidato is None:
        abort(404)
    return render_template(
        "admin_candidato.html",
        empresa=EMPRESA,
        c=candidato,
        respostas=database.listar_respostas(candidato_id),
    )


def _seguro_csv(valor):
    """Evita que o Excel execute textos que começam com = + - @ como fórmula."""
    texto = str(valor)
    return "'" + texto if texto and texto[0] in "=+-@\t\r" else texto


@app.route("/admin/exportar.csv")
@exige_admin
def admin_exportar():
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(
        ["ID", "Nome", "CPF", "Telefone", "E-mail", "Cargo", "Acertos", "Total", "Data", "Experiência"]
    )
    for c in database.listar_candidatos():
        escritor.writerow([
            c["id"],
            _seguro_csv(c["nome"]),
            formatar_cpf(c["cpf"]),
            _seguro_csv(c["telefone"]),
            _seguro_csv(c["email"]),
            _seguro_csv(c["cargo"]),
            c["acertos"],
            c["total"],
            data_br(c["criado_em"]),
            _seguro_csv(c["experiencia"]),
        ])

    return Response(
        "\ufeff" + saida.getvalue(),  # BOM para o Excel abrir os acentos certos
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=candidatos.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True)