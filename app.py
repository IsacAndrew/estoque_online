import os, hashlib, math, json, random
from datetime import datetime
from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import pool

# ============================================================================
# CONFIGURAÇÃO
# =============================================================================

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Inicializa o banco sempre que o app subir (Render / Gunicorn)
#try:
#    inicializar_banco()
#    print("Banco inicializado com sucesso")
#except Exception as e:
#    print("Erro ao inicializar banco:", e)

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool

def get_conn():
    return get_pool().getconn()

def release_conn(conn):
    get_pool().putconn(conn)

CATALOGO_INICIAL = {
    "Baby Cropped": {"cores": ["Amarelo", "Preto", "Rosa", "Marrom", "Vermelho"], "emoji": "👚"},
    "Baby Look":    {"cores": ["Amarelo", "Azul", "Lilás", "Marrom", "Off-White", "Preto", "Rosa", "Vermelho", "Verde Band.", "Amarelo Band.", "Azul Band."], "emoji": "👕"},
    "Baby Tee":     {"cores": ["Preto", "Off-White", "Rosa", "Azul Bebê", "Vermelho", "Vinho", "Azul Marinho", "Cinza", "Marrom"], "emoji": "👔"}, 
    "Blusinha Manga Longa": {"cores": ["Preto", "Verde", "Marrom", "Vinho", "Azul Marinho"], "emoji": "👕"},
    "Blusinha Regata": {"cores": ["Vinho", "Marrom", "Azul Marinho", "Preto", "Vermelho", "Azul Band.", "Amarelo Band.", "Verde Band."], "emoji": "👗"}, 
    "Body Gola Quadrada": {"cores": ["Marrom", "Azul", "Cinza", "Preto"], "emoji": "🧥"},
    "Body Manga Curta": {"cores": ["Vinho", "Marrom", "Azul Marinho", "Branco", "Cinza", "Preto"], "emoji": "👕"},
    "Body Regata": {"cores": ["Marrom", "Branco", "Preto", "Cinza", "Azul Marinho"], "emoji": "🩱"},
    "Costa Nua": {"cores": ["Vermelho", "Azul Bebê", "Marrom", "Verde", "Preto"], "emoji": "🩱"},
    "Cropped Manga Longa": {"cores": ["Marrom", "Preto"], "emoji": "👔"},
    "Body Gola Alta": {"cores": ["Preto", "Bege", "Marrom", "Cinza"], "emoji": "🧥"},
    "Mula Manca": {"cores": ["Preto", "Vermelho", "Azul Bebê", "Rosa", "Marrom"], "emoji": "👚"},
    "Top Academia": {"cores": ["Marrom", "Cinza", "Branco", "Azul Marinho", "Lilás", "Preto", "Amarelo", "Bege", "Azul Bebê", "Vermelho", "Vinho"], "emoji": "👕"},
    "Top Tube Faixa": {"cores": ["Preto", "Azul Marinho", "Marrom", "Branco", "Cinza"], "emoji": "👙"},
    "Blusinha T-Shirt": {"cores": ["Vinho", "Azul Marinho", "Marrom", "Verde", "Preto"], "emoji": "🎀"},
}

EMOJIS = ["👚","👗","🩱","👘","👕","🧣","🎀","👙","👖","🧥","👔","🥻","🩲","🧦","👒","👜"]

# =============================================================================
# BANCO DE DADOS
# =============================================================================

def _hash(s):
    return hashlib.sha256(s.encode()).hexdigest()

