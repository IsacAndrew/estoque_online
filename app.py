import os, hashlib, math, json, random
from datetime import datetime
from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import pool

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

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
    "Baby Look":        {"cores": ["Preto", "Off-White"], "emoji": "👚"},
    "Body Manga Curta": {"cores": ["Preto", "Off-White", "Marrom", "Azul", "Vermelho"], "emoji": "👕"},
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
            # Migração: remove restrição NOT NULL do barcode se ainda existir
            try:
                c.execute("ALTER TABLE movimentacoes ALTER COLUMN barcode DROP NOT NULL")
            except Exception:
                conn.rollback()
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
            # Remove sessões inativas há mais de 30 segundos (perdeu conexão/fechou browser)
            c.execute("""DELETE FROM sessoes WHERE ultimo_acesso < to_char(
                NOW() - INTERVAL '30 seconds', 'YYYY-MM-DD HH24:MI:SS')""")
            conn.commit()
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
            tempo = ""-""
        resultado.append({"nome": nome, "ultimo_acesso": ultimo, "tempo_conectado": tempo})
    return resultado

def obter_dados_info(data_ini, data_fim):
    conn = get_conn()
    p = (data_ini + " 00:00:00", data_fim + " 23:59:59")
    try:
        with conn.cursor() as c:
            sql_sum = "SELECT COALESCE(SUM(quantidade),0) FROM movimentacoes WHERE tipo=%s AND data_hora >= %s AND data_hora < %s"
            c.execute(sql_sum, ("saida",) + p)
            total_saidas = c.fetchone()[0]
            c.execute(sql_sum, ("entrada",) + p)
            total_entradas = c.fetchone()[0]
            sql_top = "SELECT cor, SUM(quantidade) as total FROM movimentacoes WHERE tipo=%s AND data_hora >= %s AND data_hora < %s GROUP BY cor ORDER BY total DESC LIMIT 1"
            c.execute(sql_top, ("saida",) + p)
            row = c.fetchone()
            cor_mais_saiu = (row[0] + " (" + str(row[1]) + " un.)") if row else ""-""
            c.execute(sql_top, ("entrada",) + p)
            row2 = c.fetchone()
            cor_mais_entrou = (row2[0] + " (" + str(row2[1]) + " un.)") if row2 else ""-""
        return {"total_saidas": total_saidas, "total_entradas": total_entradas,
                "cor_mais_saiu": cor_mais_saiu, "cor_mais_entrou": cor_mais_entrou}
    