def inicializar_banco():
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS catalogo (
                    id SERIAL PRIMARY KEY,
                    modelo TEXT NOT NULL,
                    cor TEXT NOT NULL,
                    emoji TEXT NOT NULL DEFAULT '👕',
                    UNIQUE(modelo, cor)
                );
                CREATE TABLE IF NOT EXISTS estoque (
                    id SERIAL PRIMARY KEY,
                    modelo TEXT NOT NULL,
                    cor TEXT NOT NULL,
                    quantidade INTEGER DEFAULT 0,
                    UNIQUE(modelo, cor)
                );
                CREATE TABLE IF NOT EXISTS movimentacoes (
                    id SERIAL PRIMARY KEY,
                    modelo TEXT NOT NULL,
                    cor TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    data_hora TEXT NOT NULL,
                    usuario TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL UNIQUE,
                    senha TEXT NOT NULL,
                    tipo TEXT NOT NULL DEFAULT 'colaborador'
                );
                CREATE TABLE IF NOT EXISTS config (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessoes (
                    nome TEXT PRIMARY KEY,
                    ultimo_acesso TEXT NOT NULL,
                    login_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mensagens (
                    id SERIAL PRIMARY KEY,
                    usuario TEXT NOT NULL,
                    texto TEXT NOT NULL,
                    data_hora TEXT NOT NULL
                );
            """)
            c.execute("INSERT INTO config VALUES ('nome_empresa','Grupo Multi AS') ON CONFLICT DO NOTHING")
            c.execute("SELECT COUNT(*) FROM catalogo")
            if c.fetchone()[0] == 0:
                for modelo, d in CATALOGO_INICIAL.items():
                    for cor in d["cores"]:
                        c.execute(
                            "INSERT INTO catalogo (modelo,cor,emoji) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                            (modelo, cor, d["emoji"])
                        )
            c.execute("SELECT modelo,cor FROM catalogo")
            for modelo, cor in c.fetchall():
                c.execute(
                    "INSERT INTO estoque (modelo,cor,quantidade) VALUES (%s,%s,0) ON CONFLICT DO NOTHING",
                    (modelo, cor)
                )
            c.execute("INSERT INTO usuarios (nome,senha,tipo) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                      ("isac", _hash("102030"), "administrador"))
            # Garante que só existe um programador; cria se não existir
            c.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='programador'")
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO usuarios (nome,senha,tipo) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                          ("programador", _hash("prog123"), "programador"))
        conn.commit()
    finally:
        release_conn(conn)

# =============================================================================
# FUNÇÕES DE NEGÓCIO
# =============================================================================

def obter_nome_empresa():
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT valor FROM config WHERE chave='nome_empresa'")
            r = c.fetchone()
        return r[0] if r else "Grupo Multi AS"
    finally:
        release_conn(conn)

def salvar_nome_empresa(nome):
    nome = nome.strip()
    if not nome:
        return {"sucesso": False, "mensagem": "Nome vazio."}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO config VALUES ('nome_empresa',%s) ON CONFLICT(chave) DO UPDATE SET valor=%s", (nome, nome))
        conn.commit()
        return {"sucesso": True, "mensagem": "Nome atualizado."}
    finally:
        release_conn(conn)

def obter_catalogo():
    r = {}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT modelo,cor,emoji FROM catalogo ORDER BY modelo,cor")
            for modelo, cor, emoji in c.fetchall():
                if modelo not in r:
                    r[modelo] = {"cores": [], "emoji": emoji}
                r[modelo]["cores"].append(cor)
    finally:
        release_conn(conn)
    return r

def registrar_produto_novo(modelo, cores):
    modelo = modelo.strip()
    cores = [c.strip() for c in cores if c.strip()]
    if not modelo:
        return {"sucesso": False, "mensagem": "Nome obrigatório."}
    if not cores:
        return {"sucesso": False, "mensagem": "Informe pelo menos uma cor."}
    emoji = random.choice(EMOJIS)
    adicionados = 0
    conn = get_conn()
    try:
        with conn.cursor() as c:
            for cor in cores:
                c.execute("INSERT INTO catalogo (modelo,cor,emoji) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                          (modelo, cor, emoji))
                if c.rowcount > 0:
                    c.execute("INSERT INTO estoque (modelo,cor,quantidade) VALUES (%s,%s,0) ON CONFLICT DO NOTHING",
                              (modelo, cor))
                    adicionados += 1
        conn.commit()
    finally:
        release_conn(conn)
    if adicionados == 0:
        return {"sucesso": False, "mensagem": "Produto já existe."}
    return {"sucesso": True, "mensagem": f"{adicionados} cor(es) adicionada(s) a '{modelo}'."}

def obter_estoque_completo():
    r = {}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT modelo,cor,quantidade FROM estoque ORDER BY modelo,cor")
            for modelo, cor, qtd in c.fetchall():
                r.setdefault(modelo, {})[cor] = qtd
    finally:
        release_conn(conn)
    return r

def obter_alertas():
    estoque = obter_estoque_completo()
    cat = obter_catalogo()
    zerados, baixos = [], []
    for modelo, dados in cat.items():
        for cor in dados["cores"]:
            qtd = estoque.get(modelo, {}).get(cor, 0)
            if qtd == 0:
                zerados.append({"modelo": modelo, "cor": cor, "qtd": 0})
            elif qtd <= 10:
                baixos.append({"modelo": modelo, "cor": cor, "qtd": qtd})
    return {"zerados": zerados, "baixos": baixos}

def obter_historico(pagina=1, por_pagina=20, filtros=None, usuario_filtro=None, tipo_usuario=None):
    filtros = filtros or {}
    clausulas, params = [], []
    _mapa = {
        "usuario":    "COALESCE(usuario,'')",
        "data_hora":  "data_hora",
        "modelo":     "modelo",
        "cor":        "cor",
        "tipo":       "tipo",
        "quantidade": "CAST(quantidade AS TEXT)",
    }
    # Colaborador só vê as próprias movimentações
    if tipo_usuario == "colaborador" and usuario_filtro:
        clausulas.append("LOWER(COALESCE(usuario,'')) = LOWER(%s)")
        params.append(usuario_filtro)

    for chave, coluna in _mapa.items():
        val = str(filtros.get(chave, "")).strip()
        if val:
            clausulas.append(f"LOWER({coluna}) LIKE LOWER(%s)")
            params.append(f"%{val}%")

    where = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    offset = (pagina - 1) * por_pagina
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute(f"SELECT COUNT(*) FROM movimentacoes {where}", params)
            total = c.fetchone()[0]
            c.execute(
                f"SELECT modelo,cor,tipo,quantidade,data_hora,usuario FROM movimentacoes "
                f"{where} ORDER BY id DESC LIMIT %s OFFSET %s",
                params + [por_pagina, offset]
            )
            rows = c.fetchall()
    finally:
        release_conn(conn)
    registros = [{"modelo": r[0], "cor": r[1], "tipo": r[2],
                  "quantidade": r[3], "data_hora": r[4], "usuario": r[5]} for r in rows]
    return {
        "registros": registros,
        "pagina_atual": pagina,
        "total_paginas": max(1, math.ceil(total / por_pagina)),
        "total_registros": total,
    }

def limpar_historico(nome_admin, senha):
    auth = autenticar_usuario(nome_admin, senha)
    if not auth.get("sucesso"):
        return {"sucesso": False, "mensagem": "Senha incorreta."}
    if auth.get("tipo") not in ("administrador", "programador"):
        return {"sucesso": False, "mensagem": "Sem permissão."}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM movimentacoes")
        conn.commit()
        return {"sucesso": True, "mensagem": "Histórico apagado com sucesso."}
    finally:
        release_conn(conn)

def ajustar_quantidade_direta(modelo, cor, nova_qtd, usuario=""):
    nova_qtd = int(nova_qtd)
    print(f"[AJUSTE] usuario={usuario} modelo={modelo} cor={cor} nova_qtd={nova_qtd}", flush=True)
    if nova_qtd < 0:
        return {"sucesso": False, "mensagem": "Quantidade não pode ser negativa."}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT quantidade FROM estoque WHERE modelo=%s AND cor=%s", (modelo, cor))
            row = c.fetchone()
            if not row:
                print(f"[AJUSTE] ERRO: produto não encontrado", flush=True)
                return {"sucesso": False, "mensagem": "Produto não encontrado."}
            atual = row[0]
            print(f"[AJUSTE] atual={atual} -> novo={nova_qtd}", flush=True)
            diff = nova_qtd - atual
            if diff == 0:
                print(f"[AJUSTE] sem alteração, retornando atual", flush=True)
                return {"sucesso": True, "quantidade": atual}
            tipo = "entrada" if diff > 0 else "saida"
            c.execute("UPDATE estoque SET quantidade=%s WHERE modelo=%s AND cor=%s", (nova_qtd, modelo, cor))
            c.execute(
                "INSERT INTO movimentacoes (modelo,cor,tipo,quantidade,data_hora,usuario) VALUES (%s,%s,%s,%s,%s,%s)",
                (modelo, cor, tipo, abs(diff), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), usuario)
            )
        conn.commit()
        print(f"[AJUSTE] sucesso: {modelo}/{cor} {atual}->{nova_qtd}", flush=True)
        alerta = None
        if nova_qtd == 0:
            alerta = f"⚠️ Atenção! {modelo} da cor {cor} está zerado"
        elif nova_qtd <= 10:
            alerta = f"⚠️ Atenção! {modelo} da cor {cor} está com estoque baixo"
        return {"sucesso": True, "quantidade": nova_qtd, "tipo": tipo, "diff": abs(diff), "alerta": alerta}
    except Exception as e:
        print(f"[AJUSTE] EXCEÇÃO: {e}", flush=True)
        conn.rollback()
        return {"sucesso": False, "mensagem": str(e)}
    finally:
        release_conn(conn)

def autenticar_usuario(nome, senha):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT nome,tipo FROM usuarios WHERE LOWER(nome)=LOWER(%s) AND senha=%s",
                      (nome.strip(), _hash(senha)))
            r = c.fetchone()
    finally:
        release_conn(conn)
    if r:
        return {"sucesso": True, "nome": r[0], "tipo": r[1]}
    return {"sucesso": False, "mensagem": "Usuário ou senha incorretos."}

def cadastrar_usuario(nome, senha, tipo, solicitante_tipo=""):
    nome = nome.strip()
    tipo = tipo.strip().lower()
    if not nome or not senha:
        return {"sucesso": False, "mensagem": "Nome e senha obrigatórios."}
    if tipo not in ("administrador", "colaborador", "programador"):
        return {"sucesso": False, "mensagem": "Tipo inválido."}
    # Só programador pode criar programador
    if tipo == "programador" and solicitante_tipo != "programador":
        return {"sucesso": False, "mensagem": "Sem permissão para criar programador."}
    # Só pode existir um programador
    if tipo == "programador":
        conn = get_conn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='programador'")
                if c.fetchone()[0] >= 1:
                    return {"sucesso": False, "mensagem": "Já existe um programador no sistema."}
        finally:
            release_conn(conn)
    conn = get_conn()
    try:
        try:
            with conn.cursor() as c:
                c.execute("INSERT INTO usuarios (nome,senha,tipo) VALUES (%s,%s,%s)", (nome, _hash(senha), tipo))
            conn.commit()
            return {"sucesso": True, "mensagem": f"Usuário '{nome}' cadastrado."}
        except psycopg2.IntegrityError:
            conn.rollback()
            return {"sucesso": False, "mensagem": f"Usuário '{nome}' já existe."}
    finally:
        release_conn(conn)

def alterar_usuario(nome, novo_nome, novo_tipo, nova_senha, solicitante_tipo=""):
    nome = nome.strip()
    novo_nome = (novo_nome or nome).strip()
    novo_tipo = novo_tipo.strip().lower()
    if novo_tipo not in ("administrador", "colaborador", "programador"):
        return {"sucesso": False, "mensagem": "Tipo inválido."}
    conn = get_conn()
    try:
        try:
            with conn.cursor() as c:
                if nova_senha:
                    c.execute("UPDATE usuarios SET nome=%s,tipo=%s,senha=%s WHERE LOWER(nome)=LOWER(%s)",
                              (novo_nome, novo_tipo, _hash(nova_senha), nome))
                else:
                    c.execute("UPDATE usuarios SET nome=%s,tipo=%s WHERE LOWER(nome)=LOWER(%s)",
                              (novo_nome, novo_tipo, nome))
                if c.rowcount == 0:
                    return {"sucesso": False, "mensagem": f"Usuário '{nome}' não encontrado."}
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()
            return {"sucesso": False, "mensagem": f"Nome '{novo_nome}' já está em uso."}
    finally:
        release_conn(conn)
    return {"sucesso": True, "mensagem": "Usuário atualizado."}

def remover_usuario(nome, solicitante):
    if nome.lower() == solicitante.lower():
        return {"sucesso": False, "mensagem": "Não é possível remover a própria conta."}
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM usuarios WHERE LOWER(nome)=LOWER(%s)", (nome,))
            if c.rowcount == 0:
                return {"sucesso": False, "mensagem": f"Usuário '{nome}' não encontrado."}
        conn.commit()
    finally:
        release_conn(conn)
    return {"sucesso": True, "mensagem": f"Usuário '{nome}' removido."}

def listar_usuarios():
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT nome,tipo FROM usuarios ORDER BY nome")
            return [{"nome": r[0], "tipo": r[1]} for r in c.fetchall()]
    finally:
        release_conn(conn)

def _get_tipo(nome):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT tipo FROM usuarios WHERE LOWER(nome)=LOWER(%s)", (nome,))
            r = c.fetchone()
    finally:
        release_conn(conn)
    return r[0] if r else ""

def registrar_sessao(nome):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""INSERT INTO sessoes (nome, ultimo_acesso, login_em) VALUES (%s,%s,%s)
                         ON CONFLICT(nome) DO UPDATE SET ultimo_acesso=%s, login_em=%s""",
                      (nome, agora, agora, agora, agora))
        conn.commit()
    finally:
        release_conn(conn)

def atualizar_sessao(nome):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE sessoes SET ultimo_acesso=%s WHERE LOWER(nome)=LOWER(%s)", (agora, nome))
        conn.commit()
    finally:
        release_conn(conn)

def remover_sessao(nome):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM sessoes WHERE LOWER(nome)=LOWER(%s)", (nome,))
        conn.commit()
    finally:
        release_conn(conn)

def obter_sessoes():
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT nome, ultimo_acesso, login_em FROM sessoes ORDER BY nome")
            rows = c.fetchall()
    finally:
        release_conn(conn)
    agora = datetime.now()
    resultado = []
    for nome, ultimo, login_em in rows:
        try:
            dt_login = datetime.strptime(login_em, "%Y-%m-%d %H:%M:%S")
            segundos = int((agora - dt_login).total_seconds())
            h, rem = divmod(segundos, 3600)
            m, s = divmod(rem, 60)
            tempo = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
        except:
            tempo = "—"
        resultado.append({"nome": nome, "ultimo_acesso": ultimo, "tempo_conectado": tempo})
    return resultado

def obter_dados_info(data):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM movimentacoes WHERE tipo='saida' AND data_hora LIKE %s", (f"{data}%",))
            total_saidas = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM movimentacoes WHERE tipo='entrada' AND data_hora LIKE %s", (f"{data}%",))
            total_entradas = c.fetchone()[0]
            c.execute("""SELECT cor, SUM(quantidade) as total FROM movimentacoes
                         WHERE tipo='saida' AND data_hora LIKE %s GROUP BY cor ORDER BY total DESC LIMIT 1""",
                      (f"{data}%",))
            row = c.fetchone()
            cor_mais_saiu = f"{row[0]} ({row[1]} un.)" if row else "—"
        return {
            "total_saidas": total_saidas,
            "total_entradas": total_entradas,
            "cor_mais_saiu": cor_mais_saiu,
        }
    finally:
        release_conn(conn)

def obter_saidas_modelo_cor(data, modelo, cor):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("""SELECT COALESCE(SUM(quantidade),0) FROM movimentacoes
                         WHERE tipo='saida' AND data_hora LIKE %s AND LOWER(modelo)=LOWER(%s) AND LOWER(cor)=LOWER(%s)""",
                      (f"{data}%", modelo, cor))
            return c.fetchone()[0]
    finally:
        release_conn(conn)

def obter_mensagens(ultimo_id=0):
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT id,usuario,texto,data_hora FROM mensagens WHERE id>%s ORDER BY id ASC", (ultimo_id,))
            return [{"id": r[0], "usuario": r[1], "texto": r[2], "data_hora": r[3]} for r in c.fetchall()]
    finally:
        release_conn(conn)

def enviar_mensagem(usuario, texto):
    texto = texto.strip()
    if not texto:
        return {"sucesso": False, "mensagem": "Mensagem vazia."}
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO mensagens (usuario,texto,data_hora) VALUES (%s,%s,%s)",
                      (usuario, texto, agora))
        conn.commit()
        return {"sucesso": True, "data_hora": agora}
    finally:
        release_conn(conn)

# =============================================================================
# GERAÇÃO DO HTML
# =============================================================================

def gerar_html():
    inicializar_banco()
    estoque  = obter_estoque_completo()
    cat      = obter_catalogo()
    alertas  = obter_alertas()
    nome_emp = obter_nome_empresa()
    agora    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    total    = sum(q for cores in estoque.values() for q in cores.values())

    def _tags_al(lista, cls):
        if not lista:
            return '<span class="al-vazio">Nenhum produto.</span>'
        return "".join(
            f'<span class="al-tag {cls}">{x["modelo"]} — {x["cor"]}'
            + (f' ({x["qtd"]} un.)' if x["qtd"] > 0 else '') + '</span>'
            for x in lista
        )

    abas_html = conteudo_html = ""
    for i, (modelo, dados) in enumerate(cat.items()):
        aba_id  = f"aba_{i}"
        total_m = sum(estoque.get(modelo, {}).get(c, 0) for c in dados["cores"])
        abas_html += (
            f'<button class="tab-btn" data-modelo="{modelo}" onclick="mostrarAba(\'{aba_id}\',this)">'
            f'{dados["emoji"]} {modelo} <span class="badge">{total_m}</span></button>'
        )
        cards = ""
        for cor in dados["cores"]:
            qtd = estoque.get(modelo, {}).get(cor, 0)
            cls = "card-ok" if qtd > 25 else ("card-baixo" if qtd > 10 else "card-zero")
            cid = f"card-{modelo}-{cor}".replace(" ", "_")
            cards += (
                f'<div class="card {cls}" id="{cid}" data-modelo="{modelo}" data-cor="{cor}">'
                f'<div class="card-cor">{cor}</div>'
                f'<div class="card-ctrl">'
                f'  <button class="ctrl-btn" onclick="ajustarCard(this.closest(\'.card\'),-1)">&#9664;</button>'
                f'  <span class="card-qtd" title="Clique para editar" onclick="editarQtd(this)">{qtd}</span>'
                f'  <button class="ctrl-btn" onclick="ajustarCard(this.closest(\'.card\'),1)">&#9654;</button>'
                f'</div>'
                f'<div class="card-label">unidades</div>'
                f'</div>'
            )
        conteudo_html += (
            f'<div id="{aba_id}" class="aba-conteudo" style="display:none">'
            f'<div class="aba-header"><span>{dados["emoji"]} {modelo}</span>'
            f'<span class="total-modelo">Total: {total_m} un.</span></div>'
            f'<div class="cards-grid">{cards}</div></div>'
        )

    cnt_zero  = len(alertas["zerados"])
    cnt_baixo = len(alertas["baixos"])

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sistema de Estoque — {nome_emp}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#333}}
#tela-login{{position:fixed;inset:0;background:#f0f2f5;z-index:9999;display:flex;align-items:center;justify-content:center}}
.login-box{{background:white;border-radius:16px;padding:40px 36px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,.15);text-align:center}}
.login-box h2{{color:#1a2f5a;font-size:1.4rem;margin-bottom:4px}}
.login-box p{{color:#888;font-size:.9rem;margin-bottom:24px}}
.login-input{{width:100%;padding:10px 14px;border-radius:8px;border:2px solid #ddd;font-size:1rem;outline:none;margin-bottom:12px}}
.login-input:focus{{border-color:#1a2f5a}}
.login-btn{{background:#1a2f5a;color:white;border:none;border-radius:8px;padding:11px;width:100%;font-size:1rem;font-weight:700;cursor:pointer}}
.login-btn:hover{{background:#2a4a8a}}
#login-erro{{color:#c62828;font-size:.82rem;margin-top:10px;min-height:18px}}
#app{{display:none}}
header{{background:linear-gradient(135deg,#1a2f5a,#2a4a8a);color:white;padding:16px 30px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 2px 10px rgba(0,0,0,.25)}}
header h1{{font-size:1.6rem;font-weight:800}}
.header-right{{display:flex;align-items:center;gap:16px}}
.header-info{{font-size:.82rem;opacity:.85}}
.total-badge{{background:white;color:#1a2f5a;padding:6px 14px;border-radius:20px;font-weight:bold;font-size:.85rem}}
.usuario-badge{{background:rgba(255,255,255,.15);color:white;padding:5px 12px;border-radius:20px;font-size:.82rem;border:1px solid rgba(255,255,255,.3)}}
.logout-btn{{background:rgba(255,255,255,.1);color:white;border:1px solid rgba(255,255,255,.3);padding:5px 12px;border-radius:8px;cursor:pointer;font-size:.82rem}}
.logout-btn:hover{{background:rgba(255,255,255,.2)}}
.abas-principais{{max-width:1200px;margin:16px auto 0;padding:0 20px;display:flex;gap:8px;flex-wrap:wrap}}
.aba-principal-btn{{padding:10px 20px;border-radius:8px 8px 0 0;cursor:pointer;font-size:.9rem;font-weight:600;border:none;background:#e0e0e0;color:#555}}
.aba-principal-btn.active{{background:#1a2f5a;color:white}}
.aba-principal-conteudo{{display:none}}.aba-principal-conteudo.ativa{{display:block}}
.container{{max-width:1200px;margin:0 auto;padding:0 20px 20px}}
.al-painel{{display:flex;gap:14px;margin-bottom:20px}}
.al-bloco{{flex:1;background:white;border-radius:12px;padding:14px 16px;box-shadow:0 2px 8px rgba(0,0,0,.07)}}
.al-titulo{{font-size:.8rem;font-weight:700;color:#555;margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.al-cnt{{border-radius:20px;padding:1px 7px;font-size:.72rem;font-weight:700;margin-left:4px}}
.al-cnt-zero{{background:#fde8e8;color:#b91c1c}}.al-cnt-baixo{{background:#fef3cd;color:#92400e}}
.al-lista{{display:flex;flex-wrap:wrap;gap:5px;max-height:120px;overflow-y:auto}}
.al-tag{{font-size:.76rem;padding:3px 9px;border-radius:6px;border:1px solid}}
.al-zero{{background:#fef2f2;border-color:#fca5a5;color:#b91c1c}}
.al-baixo{{background:#fffbeb;border-color:#fcd34d;color:#92400e}}
.al-vazio{{font-size:.76rem;color:#aaa;font-style:italic}}
.tabs-bar{{display:flex;flex-wrap:nowrap;gap:8px;margin-bottom:16px;background:white;padding:10px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow-x:auto;scrollbar-width:thin}}
.tab-btn{{background:#f5f5f5;border:2px solid transparent;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:.88rem;font-weight:500;display:flex;align-items:center;gap:6px;white-space:nowrap}}
.tab-btn:hover{{background:#e8eef7;border-color:#2a4a8a}}
.tab-btn.active{{background:#1a2f5a;color:white;border-color:#1a2f5a}}
.badge{{padding:2px 7px;border-radius:10px;font-size:.78rem}}
.tab-btn.active .badge{{background:rgba(255,255,255,.25)}}
.tab-btn:not(.active) .badge{{background:#1a2f5a;color:white}}
.aba-conteudo{{background:white;border-radius:12px;padding:20px 0;box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:16px}}
.aba-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:0 20px 12px;border-bottom:2px solid #f0f2f5;font-size:1.1rem;font-weight:600}}
.total-modelo{{font-size:.85rem;color:#888;font-weight:400}}
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;padding:0 20px}}
.card{{border-radius:10px;padding:14px 10px;text-align:center;border:2px solid}}
.card-ok{{background:#e8f5e9;border-color:#4caf50}}
.card-baixo{{background:#fff8e1;border-color:#ffc107}}
.card-zero{{background:#ffebee;border-color:#f44336}}
.card-cor{{font-size:.82rem;font-weight:600;color:#555;margin-bottom:6px}}
.card-ctrl{{display:flex;align-items:center;justify-content:center;gap:6px;margin:4px 0}}
.ctrl-btn{{background:rgba(0,0,0,.07);border:none;border-radius:5px;width:26px;height:26px;cursor:pointer;font-size:.9rem;display:flex;align-items:center;justify-content:center;transition:background .15s}}
.ctrl-btn:hover{{background:rgba(0,0,0,.18)}}
.card-qtd{{font-size:1.9rem;font-weight:700;line-height:1;cursor:pointer;border-bottom:2px dashed transparent;transition:border-color .2s;min-width:48px;display:inline-block}}
.card-qtd:hover{{border-bottom-color:currentColor}}
.card-ok .card-qtd{{color:#2e7d32}}
.card-baixo .card-qtd{{color:#e65100}}
.card-zero .card-qtd{{color:#c62828}}
.card-label{{font-size:.72rem;color:#888;margin-top:4px}}
.card-qtd-input{{font-size:1.5rem;font-weight:700;width:70px;text-align:center;border:2px solid #1a2f5a;border-radius:6px;outline:none;background:white}}
.legenda{{display:flex;gap:14px;margin-top:8px;justify-content:flex-end;font-size:.78rem;color:#888}}
.leg-item{{display:flex;align-items:center;gap:5px}}
.leg-dot{{width:11px;height:11px;border-radius:50%}}
.historico-wrap{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow-x:auto}}
.hist-topo{{display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
.hist-topo h3{{margin:0;flex:1;color:#1a2f5a;font-size:1rem}}
.hist-btn{{background:#f0f2f5;border:1px solid #ddd;border-radius:8px;padding:5px 14px;font-size:.82rem;font-weight:600;cursor:pointer;transition:background .15s,color .15s}}
.hist-btn:hover{{background:#e0e6f0}}
.hist-btn.ativo{{background:#1a2f5a;color:white;border-color:#1a2f5a}}
.hist-btn-danger{{background:#fde8e8;border-color:#fca5a5;color:#b91c1c}}
.hist-btn-danger:hover{{background:#fca5a5}}
.filtro-painel{{background:#f8f9fb;border:1px solid #e2e6ea;border-radius:10px;padding:14px 16px;margin-bottom:14px;display:none}}
.filtro-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}}
.filtro-campo label{{font-size:.73rem;font-weight:600;color:#666;display:block;margin-bottom:3px}}
.filtro-campo input{{width:100%;padding:6px 9px;border:1.5px solid #ddd;border-radius:7px;font-size:.84rem;outline:none;background:white;transition:border-color .15s;box-sizing:border-box}}
.filtro-campo input:focus{{border-color:#1a2f5a}}
.hist-table{{width:100%;border-collapse:collapse;font-size:.85rem}}
.hist-table th{{background:#f5f7fa;color:#555;font-weight:700;padding:8px 12px;text-align:left;border-bottom:2px solid #e0e0e0}}
.hist-table td{{padding:7px 12px;border-bottom:1px solid #f0f0f0;color:#444}}
.hist-table tr:hover td{{background:#fafafa}}
.admin-wrap{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.admin-wrap h3{{color:#1a2f5a;font-size:1rem;margin-bottom:16px}}
.admin-form{{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin-bottom:16px}}
.admin-grupo{{display:flex;flex-direction:column;gap:4px}}
.admin-label{{font-size:.78rem;font-weight:600;color:#555}}
.admin-input{{padding:7px 11px;border:2px solid #ddd;border-radius:8px;font-size:.9rem;outline:none;background:#fafafa;min-width:150px}}
.admin-input:focus{{border-color:#1a2f5a;background:white}}
.admin-btn{{background:#1a2f5a;color:white;border:none;padding:8px 20px;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer}}
.admin-btn:hover{{background:#2a4a8a}}
.admin-btn.sec{{background:#888}}.admin-btn.sec:hover{{background:#666}}
.admin-feedback{{font-size:.85rem;font-weight:600;padding:8px 14px;border-radius:8px;margin-bottom:14px}}
.adm-ok{{background:#e8f5e9;color:#2e7d32;border:1px solid #4caf50}}
.adm-erro{{background:#ffebee;color:#c62828;border:1px solid #f44336}}
.usuarios-lista{{width:100%;border-collapse:collapse;font-size:.85rem}}
.usuarios-lista th{{background:#f5f7fa;color:#555;font-weight:700;padding:7px 12px;text-align:left;border-bottom:2px solid #e0e0e0}}
.usuarios-lista td{{padding:7px 12px;border-bottom:1px solid #f0f0f0;color:#444;vertical-align:middle}}
.usuarios-lista tr:hover td{{background:#fafafa}}
.usr-tipo-adm{{color:#1a2f5a;font-weight:700}}.usr-tipo-col{{color:#555}}.usr-tipo-prog{{color:#6a0dad;font-weight:700}}
.usr-btn{{border:none;border-radius:6px;padding:3px 10px;font-size:.78rem;font-weight:600;cursor:pointer;margin-left:4px}}
.usr-btn-edit{{background:#e8eef7;color:#1a2f5a}}.usr-btn-edit:hover{{background:#c8d8f0}}
.usr-btn-del{{background:#fde8e8;color:#b91c1c}}.usr-btn-del:hover{{background:#fca5a5}}
.pag-btn{{min-width:34px;height:34px;padding:0 6px;border:1px solid #dadce0;border-radius:4px;background:white;color:#1a2f5a;font-size:.88rem;font-weight:500;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s}}
.pag-btn:hover{{background:#e8eef7;border-color:#1a2f5a}}
.pag-btn.ativo{{background:#1a2f5a;color:white;border-color:#1a2f5a;font-weight:700;cursor:default}}
.pag-btn:disabled{{color:#ccc;border-color:#eee;cursor:default;background:white}}
.pag-reticencias{{color:#aaa;font-size:.88rem;padding:0 4px;line-height:34px}}
/* Notificação flutuante */
#notif-alerta{{position:fixed;top:18px;right:18px;z-index:99999;display:flex;flex-direction:column;gap:8px;max-width:340px}}
.notif-item{{background:#1a2f5a;color:white;padding:12px 18px;border-radius:10px;font-size:.88rem;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.2);cursor:pointer;animation:slideIn .3s ease}}
.notif-item.msg{{background:#2e7d32}}
@keyframes slideIn{{from{{transform:translateX(120%);opacity:0}}to{{transform:translateX(0);opacity:1}}}}
/* Dados e informações */
.dados-wrap{{background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:16px}}
.dados-wrap h3{{color:#1a2f5a;margin-bottom:16px;font-size:1rem}}
.dados-form{{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin-bottom:20px}}
.dados-grupo{{display:flex;flex-direction:column;gap:4px}}
.dados-label{{font-size:.78rem;font-weight:600;color:#555}}
.dados-input{{padding:7px 11px;border:2px solid #ddd;border-radius:8px;font-size:.9rem;outline:none;background:#fafafa}}
.dados-input:focus{{border-color:#1a2f5a;background:white}}
.dados-btn{{background:#1a2f5a;color:white;border:none;padding:8px 20px;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer}}
.dados-btn:hover{{background:#2a4a8a}}
.dados-stats{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:20px}}
.stat-card{{background:#f5f7fa;border-radius:10px;padding:16px;border-left:4px solid #1a2f5a}}
.stat-card .stat-val{{font-size:1.6rem;font-weight:800;color:#1a2f5a}}
.stat-card .stat-lbl{{font-size:.78rem;color:#888;margin-top:4px}}
.dados-sep{{border:none;border-top:1px solid #eee;margin:16px 0}}
/* Aba INFOS */
.infos-wrap{{background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.infos-wrap h3{{color:#6a0dad;margin-bottom:16px;font-size:1rem}}
.infos-table{{width:100%;border-collapse:collapse;font-size:.85rem}}
.infos-table th{{background:#f5f7fa;color:#555;font-weight:700;padding:8px 12px;text-align:left;border-bottom:2px solid #e0e0e0}}
.infos-table td{{padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#444}}
.online-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#4caf50;margin-right:6px}}
/* Chat Observações */
.chat-wrap{{background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;flex-direction:column;height:520px}}
.chat-msgs{{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}}
.chat-msg{{max-width:75%;padding:10px 14px;border-radius:12px;font-size:.88rem;line-height:1.4}}
.chat-msg.minha{{align-self:flex-end;background:#1a2f5a;color:white;border-bottom-right-radius:3px}}
.chat-msg.outra{{align-self:flex-start;background:#f0f2f5;color:#333;border-bottom-left-radius:3px}}
.chat-msg .chat-autor{{font-size:.72rem;font-weight:700;margin-bottom:3px;opacity:.75}}
.chat-msg .chat-hora{{font-size:.68rem;opacity:.6;margin-top:4px;text-align:right}}
.chat-input-row{{display:flex;gap:8px;padding:12px 16px;border-top:1px solid #eee}}
.chat-input{{flex:1;padding:9px 14px;border:2px solid #ddd;border-radius:20px;font-size:.9rem;outline:none}}
.chat-input:focus{{border-color:#1a2f5a}}
.chat-send-btn{{background:#1a2f5a;color:white;border:none;border-radius:20px;padding:9px 20px;font-size:.88rem;font-weight:600;cursor:pointer}}
.chat-send-btn:hover{{background:#2a4a8a}}
/* Novo produto */
.novo-produto-form{{background:#f8f9fb;border:1px solid #e2e6ea;border-radius:10px;padding:16px;margin-bottom:20px}}
.novo-produto-form h4{{color:#1a2f5a;font-size:.9rem;margin-bottom:12px}}
footer{{text-align:center;padding:20px;color:#aaa;font-size:.78rem}}
@media(max-width:600px){{
  header,.al-painel,.abas-principais{{flex-direction:column;gap:10px;text-align:center}}
  .cards-grid{{grid-template-columns:repeat(auto-fit,minmax(100px,1fr))}}
}}
</style>
</head>
<body>

<div id="notif-alerta"></div>

<div id="tela-login">
  <div class="login-box">
    <div style="font-size:2.4rem;margin-bottom:10px">📦</div>
    <h2>Sistema de Estoque</h2>
    <p id="login-empresa">{nome_emp}</p>
    <input id="login-usuario" class="login-input" type="text" placeholder="Usuário"
           onkeydown="if(event.key==='Enter')document.getElementById('login-senha').focus()"/>
    <input id="login-senha" class="login-input" type="password" placeholder="Senha"
           onkeydown="if(event.key==='Enter')fazerLogin()"/>
    <button class="login-btn" onclick="fazerLogin()">Entrar</button>
    <div id="login-erro"></div>
  </div>
</div>

<div id="app">
<header>
  <h1>📦 <span id="nome-empresa-txt">{nome_emp}</span></h1>
  <div class="header-right">
    <div class="header-info">Atualizado: <span id="hdr-hora">{agora}</span></div>
    <div class="total-badge">🏷️ <span id="hdr-total">{total}</span> itens</div>
    <span class="usuario-badge" id="badge-usuario"></span>
    <button class="logout-btn" onclick="fazerLogout()">Sair</button>
  </div>
</header>

<div class="abas-principais">
  <button class="aba-principal-btn active" onclick="trocarAba('estoque',this)">📦 Estoque</button>
  <button class="aba-principal-btn" id="btn-historico" style="display:none" onclick="trocarAba('historico',this)">📋 Histórico</button>
  <button class="aba-principal-btn" id="btn-dados" style="display:none" onclick="trocarAba('dados',this)">📊 Dados e Informações</button>
  <button class="aba-principal-btn" id="btn-admin" style="display:none" onclick="trocarAba('admin',this)">⚙️ Login e Registros</button>
  <button class="aba-principal-btn" onclick="trocarAba('obs',this)">💬 Observações</button>
  <button class="aba-principal-btn" id="btn-infos" style="display:none" onclick="trocarAba('infos',this)">🛠️ INFOS</button>
</div>

<div class="container">

  <!-- ABA ESTOQUE -->
  <div id="aba-estoque" class="aba-principal-conteudo ativa" style="padding-top:16px">
    <div class="al-painel">
      <div class="al-bloco">
        <div class="al-titulo">🔴 Zerados <span class="al-cnt al-cnt-zero" id="cnt-zero">{cnt_zero}</span></div>
        <div class="al-lista" id="al-lista-zero">{_tags_al(alertas["zerados"],"al-zero")}</div>
      </div>
      <div class="al-bloco">
        <div class="al-titulo">🟡 Estoque baixo (1–10 un.) <span class="al-cnt al-cnt-baixo" id="cnt-baixo">{cnt_baixo}</span></div>
        <div class="al-lista" id="al-lista-baixo">{_tags_al(alertas["baixos"],"al-baixo")}</div>
      </div>
    </div>
    <div class="tabs-bar">{abas_html}</div>
    <div id="conteudo-abas">{conteudo_html}</div>
    <div class="legenda">
      <div class="leg-item"><div class="leg-dot" style="background:#4caf50"></div> Normal (&gt;25)</div>
      <div class="leg-item"><div class="leg-dot" style="background:#ffc107"></div> Baixo (11–25)</div>
      <div class="leg-item"><div class="leg-dot" style="background:#f44336"></div> Crítico (0–10)</div>
    </div>
  </div>

  <!-- ABA HISTÓRICO -->
  <div id="aba-historico" class="aba-principal-conteudo" style="padding-top:16px">
    <div class="historico-wrap">
      <div class="hist-topo">
        <h3>📋 Histórico de Movimentações</h3>
        <button id="btn-toggle-filtro" class="hist-btn" onclick="toggleFiltroHist()">🔍 Filtro</button>
        <button id="btn-limpar-hist" class="hist-btn hist-btn-danger" style="display:none" onclick="limparHistoricoWeb()">🗑 Limpar</button>
      </div>
      <div id="filtro-painel" class="filtro-painel">
        <div class="filtro-grid">
          <div class="filtro-campo"><label>Usuário</label><input id="f-usuario" oninput="agendarFiltro()"/></div>
          <div class="filtro-campo"><label>Data/Hora</label><input id="f-data_hora" placeholder="ex: 2025-06" oninput="agendarFiltro()"/></div>
          <div class="filtro-campo"><label>Modelo</label><input id="f-modelo" oninput="agendarFiltro()"/></div>
          <div class="filtro-campo"><label>Cor</label><input id="f-cor" oninput="agendarFiltro()"/></div>
          <div class="filtro-campo"><label>Tipo</label><input id="f-tipo" placeholder="entrada / saida" oninput="agendarFiltro()"/></div>
          <div class="filtro-campo"><label>Qtd</label><input id="f-quantidade" oninput="agendarFiltro()"/></div>
        </div>
        <div style="text-align:right;margin-top:10px">
          <button onclick="limparFiltros()" style="background:none;border:none;color:#999;font-size:.78rem;cursor:pointer;text-decoration:underline">✕ limpar filtros</button>
        </div>
      </div>
      <table class="hist-table">
        <thead><tr><th>Data/Hora</th><th>Usuário</th><th>Modelo</th><th>Cor</th><th>Tipo</th><th>Qtd</th></tr></thead>
        <tbody id="hist-tbody"></tbody>
      </table>
      <div id="hist-paginacao" style="display:flex;justify-content:center;align-items:center;gap:4px;padding:16px 0;flex-wrap:wrap"></div>
    </div>
  </div>

  <!-- ABA DADOS E INFORMAÇÕES -->
  <div id="aba-dados" class="aba-principal-conteudo" style="padding-top:16px">
    <div class="dados-wrap">
      <h3>📊 Dados e Informações</h3>
      <div class="dados-form">
        <div class="dados-grupo">
          <label class="dados-label">Selecione a data</label>
          <input id="dados-data" class="dados-input" type="date"/>
        </div>
        <button class="dados-btn" onclick="carregarDados()">🔍 Consultar</button>
      </div>
      <div class="dados-stats" id="dados-stats" style="display:none">
        <div class="stat-card">
          <div class="stat-val" id="stat-saidas">—</div>
          <div class="stat-lbl">Baixas (saídas) no dia</div>
        </div>
        <div class="stat-card">
          <div class="stat-val" id="stat-entradas">—</div>
          <div class="stat-lbl">Entradas no dia</div>
        </div>
        <div class="stat-card">
          <div class="stat-val" id="stat-cor" style="font-size:1rem;padding-top:6px">—</div>
          <div class="stat-lbl">Cor que mais saiu</div>
        </div>
      </div>
      <hr class="dados-sep">
      <h3>🔎 Saídas por Modelo/Cor</h3>
      <div class="dados-form">
        <div class="dados-grupo">
          <label class="dados-label">Data</label>
          <input id="mc-data" class="dados-input" type="date"/>
        </div>
        <div class="dados-grupo">
          <label class="dados-label">Modelo</label>
          <input id="mc-modelo" class="dados-input" type="text" placeholder="ex: Baby Look"/>
        </div>
        <div class="dados-grupo">
          <label class="dados-label">Cor</label>
          <input id="mc-cor" class="dados-input" type="text" placeholder="ex: Preto"/>
        </div>
        <button class="dados-btn" onclick="carregarSaidasMC()">🔍 Consultar</button>
      </div>
      <div id="mc-resultado" style="font-size:.95rem;color:#1a2f5a;font-weight:600;min-height:24px"></div>
      <hr class="dados-sep">
      <h3>➕ Registrar Novo Produto</h3>
      <div class="novo-produto-form">
        <div class="dados-form">
          <div class="dados-grupo">
            <label class="dados-label">Nome do modelo</label>
            <input id="np-modelo" class="dados-input" type="text" placeholder="ex: Camiseta"/>
          </div>
          <div class="dados-grupo">
            <label class="dados-label">Cores (separadas por vírgula)</label>
            <input id="np-cores" class="dados-input" type="text" placeholder="ex: Preto, Branco, Azul" style="min-width:220px"/>
          </div>
          <button class="dados-btn" onclick="registrarNovoProduto()">➕ Registrar</button>
        </div>
        <div id="np-feedback" style="font-size:.85rem;font-weight:600;min-height:20px"></div>
      </div>
    </div>
  </div>

  <!-- ABA ADMIN -->
  <div id="aba-admin" class="aba-principal-conteudo" style="padding-top:16px">
    <div class="admin-wrap">
      <h3 id="adm-titulo">⚙️ Cadastrar Usuário</h3>
      <div id="admin-feedback" style="display:none" class="admin-feedback"></div>
      <div class="admin-form">
        <input id="adm-editando" type="hidden" value=""/>
        <div class="admin-grupo"><label class="admin-label">Nome</label>
          <input id="adm-nome" class="admin-input" type="text" placeholder="Nome do usuário"/></div>
        <div class="admin-grupo">
          <label class="admin-label">Senha <span id="adm-senha-hint" style="font-weight:400;color:#aaa"></span></label>
          <input id="adm-senha" class="admin-input" type="password" placeholder="Senha"/></div>
        <div class="admin-grupo"><label class="admin-label">Tipo</label>
          <select id="adm-tipo" class="admin-input" style="min-width:140px">
            <option value="colaborador">Colaborador</option>
            <option value="administrador">Administrador</option>
            <option value="programador" id="opt-programador" style="display:none">Programador</option>
          </select></div>
        <button class="admin-btn" onclick="salvarUsuario()">💾 Salvar</button>
        <button class="admin-btn sec" onclick="cancelarEdicao()">✕</button>
      </div>
      <table class="usuarios-lista">
        <thead><tr><th>Usuário</th><th>Tipo</th><th>Ações</th></tr></thead>
        <tbody id="usuarios-lista"><tr><td colspan="3" style="color:#aaa">Carregando...</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- ABA OBSERVAÇÕES -->
  <div id="aba-obs" class="aba-principal-conteudo" style="padding-top:16px">
    <div class="chat-wrap">
      <div class="chat-msgs" id="chat-msgs"></div>
      <div class="chat-input-row">
        <input id="chat-input" class="chat-input" type="text" placeholder="Digite uma mensagem..."
               onkeydown="if(event.key==='Enter')enviarMensagem()"/>
        <button class="chat-send-btn" onclick="enviarMensagem()">Enviar</button>
      </div>
    </div>
  </div>

  <!-- ABA INFOS -->
  <div id="aba-infos" class="aba-principal-conteudo" style="padding-top:16px">
    <div class="infos-wrap">
      <h3>🛠️ INFOS — Usuários Online</h3>
      <table class="infos-table">
        <thead><tr><th>Usuário</th><th>Tempo conectado</th><th>Último acesso</th></tr></thead>
        <tbody id="infos-tbody"><tr><td colspan="3" style="color:#aaa">Carregando...</td></tr></tbody>
      </table>
    </div>
  </div>

</div>
<footer>Sistema de Estoque — {nome_emp}</footer>
</div>

<script>
let usuarioAtual = null, tipoUsuario = null;
let intervalo = null, intervaloInfos = null, intervaloChat = null;
let ultimoMsgId = 0;
let _alertasAnteriores = {{}};
// Mapa de cards alterados recentemente: chave -> timestamp
// atualizarDados ignora esses cards por 3 segundos após um ajuste
const _cardsBloqueados = {{}};

// ── Login / Logout ──────────────────────────────────────────────
async function fazerLogin() {{
  const nome  = document.getElementById('login-usuario').value.trim();
  const senha = document.getElementById('login-senha').value;
  if (!nome||!senha) {{ document.getElementById('login-erro').textContent='Preencha usuário e senha.'; return; }}
  const d = await fetch('/api/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{nome,senha}})}}).then(r=>r.json()).catch(()=>({{}}));
  if (d.sucesso) {{
    usuarioAtual = d.nome; tipoUsuario = d.tipo;
    document.getElementById('tela-login').style.display = 'none';
    document.getElementById('app').style.display = 'block';
    const icone = tipoUsuario==='programador'?'💻 ':tipoUsuario==='administrador'?'👑 ':'👤 ';
    document.getElementById('badge-usuario').textContent = icone + usuarioAtual;

    // Abas por tipo
    if (tipoUsuario === 'administrador' || tipoUsuario === 'programador') {{
      document.getElementById('btn-historico').style.display = 'inline-block';
      document.getElementById('btn-dados').style.display = 'inline-block';
      document.getElementById('btn-admin').style.display = 'inline-block';
      document.getElementById('btn-limpar-hist').style.display = 'inline-block';
      const s = document.getElementById('nome-empresa-txt');
      s.style.cssText = 'cursor:pointer;border-bottom:2px dashed rgba(255,255,255,.4)';
      s.title = 'Clique para editar'; s.onclick = editarNome;
      carregarUsuarios();
    }}
    if (tipoUsuario === 'colaborador') {{
      document.getElementById('btn-historico').style.display = 'inline-block';
    }}
    if (tipoUsuario === 'programador') {{
      document.getElementById('btn-infos').style.display = 'inline-block';
      document.getElementById('opt-programador').style.display = 'block';
      intervaloInfos = setInterval(carregarInfos, 1000);
    }}

    const primeiro = document.querySelector('.tab-btn');
    if (primeiro) primeiro.click();
    intervalo = setInterval(atualizarDados, 2000);
    // Inicia chat polling — primeiro carrega silenciosamente para marcar ID atual
    fetch('/api/mensagens?ultimo_id=0').then(r=>r.json()).then(msgs => {{
      if (msgs && msgs.length) ultimoMsgId = msgs[msgs.length-1].id;
      carregarMensagens();
    }}).catch(()=> carregarMensagens());
    intervaloChat = setInterval(carregarMensagens, 3000);
    // Registra sessão no servidor
    fetch('/api/sessao/registrar', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nome:usuarioAtual}})}});
    // Keepalive da sessão
    setInterval(()=>{{
      if(usuarioAtual) fetch('/api/sessao/ping',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nome:usuarioAtual}})}});
    }}, 10000);
  }} else {{
    document.getElementById('login-erro').textContent = d.mensagem || 'Erro ao entrar.';
  }}
}}

function fazerLogout() {{
  if(usuarioAtual) fetch('/api/sessao/remover',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nome:usuarioAtual}})}});
  usuarioAtual = null; tipoUsuario = null;
  if (intervalo) clearInterval(intervalo);
  if (intervaloInfos) clearInterval(intervaloInfos);
  if (intervaloChat) clearInterval(intervaloChat);
  document.getElementById('app').style.display = 'none';
  document.getElementById('tela-login').style.display = 'flex';
  document.getElementById('login-usuario').value = '';
  document.getElementById('login-senha').value = '';
  document.getElementById('login-erro').textContent = '';
  document.getElementById('btn-historico').style.display = 'none';
  document.getElementById('btn-dados').style.display = 'none';
  document.getElementById('btn-admin').style.display = 'none';
  document.getElementById('btn-infos').style.display = 'none';
  document.getElementById('btn-limpar-hist').style.display = 'none';
  document.getElementById('filtro-painel').style.display = 'none';
  document.getElementById('btn-toggle-filtro').classList.remove('ativo');
  const s = document.getElementById('nome-empresa-txt');
  s.style.cssText = ''; s.title = ''; s.onclick = null;
  ultimoMsgId = 0;
}}

// ── Navegação entre abas ────────────────────────────────────────
function trocarAba(id, btn) {{
  document.querySelectorAll('.aba-principal-conteudo').forEach(el=>el.classList.remove('ativa'));
  document.querySelectorAll('.aba-principal-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById('aba-'+id).classList.add('ativa');
  btn.classList.add('active');
  if (id==='admin') carregarUsuarios();
  if (id==='historico') {{ histPagina=1; carregarHistorico(1); }}
  if (id==='obs') {{ setTimeout(()=>{{const m=document.getElementById('chat-msgs');m.scrollTop=m.scrollHeight;}},100); }}
}}

function mostrarAba(id, btn) {{
  document.querySelectorAll('.aba-conteudo').forEach(el=>el.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById(id).style.display = 'block';
  btn.classList.add('active');
}}

// ── Atualização de dados (cards + alertas) ─────────────────────
async function atualizarDados() {{
  if (!usuarioAtual) return;
  try {{
    const dados = await fetch('/api/estoque').then(r=>r.json());
    for (const [modelo, cores] of Object.entries(dados)) {{
      let tot_m = 0;
      for (const [cor, qtd] of Object.entries(cores)) {{
        tot_m += qtd;
        const chave = modelo + '|' + cor;
        // Ignora cards que estão com requisição em andamento
        if (_cardsBloqueados[chave]) continue;
        const card = document.getElementById('card-'+(modelo+'-'+cor).replace(/ /g,'_'));
        if (!card) continue;
        card.className = 'card '+(qtd>25?'card-ok':qtd>10?'card-baixo':'card-zero');
        const span = card.querySelector('.card-qtd');
        // Não sobrescreve se o usuário estiver digitando (input ativo)
        if (span && span.tagName === 'SPAN') span.textContent = qtd;
      }}
      document.querySelectorAll(`.tab-btn[data-modelo="${{modelo}}"] .badge`).forEach(b => b.textContent = tot_m);
    }}
    document.getElementById('hdr-total').textContent =
      Object.values(dados).reduce((s,c) => s + Object.values(c).reduce((a,b)=>a+b,0), 0);
    const now = new Date();
    document.getElementById('hdr-hora').textContent = now.toLocaleDateString('pt-BR') + ' ' + now.toLocaleTimeString('pt-BR');
    const al = await fetch('/api/alertas').then(r=>r.json());
    const tags = (lista, cls) => lista.length
      ? lista.map(x=>`<span class="al-tag ${{cls}}">${{x.modelo}} — ${{x.cor}}${{x.qtd>0?' ('+x.qtd+' un.)':''}}</span>`).join('')
      : '<span class="al-vazio">Nenhum produto.</span>';
    document.getElementById('al-lista-zero').innerHTML  = tags(al.zerados, 'al-zero');
    document.getElementById('al-lista-baixo').innerHTML = tags(al.baixos,  'al-baixo');
    document.getElementById('cnt-zero').textContent  = al.zerados.length;
    document.getElementById('cnt-baixo').textContent = al.baixos.length;
  }} catch(e) {{}}
}}

// ── Ajuste via botões ← → ──────────────────────────────────────
async function ajustarCard(cardEl, delta) {{
  const span = cardEl.querySelector('.card-qtd');
  if (!span || span.tagName !== 'SPAN') return;
  const nova = Math.max(0, (parseInt(span.textContent) || 0) + delta);
  span.textContent = nova;
  await enviarAjuste(cardEl.dataset.modelo, cardEl.dataset.cor, nova);
}}

function editarQtd(spanEl) {{
  const cardEl = spanEl.closest('.card');
  const modelo = cardEl.dataset.modelo;
  const cor    = cardEl.dataset.cor;
  const atual  = parseInt(spanEl.textContent) || 0;
  const input  = document.createElement('input');
  input.type = 'number'; input.min = '0'; input.value = atual;
  input.className = 'card-qtd-input';
  spanEl.replaceWith(input);
  input.focus(); input.select();
  let confirmado = false;
  const confirmar = async () => {{
    if (confirmado) return; confirmado = true;
    const nova = Math.max(0, parseInt(input.value) || 0);
    const novoSpan = document.createElement('span');
    novoSpan.className = 'card-qtd'; novoSpan.title = 'Clique para editar';
    novoSpan.textContent = nova; novoSpan.onclick = () => editarQtd(novoSpan);
    input.replaceWith(novoSpan);
    if (nova !== atual) await enviarAjuste(modelo, cor, nova);
  }};
  input.addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{ e.preventDefault(); confirmar(); }}
    if (e.key === 'Escape') {{ input.value = atual; confirmar(); }}
  }});
  input.addEventListener('blur', confirmar);
}}

async function enviarAjuste(modelo, cor, nova_qtd) {{
  const chave = modelo + '|' + cor;
  _cardsBloqueados[chave] = Date.now();
  const d = await fetch('/api/ajuste_direto', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{modelo, cor, quantidade: nova_qtd, usuario: usuarioAtual}})
  }}).then(r=>r.json()).catch(() => ({{}}));
  // Atualiza o card com o valor confirmado pelo servidor
  if (d.sucesso) {{
    const card = document.getElementById('card-'+(modelo+'-'+cor).replace(/ /g,'_'));
    if (card) {{
      const qtd = d.quantidade;
      card.className = 'card '+(qtd>25?'card-ok':qtd>10?'card-baixo':'card-zero');
      const span = card.querySelector('.card-qtd');
      if (span && span.tagName==='SPAN') span.textContent = qtd;
    }}
  }}
  if (d.alerta) mostrarNotif(d.alerta, 'alerta');
  // Libera o bloqueio após confirmar — polling pode voltar a atualizar normalmente
  delete _cardsBloqueados[chave];
}}

// ── Notificações flutuantes ────────────────────────────────────
function mostrarNotif(msg, tipo) {{
  const container = document.getElementById('notif-alerta');
  const el = document.createElement('div');
  el.className = 'notif-item' + (tipo==='msg'?' msg':'');
  el.textContent = msg;
  el.onclick = () => el.remove();
  container.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}}

// ── Usuários ───────────────────────────────────────────────────
async function carregarUsuarios() {{
  const lista = await fetch('/api/usuarios').then(r=>r.json()).catch(()=>[]);
  const tbody = document.getElementById('usuarios-lista');
  if (!lista.length) {{ tbody.innerHTML='<tr><td colspan="3" style="color:#aaa;text-align:center">Nenhum usuário.</td></tr>'; return; }}
  tbody.innerHTML = lista.map(u=>{{
    const isAdm = u.tipo==='administrador', isProg = u.tipo==='programador';
    const ehEu  = u.nome.toLowerCase()===usuarioAtual.toLowerCase();
    const cls   = isProg?'usr-tipo-prog':isAdm?'usr-tipo-adm':'usr-tipo-col';
    const icone = isProg?'💻':isAdm?'👑':'👤';
    const label = `<span class="${{cls}}">${{icone}} ${{u.tipo.charAt(0).toUpperCase()+u.tipo.slice(1)}}</span>`;
    const acoes = ehEu
      ? '<span style="color:#aaa;font-size:.75rem">— conta atual —</span>'
      : `<button class="usr-btn usr-btn-edit" onclick="editarUsuario('${{u.nome}}','${{u.tipo}}')">✏️ Editar</button>`
        +`<button class="usr-btn usr-btn-del"  onclick="removerUsuario('${{u.nome}}')">🗑️ Remover</button>`;
    return `<tr><td><strong>${{u.nome}}</strong></td><td>${{label}}</td><td>${{acoes}}</td></tr>`;
  }}).join('');
}}

function editarUsuario(nome, tipo) {{
  document.getElementById('adm-editando').value = nome;
  document.getElementById('adm-nome').value = nome;
  document.getElementById('adm-senha').value = '';
  document.getElementById('adm-tipo').value = tipo;
  document.getElementById('adm-titulo').textContent = '✏️ Editar Usuário: ' + nome;
  document.getElementById('adm-senha-hint').textContent = '(deixe em branco para manter)';
  document.getElementById('adm-nome').focus();
}}

function cancelarEdicao() {{
  document.getElementById('adm-editando').value = '';
  document.getElementById('adm-nome').value = '';
  document.getElementById('adm-senha').value = '';
  document.getElementById('adm-tipo').value = 'colaborador';
  document.getElementById('adm-titulo').textContent = '⚙️ Cadastrar Usuário';
  document.getElementById('adm-senha-hint').textContent = '';
}}

async function salvarUsuario() {{
  const editando = document.getElementById('adm-editando').value;
  const nome  = document.getElementById('adm-nome').value.trim();
  const senha = document.getElementById('adm-senha').value;
  const tipo  = document.getElementById('adm-tipo').value;
  if (!nome) {{ admFb('Informe o nome.',false); return; }}
  if (!editando && !senha) {{ admFb('Informe a senha.',false); return; }}
  const [rota, body] = editando
    ? ['/api/usuarios/alterar', {{nome:editando,novo_nome:nome,novo_tipo:tipo,nova_senha:senha,solicitante:usuarioAtual}}]
    : ['/api/usuarios',         {{nome,senha,tipo,solicitante:usuarioAtual}}];
  const d = await fetch(rota,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}}).then(r=>r.json()).catch(()=>({{}}));
  admFb(d.sucesso?'✅ '+d.mensagem:'❌ '+(d.mensagem||'Erro'), d.sucesso);
  if (d.sucesso) {{ cancelarEdicao(); carregarUsuarios(); }}
}}

async function removerUsuario(nome) {{
  if (!confirm(`Remover "${{nome}}"?`)) return;
  const d = await fetch('/api/usuarios/remover',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{nome,solicitante:usuarioAtual}})}}).then(r=>r.json()).catch(()=>({{}}));
  admFb(d.sucesso?'✅ '+d.mensagem:'❌ '+(d.mensagem||'Erro'), d.sucesso);
  if (d.sucesso) carregarUsuarios();
}}

function admFb(msg, ok) {{
  const fb = document.getElementById('admin-feedback');
  fb.className = 'admin-feedback '+(ok?'adm-ok':'adm-erro');
  fb.textContent = msg; fb.style.display = 'block';
  setTimeout(()=>fb.style.display='none', 3500);
}}

// ── Editar nome da empresa ─────────────────────────────────────
function editarNome() {{
  const atual = document.getElementById('nome-empresa-txt').textContent;
  const novo  = prompt('Editar nome da empresa:', atual);
  if (!novo || novo.trim()===atual) return;
  fetch('/api/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{nome_empresa:novo.trim(),solicitante:usuarioAtual}})}})
  .then(r=>r.json()).then(d=>{{
    if (d.sucesso) {{
      document.getElementById('nome-empresa-txt').textContent = novo.trim();
      document.title = 'Sistema de Estoque — '+novo.trim();
    }} else alert('Erro: '+d.mensagem);
  }});
}}

// ── Histórico ──────────────────────────────────────────────────
let histPagina = 1, _filtroTimer = null;

function coletarFiltros() {{
  const campos = ['usuario','data_hora','modelo','cor','tipo','quantidade'];
  const p = new URLSearchParams();
  campos.forEach(id => {{
    const v = (document.getElementById('f-'+id)?.value||'').trim();
    if (v) p.set(id, v);
  }});
  return p;
}}

async function carregarHistorico(pagina) {{
  histPagina = pagina;
  const filtros = coletarFiltros();
  filtros.set('pagina', pagina);
  filtros.set('tipo_usuario', tipoUsuario);
  filtros.set('usuario_atual', usuarioAtual);
  const dados = await fetch(`/api/historico?${{filtros}}`).then(r=>r.json()).catch(()=>null);
  if (!dados) return;
  const tbody = document.getElementById('hist-tbody');
  if (!dados.registros.length) {{
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#aaa;padding:20px">Nenhuma movimentação.</td></tr>';
  }} else {{
    tbody.innerHTML = dados.registros.map(h => {{
      const cor = h.tipo === 'entrada' ? '#2e7d32' : '#c62828';
      return `<tr><td>${{h.data_hora}}</td><td>${{h.usuario||'—'}}</td><td>${{h.modelo}}</td><td>${{h.cor}}</td>
        <td style="color:${{cor}};font-weight:600">${{h.tipo==='entrada'?'➕':'➖'}} ${{h.tipo.charAt(0).toUpperCase()+h.tipo.slice(1)}}</td>
        <td style="font-weight:700">${{h.quantidade}}</td></tr>`;
    }}).join('');
  }}
  const total = dados.total_paginas, atual = dados.pagina_atual;
  const pg = document.getElementById('hist-paginacao');
  pg.innerHTML = '';
  if (total <= 1) return;
  const btnPag = (label, pag, ativo=false, disabled=false) => {{
    const b = document.createElement('button');
    b.className = 'pag-btn' + (ativo ? ' ativo' : '');
    b.textContent = label;
    if (disabled || ativo) b.disabled = true;
    else b.onclick = () => carregarHistorico(pag);
    return b;
  }};
  const reticencias = () => {{ const s=document.createElement('span'); s.className='pag-reticencias'; s.textContent='…'; return s; }};
  pg.appendChild(btnPag('‹', atual-1, false, atual===1));
  const visiveis = new Set([1, total]);
  for (let p = Math.max(2, atual-2); p <= Math.min(total-1, atual+2); p++) visiveis.add(p);
  const ordenadas = [...visiveis].sort((a,b)=>a-b);
  let anterior = 0;
  for (const p of ordenadas) {{
    if (p - anterior > 1) pg.appendChild(reticencias());
    pg.appendChild(btnPag(p, p, p===atual));
    anterior = p;
  }}
  pg.appendChild(btnPag('›', atual+1, false, atual===total));
}}

function toggleFiltroHist() {{
  const painel = document.getElementById('filtro-painel');
  const btn    = document.getElementById('btn-toggle-filtro');
  const aberto = painel.style.display !== 'none';
  painel.style.display = aberto ? 'none' : 'block';
  btn.classList.toggle('ativo', !aberto);
}}

function agendarFiltro() {{
  clearTimeout(_filtroTimer);
  _filtroTimer = setTimeout(() => carregarHistorico(1), 300);
}}

function limparFiltros() {{
  ['usuario','data_hora','modelo','cor','tipo','quantidade']
    .forEach(id => {{ const el = document.getElementById('f-'+id); if (el) el.value=''; }});
  carregarHistorico(1);
}}

async function limparHistoricoWeb() {{
  if (!confirm('⚠️ Apagar TODO o histórico? Essa ação é irreversível.')) return;
  const senha = prompt('Digite sua senha para confirmar:');
  if (senha === null || senha === '') return;
  const d = await fetch('/api/historico/limpar', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ nome: usuarioAtual, senha }})
  }}).then(r=>r.json()).catch(()=>({{}}));
  if (d.sucesso) {{ alert('✅ ' + d.mensagem); carregarHistorico(1); }}
  else alert('❌ ' + (d.mensagem || 'Erro.'));
}}

setInterval(() => {{
  const aba = document.getElementById('aba-historico');
  if (!aba || !aba.classList.contains('ativa') || !usuarioAtual) return;
  carregarHistorico(histPagina);
}}, 5000);

// ── Dados e Informações ────────────────────────────────────────
async function carregarDados() {{
  const data = document.getElementById('dados-data').value;
  if (!data) {{ alert('Selecione uma data.'); return; }}
  const d = await fetch(`/api/dados_info?data=${{data}}`).then(r=>r.json()).catch(()=>null);
  if (!d) return;
  document.getElementById('dados-stats').style.display = 'grid';
  document.getElementById('stat-saidas').textContent   = d.total_saidas;
  document.getElementById('stat-entradas').textContent = d.total_entradas;
  document.getElementById('stat-cor').textContent      = d.cor_mais_saiu;
}}

async function carregarSaidasMC() {{
  const data   = document.getElementById('mc-data').value;
  const modelo = document.getElementById('mc-modelo').value.trim();
  const cor    = document.getElementById('mc-cor').value.trim();
  if (!data||!modelo||!cor) {{ alert('Preencha data, modelo e cor.'); return; }}
  const d = await fetch(`/api/saidas_mc?data=${{data}}&modelo=${{encodeURIComponent(modelo)}}&cor=${{encodeURIComponent(cor)}}`).then(r=>r.json()).catch(()=>null);
  if (d===null) return;
  document.getElementById('mc-resultado').textContent = `${{modelo}} — ${{cor}}: ${{d.quantidade}} saída(s) em ${{data}}`;
}}

async function registrarNovoProduto() {{
  const modelo = document.getElementById('np-modelo').value.trim();
  const cores  = document.getElementById('np-cores').value.split(',');
  const fb     = document.getElementById('np-feedback');
  const d = await fetch('/api/produto_novo',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{modelo,cores,solicitante:usuarioAtual}})}}).then(r=>r.json()).catch(()=>({{}}));
  fb.style.color = d.sucesso ? '#2e7d32' : '#c62828';
  fb.textContent = d.sucesso ? '✅ '+d.mensagem : '❌ '+(d.mensagem||'Erro');
  if (d.sucesso) {{
    document.getElementById('np-modelo').value = '';
    document.getElementById('np-cores').value = '';
    setTimeout(()=>location.reload(), 1500);
  }}
  setTimeout(()=>fb.textContent='', 4000);
}}

// ── INFOS (apenas programador) ─────────────────────────────────
async function carregarInfos() {{
  if (tipoUsuario !== 'programador') return;
  const dados = await fetch('/api/infos').then(r=>r.json()).catch(()=>null);
  if (!dados) return;
  const tbody = document.getElementById('infos-tbody');
  if (!dados.length) {{
    tbody.innerHTML = '<tr><td colspan="3" style="color:#aaa;text-align:center">Nenhum usuário online.</td></tr>';
    return;
  }}
  tbody.innerHTML = dados.map(u=>
    `<tr><td><span class="online-dot"></span><strong>${{u.nome}}</strong></td>
     <td>${{u.tempo_conectado}}</td><td>${{u.ultimo_acesso}}</td></tr>`
  ).join('');
}}

// ── Chat Observações ───────────────────────────────────────────
async function carregarMensagens() {{
  if (!usuarioAtual) return;
  const dados = await fetch(`/api/mensagens?ultimo_id=${{ultimoMsgId}}`).then(r=>r.json()).catch(()=>null);
  if (!dados || !dados.length) return;

  const container = document.getElementById('chat-msgs');
  const estaEmbaixo = container.scrollHeight - container.scrollTop <= container.clientHeight + 60;

  dados.forEach(msg => {{
    ultimoMsgId = Math.max(ultimoMsgId, msg.id);
    const div = document.createElement('div');
    const minha = msg.usuario.toLowerCase() === usuarioAtual.toLowerCase();
    div.className = 'chat-msg ' + (minha ? 'minha' : 'outra');
    div.innerHTML = (!minha ? `<div class="chat-autor">${{msg.usuario}}</div>` : '')
      + `<div>${{msg.texto}}</div><div class="chat-hora">${{msg.data_hora.slice(11,16)}}</div>`;
    container.appendChild(div);

    // Notificação para mensagens de outros usuários
    if (!minha) {{
      const abaObs = document.getElementById('aba-obs');
      const visivel = abaObs && abaObs.classList.contains('ativa');
      if (!visivel) {{
        mostrarNotif(`📩 Nova mensagem de ${{msg.usuario}}`, 'msg');
      }}
    }}
  }});

  if (estaEmbaixo) container.scrollTop = container.scrollHeight;
}}

async function enviarMensagem() {{
  const input = document.getElementById('chat-input');
  const texto = input.value.trim();
  if (!texto || !usuarioAtual) return;
  input.value = '';
  await fetch('/api/mensagens',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{usuario:usuarioAtual,texto}})}}).catch(()=>{{}});
  await carregarMensagens();
}}
</script>
</body></html>"""

# =============================================================================
# ROTAS FLASK
# =============================================================================

@app.route("/")
@app.route("/index.html")
def index():
    from flask import make_response
    resp = make_response(gerar_html())
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/api/estoque")
def api_estoque():
    return jsonify(obter_estoque_completo())

@app.route("/api/alertas")
def api_alertas():
    return jsonify(obter_alertas())

@app.route("/api/usuarios", methods=["GET"])
def api_listar_usuarios():
    return jsonify(listar_usuarios())

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify({"nome_empresa": obter_nome_empresa()})

@app.route("/api/historico")
def api_historico():
    pagina = int(request.args.get("pagina", 1))
    tipo_usuario = request.args.get("tipo_usuario", "")
    usuario_atual = request.args.get("usuario_atual", "")
    filtros = {}
    for campo in ("usuario", "data_hora", "modelo", "cor", "tipo", "quantidade"):
        v = request.args.get(campo, "").strip()
        if v:
            filtros[campo] = v
    return jsonify(obter_historico(pagina, filtros=filtros,
                                   usuario_filtro=usuario_atual if tipo_usuario=="colaborador" else None,
                                   tipo_usuario=tipo_usuario))

@app.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json(force=True) or {}
    return jsonify(autenticar_usuario(dados.get("nome",""), dados.get("senha","")))

@app.route("/api/historico/limpar", methods=["POST"])
def api_limpar_historico():
    dados = request.get_json(force=True) or {}
    return jsonify(limpar_historico(dados.get("nome",""), dados.get("senha","")))

@app.route("/api/ajuste_direto", methods=["POST"])
def api_ajuste_direto():
    dados = request.get_json(force=True) or {}
    return jsonify(ajustar_quantidade_direta(
        dados["modelo"].strip(), dados["cor"].strip(),
        int(dados.get("quantidade", 0)), dados.get("usuario","").strip()
    ))

@app.route("/api/usuarios", methods=["POST"])
def api_cadastrar_usuario():
    dados = request.get_json(force=True) or {}
    sol = dados.get("solicitante","").strip()
    sol_tipo = _get_tipo(sol)
    if sol_tipo not in ("administrador", "programador"):
        return jsonify({"sucesso": False, "mensagem": "Sem permissão."})
    return jsonify(cadastrar_usuario(dados.get("nome",""), dados.get("senha",""),
                                     dados.get("tipo","colaborador"), sol_tipo))

@app.route("/api/usuarios/alterar", methods=["POST"])
def api_alterar_usuario():
    dados = request.get_json(force=True) or {}
    sol = dados.get("solicitante","").strip()
    sol_tipo = _get_tipo(sol)
    if sol_tipo not in ("administrador", "programador"):
        return jsonify({"sucesso": False, "mensagem": "Sem permissão."})
    return jsonify(alterar_usuario(
        dados.get("nome",""), dados.get("novo_nome",""),
        dados.get("novo_tipo","colaborador"), dados.get("nova_senha",""), sol_tipo
    ))

@app.route("/api/usuarios/remover", methods=["POST"])
def api_remover_usuario():
    dados = request.get_json(force=True) or {}
    sol = dados.get("solicitante","").strip()
    sol_tipo = _get_tipo(sol)
    if sol_tipo not in ("administrador", "programador"):
        return jsonify({"sucesso": False, "mensagem": "Sem permissão."})
    return jsonify(remover_usuario(dados.get("nome",""), sol))

@app.route("/api/config", methods=["POST"])
def api_salvar_config():
    dados = request.get_json(force=True) or {}
    sol = dados.get("solicitante","").strip()
    if _get_tipo(sol) not in ("administrador", "programador"):
        return jsonify({"sucesso": False, "mensagem": "Sem permissão."})
    return jsonify(salvar_nome_empresa(dados.get("nome_empresa","")))

@app.route("/api/dados_info")
def api_dados_info():
    data = request.args.get("data","")
    if not data:
        return jsonify({"erro": "data obrigatória"})
    return jsonify(obter_dados_info(data))

@app.route("/api/saidas_mc")
def api_saidas_mc():
    data   = request.args.get("data","")
    modelo = request.args.get("modelo","")
    cor    = request.args.get("cor","")
    return jsonify({"quantidade": obter_saidas_modelo_cor(data, modelo, cor)})

@app.route("/api/produto_novo", methods=["POST"])
def api_produto_novo():
    dados = request.get_json(force=True) or {}
    sol = dados.get("solicitante","").strip()
    if _get_tipo(sol) not in ("administrador", "programador"):
        return jsonify({"sucesso": False, "mensagem": "Sem permissão."})
    return jsonify(registrar_produto_novo(dados.get("modelo",""), dados.get("cores",[])))

@app.route("/api/sessao/registrar", methods=["POST"])
def api_sessao_registrar():
    dados = request.get_json(force=True) or {}
    registrar_sessao(dados.get("nome",""))
    return jsonify({"sucesso": True})

@app.route("/api/sessao/ping", methods=["POST"])
def api_sessao_ping():
    dados = request.get_json(force=True) or {}
    atualizar_sessao(dados.get("nome",""))
    return jsonify({"sucesso": True})

@app.route("/api/sessao/remover", methods=["POST"])
def api_sessao_remover():
    dados = request.get_json(force=True) or {}
    remover_sessao(dados.get("nome",""))
    return jsonify({"sucesso": True})

@app.route("/api/infos")
def api_infos():
    return jsonify(obter_sessoes())

@app.route("/api/mensagens", methods=["GET"])
def api_get_mensagens():
    ultimo_id = int(request.args.get("ultimo_id", 0))
    return jsonify(obter_mensagens(ultimo_id))

@app.route("/api/mensagens", methods=["POST"])
def api_post_mensagem():
    dados = request.get_json(force=True) or {}
    return jsonify(enviar_mensagem(dados.get("usuario",""), dados.get("texto","")))

# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

