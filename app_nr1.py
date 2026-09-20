from io import BytesIO
from pathlib import Path
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from collections import Counter
import hashlib
import math
import re
import html
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
import tempfile

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    KeepTogether,
)


# ============================================================
# CONFIGURAÇÕES E CONSTANTES DO SISTEMA
# ============================================================

# Caminhos dos Arquivos do Sistema
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo_escritorio.png"
QRCODE_PATH = BASE_DIR / "qrcode_whatsapp.png"

# Identificação da Empresa
NOME_EMPRESA = "OPÇÃO CONSULTORIA"
SUBTITULO = "em Saúde e Segurança do Trabalho"

# Paleta de Cores
HEX_VERDE_ESCURO = "#003C17"
HEX_VERDE = "#329632"
HEX_VERDE_GRAFICO = "#64B42D"
HEX_VERDE_PROTETOR = "#84C758"
HEX_AMARELO = "#E6A100"
HEX_VERMELHO = "#C82333"
HEX_FUNDO_MODERADO = "#FFF2CC"
HEX_FUNDO_ALTO_RISCO = "#F4CCCC"

COLOR_VERDE_ESCURO = colors.HexColor(HEX_VERDE_ESCURO)
COLOR_VERDE = colors.HexColor(HEX_VERDE)
COLOR_VERDE_PROTETOR = colors.HexColor(HEX_VERDE_PROTETOR)
COLOR_BORDER = colors.HexColor("#C8D0C8")
COLOR_TEXT_MAIN = colors.HexColor("#222222")

# Credenciais do Administrador Padrão
ADMIN_USUARIO = "admin"
ADMIN_SENHA = "Admin@123"
ADMIN_NOME = "Administrador do Sistema"

# Dimensões e Margens do Documento PDF (A4)
PDF_MARGIN_LEFT = 1.4 * cm
PDF_MARGIN_RIGHT = 1.4 * cm
PDF_MARGIN_TOP = 3.6 * cm
PDF_MARGIN_BOTTOM = 1.7 * cm
PDF_CONTENT_WIDTH = A4[0] - PDF_MARGIN_LEFT - PDF_MARGIN_RIGHT  # ~18.2 cm

# Tamanhos Globais de Gráficos e Imagens
COVER_LOGO_WIDTH = 28.0 * cm
COVER_LOGO_HEIGHT = 10.5 * cm
HEADER_LOGO_HEIGHT = 50.0
HEADER_QR_SIZE = 50.0

CHART_DONUT_WIDTH = 15.0 * cm
CHART_DONUT_HEIGHT = 7.8 * cm
CHART_STAR_WIDTH = 15.0 * cm
CHART_STAR_HEIGHT = 5.8 * cm

# Mapeamento de acentos para normalização de textos
TRANS_TAB = str.maketrans(
    "áàãâäéèêëíìîïóòõôöúùûüç",
    "aaaaaeeeeiiiiooooouuuuc"
)


# ============================================================
# HELPER DE DATA E HORA
# ============================================================

def agora_str(formato: str = "%d/%m/%Y %H:%M:%S") -> str:
    """Retorna a data e hora atual formatada."""
    return datetime.now().strftime(formato)


# ============================================================
# STREAMLIT - CONFIGURAÇÃO DE PÁGINA E ESTILOS
# ============================================================

st.set_page_config(
    page_title="Opção Consultoria — Avaliação Psicossocial NR-1",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# GERENCIAMENTO ROBUSTO DO ESTADO DA SESSÃO
# ============================================================

SESSION_STATE_PADRAO = {
    "logado": False,
    "logged_in": False,
    "usuario_id": None,
    "user_id": None,
    "usuario": "",
    "nome_usuario": "",
    "perfil": "COLABORADOR",
    "user_role": "COLABORADOR",
    "tela_cadastro": False,
    "current_page": "📊 Processamento",
    "menu_navegacao": "📊 Processamento",
    "upload_version": 0,
    "arquivo_hash": None,
    "df": None,
    "dados_processados": None,
    "nome_arquivo_original": "",
    "pdf_path": None,
}


def inicializar_session_state():
    """Garante a existência das chaves da sessão antes de qualquer acesso."""
    for chave, valor_padrao in SESSION_STATE_PADRAO.items():
        st.session_state.setdefault(chave, valor_padrao)

    # Mantém aliases em sincronia com as chaves já utilizadas pelo sistema.
    st.session_state["logged_in"] = bool(st.session_state.get("logado", False))
    st.session_state["user_id"] = st.session_state.get("usuario_id")
    st.session_state["user_role"] = st.session_state.get("perfil", "COLABORADOR")


inicializar_session_state()

st.markdown(
    f"""
    <style>
        .main {{ background-color: #f7f9f7; }}
        .block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px; }}
        .titulo-principal {{ color: {HEX_VERDE_ESCURO}; font-size: 2rem; font-weight: 800; margin-bottom: 0; }}
        .subtitulo-principal {{ color: #555555; font-size: 1rem; margin-top: 0; margin-bottom: 1rem; }}
        .caixa-marca {{
            border-left: 6px solid {HEX_VERDE_GRAFICO};
            background: white;
            padding: 1rem 1.3rem;
            border-radius: 8px;
            box-shadow: 0 1px 5px rgba(0,0,0,.08);
            margin-bottom: 1rem;
        }}
        .toolbar {{
            background: white;
            padding: .75rem;
            border-radius: 9px;
            border: 1px solid #dfe7df;
            margin-bottom: 1rem;
        }}

        /* =====================================================
           BOTÕES DA TOOLBAR - ESCOPO RESTRITO
           ===================================================== */
        /* A linha que contém o download button identifica exclusivamente
           a toolbar de ações, evitando vazamento para outros botões. */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button {{
            min-height: 52px !important;
            height: 52px !important;
            padding: 0.55rem 1rem !important;
            border-radius: 8px !important;
            font-size: 1rem !important;
            line-height: 1.15 !important;
            font-weight: 700 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            white-space: normal !important;
            border-width: 1px !important;
            box-shadow: 0 2px 7px rgba(0, 0, 0, 0.08) !important;
            transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease !important;
        }}

        /* GERAR RELATÓRIO PDF - Verde Corporativo */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button[data-testid="stBaseButton-primary"] {{
            background: #003C17 !important;
            background-color: #003C17 !important;
            color: #FFFFFF !important;
            border-color: #003C17 !important;
        }}

        /* BAIXAR PDF - Azul Executivo */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button[data-testid="stBaseButton-secondary"] {{
            background: #2A5298 !important;
            background-color: #2A5298 !important;
            color: #FFFFFF !important;
            border-color: #2A5298 !important;
        }}

        /* LIMPAR SESSÃO - Cinza Sóbrio */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button[data-testid="stBaseButton-secondary"] {{
            background: #4B5563 !important;
            background-color: #4B5563 !important;
            color: #FFFFFF !important;
            border-color: #4B5563 !important;
        }}

        /* Hover específico da toolbar */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button[data-testid="stBaseButton-primary"]:hover {{
            background: #329632 !important;
            background-color: #329632 !important;
            border-color: #329632 !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 10px rgba(0, 60, 23, 0.16) !important;
        }}

        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button[data-testid="stBaseButton-secondary"]:hover {{
            background: #1E3A8A !important;
            background-color: #1E3A8A !important;
            border-color: #1E3A8A !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 10px rgba(42, 82, 152, 0.16) !important;
        }}

        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button[data-testid="stBaseButton-secondary"]:hover {{
            background: #374151 !important;
            background-color: #374151 !important;
            border-color: #374151 !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 10px rgba(75, 85, 99, 0.16) !important;
        }}

        /* Foco específico da toolbar */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button:focus,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button:focus,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button:focus-visible,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button:focus-visible {{
            outline: 2px solid rgba(100, 180, 45, 0.35) !important;
            outline-offset: 2px !important;
        }}

        /* Texto e ícones somente nos botões da toolbar */
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button p,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button p {{
            font-size: 1rem !important;
            font-weight: 700 !important;
            line-height: 1.15 !important;
            margin: 0 !important;
        }}

        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div.stButton > button svg,
        div[data-testid="stVerticalBlock"]:has(.toolbar)
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stDownloadButton"])
        div[data-testid="stDownloadButton"] > button svg {{
            width: 1.15rem !important;
            height: 1.15rem !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BANCO DE DADOS - SUPABASE / POSTGRESQL
# ============================================================

COLUNAS_USUARIOS = [
    "id", "nome", "usuario", "senha_hash", "salt",
    "perfil", "status", "criado_em", "aprovado_em", "aprovado_por"
]

COLUNAS_AUDITORIA = [
    "id", "usuario", "acao", "data_hora", "arquivo"
]


class ConexaoPostgreSQL:
    """Adaptador simples para manter a mesma interface usada pelo sistema."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, query: str, params=None):
        cursor = self._connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params)
        return cursor

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is not None:
                self._connection.rollback()
        finally:
            self._connection.close()
        return False


def conectar_banco() -> ConexaoPostgreSQL:
    try:
        database_url = st.secrets["postgres"]["url"]
    except Exception as exc:
        raise RuntimeError(
            'A conexão com o Supabase não foi configurada. '
            'Cadastre [postgres].url nos Secrets do Streamlit Cloud.'
        ) from exc

    if not database_url:
        raise RuntimeError(
            'O Secret "postgres.url" está vazio. Configure a URL de conexão do Supabase.'
        )

    connection = psycopg2.connect(database_url)
    return ConexaoPostgreSQL(connection)


def criar_tabelas(conn: ConexaoPostgreSQL) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios_nr1 (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'COLABORADOR',
            status TEXT NOT NULL DEFAULT 'PENDENTE',
            criado_em TIMESTAMP NOT NULL,
            aprovado_em TIMESTAMP NULL,
            aprovado_por TEXT NULL
        )
        """
    ).close()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auditoria_nr1 (
            id SERIAL PRIMARY KEY,
            usuario TEXT,
            acao TEXT NOT NULL,
            data_hora TIMESTAMP NOT NULL,
            arquivo TEXT
        )
        """
    ).close()
    conn.commit()


def esquema_compativel(conn: ConexaoPostgreSQL) -> bool:
    try:
        tabelas = {
            row["table_name"]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('usuarios_nr1', 'auditoria_nr1')
                """
            ).fetchall()
        }

        if "usuarios_nr1" not in tabelas or "auditoria_nr1" not in tabelas:
            return False

        cols_usuarios = [
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("usuarios_nr1",),
            ).fetchall()
        ]

        cols_auditoria = [
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("auditoria_nr1",),
            ).fetchall()
        ]

        if cols_usuarios != COLUNAS_USUARIOS:
            return False
        if cols_auditoria != COLUNAS_AUDITORIA:
            return False

        return True
    except Exception:
        conn.rollback()
        return False


def gerar_hash_senha(senha: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    senha_hash = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()
    return senha_hash, salt


def verificar_senha(senha: str, senha_hash: str, salt: str) -> bool:
    novo_hash, _ = gerar_hash_senha(senha, salt)
    return secrets.compare_digest(novo_hash, senha_hash)


def registrar_auditoria(usuario: str, acao: str, arquivo: str = "") -> None:
    with conectar_banco() as conn:
        conn.execute(
            """
            INSERT INTO auditoria_nr1 (usuario, acao, data_hora, arquivo)
            VALUES (%s, %s, %s, %s)
            """,
            (usuario, acao, datetime.now(), arquivo),
        ).close()
        conn.commit()


def criar_admin_padrao(conn: ConexaoPostgreSQL) -> None:
    total_usuarios = conn.execute(
        "SELECT COUNT(*) AS total FROM usuarios_nr1"
    ).fetchone()["total"]

    if total_usuarios > 0:
        return

    senha_hash, salt = gerar_hash_senha(ADMIN_SENHA)
    agora = datetime.now()
    conn.execute(
        """
        INSERT INTO usuarios_nr1 (
            nome, usuario, senha_hash, salt, perfil, status,
            criado_em, aprovado_em, aprovado_por
        )
        VALUES (%s, %s, %s, %s, 'ADMIN', 'LIBERADO', %s, %s, 'SISTEMA')
        """,
        (ADMIN_NOME, ADMIN_USUARIO, senha_hash, salt, agora, agora),
    ).close()
    conn.commit()


def recriar_banco_completo() -> None:
    with conectar_banco() as conn:
        conn.execute("DROP TABLE IF EXISTS auditoria_nr1").close()
        conn.execute("DROP TABLE IF EXISTS usuarios_nr1").close()
        conn.commit()
        criar_tabelas(conn)
        criar_admin_padrao(conn)


def inicializar_banco() -> None:
    try:
        with conectar_banco() as conn:
            if not esquema_compativel(conn):
                conn.execute("DROP TABLE IF EXISTS auditoria_nr1").close()
                conn.execute("DROP TABLE IF EXISTS usuarios_nr1").close()
                conn.commit()
                criar_tabelas(conn)
                criar_admin_padrao(conn)
                return

            criar_tabelas(conn)
            criar_admin_padrao(conn)
    except Exception:
        recriar_banco_completo()


# ============================================================
# USUÁRIOS
# ============================================================

def buscar_usuario(usuario: str) -> dict | None:
    with conectar_banco() as conn:
        cursor = conn.execute(
            "SELECT * FROM usuarios_nr1 WHERE LOWER(usuario) = LOWER(%s)",
            (usuario.strip(),),
        )
        return cursor.fetchone()


def autenticar(usuario: str, senha: str) -> dict | None:
    usuario_db = buscar_usuario(usuario)
    if usuario_db is None or usuario_db["status"] != "LIBERADO":
        return None

    if not verificar_senha(senha, usuario_db["senha_hash"], usuario_db["salt"]):
        return None

    return usuario_db


def cadastrar_colaborador(nome: str, usuario: str, senha: str) -> tuple[bool, str]:
    nome = nome.strip()
    usuario = usuario.strip().lower()

    if not nome or not usuario or not senha:
        return False, "Preencha todos os campos."

    if len(senha) < 6:
        return False, "A senha deve possuir pelo menos 6 caracteres."

    with conectar_banco() as conn:
        existente = conn.execute(
            "SELECT id FROM usuarios_nr1 WHERE LOWER(usuario) = LOWER(%s)",
            (usuario,),
        ).fetchone()

        if existente:
            return False, "Esse usuário já existe."

        senha_hash, salt = gerar_hash_senha(senha)
        conn.execute(
            """
            INSERT INTO usuarios_nr1 (nome, usuario, senha_hash, salt, perfil, status, criado_em)
            VALUES (%s, %s, %s, %s, 'COLABORADOR', 'PENDENTE', %s)
            """,
            (nome, usuario, senha_hash, salt, datetime.now()),
        ).close()
        conn.commit()
        return True, "Cadastro realizado. Aguarde a liberação pelo administrador."


def listar_usuarios() -> list[dict]:
    with conectar_banco() as conn:
        return conn.execute(
            """
            SELECT * FROM usuarios_nr1
            ORDER BY
                CASE status
                    WHEN 'PENDENTE' THEN 1
                    WHEN 'LIBERADO' THEN 2
                    WHEN 'BLOQUEADO' THEN 3
                    ELSE 4
                END, nome
            """
        ).fetchall()


def alterar_status_usuario(user_id: int, novo_status: str, aprovador: str) -> None:
    with conectar_banco() as conn:
        conn.execute(
            """
            UPDATE usuarios_nr1
            SET status = %s, aprovado_em = %s, aprovado_por = %s
            WHERE id = %s
            """,
            (novo_status, datetime.now(), aprovador, user_id),
        ).close()
        conn.commit()


# ============================================================
# TRATAMENTO DE ARQUIVOS E RESPOSTAS
# ============================================================

def ler_arquivo(uploaded_file) -> pd.DataFrame:
    nome = uploaded_file.name.lower()

    if nome.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    if nome.endswith(".csv"):
        dados = uploaded_file.getvalue()
        tentativas = [
            ("utf-8-sig", ","), ("utf-8-sig", ";"),
            ("utf-8", ","),     ("utf-8", ";"),
            ("latin1", ","),    ("latin1", ";"),
        ]

        for encoding, separador in tentativas:
            try:
                return pd.read_csv(BytesIO(dados), encoding=encoding, sep=separador)
            except Exception:
                pass

        raise ValueError("Não foi possível interpretar o arquivo CSV.")

    raise ValueError("Formato não suportado. Use CSV ou XLSX.")


def obter_nome_empresa(nome_arquivo: str) -> str:
    nome = Path(nome_arquivo).stem
    nome = re.sub(r"\s*-\s*Riscos\s+Psicossociais\s*$", "", nome, flags=re.IGNORECASE)
    nome = re.sub(r"[^\wÀ-ÿ]+", "_", nome, flags=re.UNICODE)
    nome = re.sub(r"_+", "_", nome).strip("_")
    return nome or "EMPRESA"


def normalizar_texto(valor) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip().lower().translate(TRANS_TAB)


def valor_numerico(valor) -> float | None:
    if pd.isna(valor) or isinstance(valor, bool):
        return None

    if isinstance(valor, (int, float)):
        numero = float(valor)
        return numero if 1 <= numero <= 5 else None

    texto = str(valor).strip().replace(",", ".")
    try:
        numero = float(texto)
        return numero if 1 <= numero <= 5 else None
    except Exception:
        return None


def converter_resposta(valor) -> float | None:
    numero = valor_numerico(valor)
    if numero is not None:
        return numero

    texto = normalizar_texto(valor)
    if "concordo totalmente" in texto or texto == "concordo":
        return 5.0
    if "concordo em parte" in texto:
        return 3.0
    if "discordo" in texto:
        return 1.0

    return None


def obter_estatisticas(serie: pd.Series, numero_questao: int) -> dict:
    respostas_validas = []
    frequencia_numerica = Counter()
    concordo_totalmente = 0
    concordo_parte = 0
    discordo = 0

    # Consolidação dos cálculos em um único loop
    for valor in serie:
        numero = converter_resposta(valor)
        if numero is not None:
            val_float = float(numero)
            respostas_validas.append(val_float)

            inteiro = int(round(val_float))
            if 1 <= inteiro <= 5:
                frequencia_numerica[inteiro] += 1

            if val_float >= 4:
                concordo_totalmente += 1
            elif val_float >= 3:
                concordo_parte += 1
            else:
                discordo += 1

    media = (sum(respostas_validas) / len(respostas_validas)) if respostas_validas else None

    return {
        "media": media,
        "n": len(respostas_validas),
        "distribuicao": {
            "Concordo totalmente": concordo_totalmente,
            "Concordo em parte": concordo_parte,
            "Discordo": discordo,
        },
        "frequencia_numerica": frequencia_numerica,
        "respostas_validas": respostas_validas,
    }


# ============================================================
# CLASSIFICAÇÃO E ANÁLISE TÉCNICA
# ============================================================

def arredondar_classificacao(media: float) -> float | None:
    if media is None:
        return None
    return float(Decimal(str(media)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def classificar_risco(media: float) -> tuple[str, str]:
    if media is None:
        return "SEM DADOS", "#E0E0E0"

    valor = arredondar_classificacao(media)
    if valor <= 2.5:
        return "ALTO RISCO", HEX_FUNDO_ALTO_RISCO
    if valor <= 3.9:
        return "RISCO MODERADO", HEX_FUNDO_MODERADO
    return "BAIXO RISCO / FATOR PROTETOR", HEX_VERDE_PROTETOR


def analise_tecnica(media: float) -> dict:
    if media is None:
        return {
            "titulo": "ANÁLISE TÉCNICA — DADOS INSUFICIENTES",
            "texto": (
                "Não foram identificadas respostas válidas suficientes para emitir "
                "uma interpretação técnica deste indicador."
            ),
            "recomendacoes": [],
        }

    valor = arredondar_classificacao(media)

    if valor <= 2.5:
        return {
            "titulo": "ANÁLISE CRÍTICA — RISCO PSICOSSOCIAL ALTO",
            "texto": (
                f"A média de {media:.2f} situa o indicador na faixa de alto risco psicossocial. "
                "O resultado representa um sinal crítico que demanda intervenção prioritária. "
                "Caso esse padrão se mantenha, pode aumentar a probabilidade de sofrimento psíquico, "
                "afastamentos, absenteísmo e conflitos relacionados às condições de trabalho. "
                "A organização deve tratar o resultado como evidência para revisão das condições "
                "que originaram o indicador."
            ),
            "recomendacoes": [
                (
                    "Reorganizar as condições de trabalho relacionadas ao indicador, revisando "
                    "carga e distribuição de tarefas, prioridades, prazos, recursos disponíveis, "
                    "pausas e clareza de responsabilidades."
                ),
                (
                    "Implantar um plano de intervenção com responsáveis, prazos e indicadores de "
                    "acompanhamento, envolvendo lideranças e trabalhadores e realizando nova medição "
                    "após as ações."
                ),
            ],
        }

    if valor <= 3.9:
        return {
            "titulo": "ANÁLISE DE ALERTA — RISCO PSICOSSOCIAL MODERADO",
            "texto": (
                f"A média de {media:.2f} enquadra o indicador na faixa de risco psicossocial moderado. "
                "O resultado demonstra uma condição de atenção que pode indicar instabilidade ou "
                "fragilidades no fator avaliado. A situação deve ser acompanhada preventivamente para "
                "evitar agravamento e para identificar as causas organizacionais associadas ao resultado."
            ),
            "recomendacoes": [
                (
                    "Realizar uma intervenção preventiva direcionada ao indicador, com escuta dos "
                    "trabalhadores e revisão dos processos, rotinas e condições de trabalho relacionadas."
                ),
                (
                    "Estabelecer acompanhamento periódico do indicador, registrando as medidas adotadas "
                    "e verificando sua efetividade por meio de nova avaliação."
                ),
            ],
        }

    return {
        "titulo": "ANÁLISE TÉCNICA — BAIXO RISCO / FATOR PROTETOR ATIVO",
        "texto": (
            f"A média de {media:.2f} é compatível com baixo risco psicossocial e caracteriza resultado "
            "favorável para o indicador avaliado. O resultado constitui evidência documental favorável "
            "ao gerenciamento preventivo das condições de trabalho e indica a presença de percepção "
            "predominantemente positiva entre os respondentes. Recomenda-se a manutenção das práticas "
            "associadas ao resultado e seu monitoramento periódico. Este resultado não elimina outras "
            "obrigações legais, preventivas ou de gestão, nem representa, isoladamente, garantia de "
            "inexistência de riscos."
        ),
        "recomendacoes": [],
    }


# ============================================================
# GERADORES DE GRÁFICOS (MATPLOTLIB)
# ============================================================

def criar_grafico_donut(distribuicao: dict, media: float, numero_questao: int, caminho: str) -> None:
    labels = ["Concordo totalmente", "Concordo em parte", "Discordo"]
    valores = [distribuicao[label] for label in labels]
    cores_grafico = [HEX_VERDE_GRAFICO, HEX_AMARELO, HEX_VERMELHO]

    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    total = sum(valores)

    if total > 0:
        def autopct(pct):
            return f"{pct:.1f}%" if pct >= 3 else ""

        wedges, _, autotexts = ax.pie(
            valores,
            labels=None,
            colors=cores_grafico,
            startangle=90,
            counterclock=False,
            autopct=autopct,
            pctdistance=0.72,
            wedgeprops={"width": 0.40, "edgecolor": "white", "linewidth": 2},
            textprops={"fontsize": 10, "fontweight": "bold"},
        )

        for texto in autotexts:
            texto.set_color("white")

        texto_central = f"{media:.2f}" if media is not None else "—"
        ax.text(
            0, 0, texto_central,
            ha="center", va="center",
            fontsize=22, fontweight="bold", color=HEX_VERDE_ESCURO,
        )

        textos_legenda = [
            f"{label}: {v} ({(v / total) * 100:.1f}%)"
            for label, v in zip(labels, valores)
        ]

        ax.legend(
            wedges, textos_legenda,
            loc="center left", bbox_to_anchor=(1.00, 0.5),
            frameon=False, fontsize=11, labelspacing=1.2, handlelength=1.4,
        )
    else:
        ax.text(
            0.5, 0.5, "Sem respostas válidas",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=15, color=HEX_VERDE_ESCURO, fontweight="bold",
        )

    ax.set_title("Distribuição das Respostas", fontsize=14, fontweight="bold", color=HEX_VERDE_ESCURO, pad=14)
    ax.set_aspect("equal")
    plt.tight_layout(rect=[0, 0, 0.72, 1])

    fig.savefig(caminho, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pontos_estrela(centro_x: float, centro_y: float, raio_externo: float, raio_interno: float) -> list:
    pontos = []
    for indice in range(10):
        angulo = (math.pi / 2) + indice * (math.pi / 5)
        raio = raio_externo if indice % 2 == 0 else raio_interno
        pontos.append((centro_x + raio * math.cos(angulo), centro_y + raio * math.sin(angulo)))
    return pontos


def _recortar_estrela_verticalmente(pontos: list, limite_x: float) -> list:
    if not pontos:
        return []

    resultado = []
    anterior = pontos[-1]
    anterior_dentro = anterior[0] <= limite_x

    for atual in pontos:
        atual_dentro = atual[0] <= limite_x
        if atual_dentro != anterior_dentro:
            x1, y1 = anterior
            x2, y2 = atual
            y_intersecao = y1 + ((limite_x - x1) / (x2 - x1)) * (y2 - y1) if x2 != x1 else y1
            resultado.append((limite_x, y_intersecao))

        if atual_dentro:
            resultado.append(atual)

        anterior = atual
        anterior_dentro = atual_dentro

    return resultado


def criar_grafico_estrelas_q15(media: float, caminho: str) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 1)

    centros_x = [0.5, 1.5, 2.5, 3.5, 4.5]
    raio_externo = 0.34 * 0.8
    raio_interno = 0.15 * 0.8

    valor = max(0.0, min(5.0, float(media))) if media is not None else 0.0

    for indice, centro_x in enumerate(centros_x):
        pontos = _pontos_estrela(centro_x, 0.63, raio_externo, raio_interno)
        ax.add_patch(Polygon(pontos, closed=True, facecolor="#D0D0D0", edgecolor="none"))

        preenchimento = max(0.0, min(1.0, valor - indice))
        if preenchimento <= 0:
            continue

        x_min = min(p[0] for p in pontos)
        x_max = max(p[0] for p in pontos)
        limite_x = x_min + (x_max - x_min) * preenchimento

        pontos_preenchidos = _recortar_estrela_verticalmente(pontos, limite_x)
        if len(pontos_preenchidos) >= 3:
            ax.add_patch(Polygon(pontos_preenchidos, closed=True, facecolor="#FFC107", edgecolor="none"))

    ax.text(
        2.5, 0.13,
        f"{valor:.1f} / 5" if media is not None else "Sem dados / 5",
        ha="center", va="center", fontsize=13, color="#666666",
    )
    ax.axis("off")
    plt.tight_layout()

    fig.savefig(caminho, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ============================================================
# ESTILOS E COMPONENTES DO PDF
# ============================================================

def estilos_pdf() -> dict:
    estilos = getSampleStyleSheet()

    return {
        "capa_titulo": ParagraphStyle(
            "CapaTitulo", parent=estilos["Title"],
            fontName="Helvetica-Bold", fontSize=19, leading=24,
            alignment=TA_CENTER, textColor=COLOR_VERDE_ESCURO, spaceAfter=14,
        ),
        "capa_empresa": ParagraphStyle(
            "CapaEmpresa", parent=estilos["Normal"],
            fontName="Helvetica-Bold", fontSize=16, leading=20,
            alignment=TA_CENTER, textColor=COLOR_VERDE, spaceBefore=15, spaceAfter=8,
        ),
        "capa_risco": ParagraphStyle(
            "CapaRisco", parent=estilos["Normal"],
            fontName="Helvetica-Bold", fontSize=13, leading=17,
            alignment=TA_CENTER, textColor=COLOR_VERDE_ESCURO, spaceBefore=2, spaceAfter=14,
        ),
        "capa_info": ParagraphStyle(
            "CapaInfo", parent=estilos["Normal"],
            fontName="Helvetica", fontSize=10, leading=14,
            alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
        ),
        "h1": ParagraphStyle(
            "H1Custom", parent=estilos["Heading1"],
            fontName="Helvetica-Bold", fontSize=14, leading=18,
            textColor=COLOR_VERDE_ESCURO, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2Custom", parent=estilos["Heading2"],
            fontName="Helvetica-Bold", fontSize=10.5, leading=14,
            textColor=COLOR_VERDE_ESCURO, spaceBefore=6, spaceAfter=6, keepWithNext=True,
        ),
        "normal": ParagraphStyle(
            "NormalCustom", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=8.7, leading=12,
            alignment=TA_JUSTIFY, textColor=COLOR_TEXT_MAIN, spaceAfter=5,
        ),
        "normal_center": ParagraphStyle(
            "NormalCenter", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=9, leading=12,
            alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
        ),
        "questao": ParagraphStyle(
            "Questao", parent=estilos["BodyText"],
            fontName="Helvetica-Bold", fontSize=10, leading=13,
            textColor=COLOR_VERDE_ESCURO, spaceAfter=5,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=estilos["BodyText"],
            fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "TableCell", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=COLOR_TEXT_MAIN,
        ),
        "table_cell_center": ParagraphStyle(
            "TableCellCenter", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=COLOR_TEXT_MAIN, alignment=TA_CENTER,
        ),
        "analise": ParagraphStyle(
            "Analise", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=8.8, leading=12,
            alignment=TA_JUSTIFY, textColor=COLOR_TEXT_MAIN, spaceAfter=6,
        ),
        "recomendacao": ParagraphStyle(
            "Recomendacao", parent=estilos["BodyText"],
            fontName="Helvetica", fontSize=8.7, leading=12,
            leftIndent=8, firstLineIndent=-8, alignment=TA_JUSTIFY,
            textColor=COLOR_TEXT_MAIN, spaceAfter=5,
        ),
    }


def _estilo_tabela_base(
    bg_header=COLOR_VERDE_ESCURO,
    grid_color=COLOR_BORDER,
    padding_v: int = 5,
    padding_h: int = 6
) -> TableStyle:
    """Gera o estilo base padrão para tabelas do relatório."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), bg_header),
        ("GRID", (0, 0), (-1, -1), 0.35, grid_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), padding_h),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding_h),
        ("TOPPADDING", (0, 0), (-1, -1), padding_v),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding_v),
    ])


def _tabela_imagem_centralizada(imagem: Image, largura_coluna: float = 16.5 * cm) -> Table:
    """Envolve uma imagem em uma tabela para garantir alinhamento centralizado no PDF."""
    tabela = Table([[imagem]], colWidths=[largura_coluna])
    tabela.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tabela


def desenhar_capa(canvas, doc):
    """Callback da capa (sem cabeçalho/rodapé)."""
    return


def desenhar_rodape(canvas, doc):
    """Desenha o rodapé padrão nas páginas internas."""
    canvas.saveState()
    largura, _ = A4

    canvas.setStrokeColor(colors.HexColor("#D5DDD5"))
    canvas.setLineWidth(0.5)
    canvas.line(PDF_MARGIN_LEFT, 1.35 * cm, largura - PDF_MARGIN_RIGHT, 1.35 * cm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#777777"))

    data_hora = getattr(doc, "data_hora_processamento", agora_str("%d/%m/%Y %H:%M"))
    responsavel = getattr(doc, "responsavel_relatorio", "")

    if " " in data_hora:
        data_p, hora_p = data_hora.split(" ", 1)
    else:
        data_p, hora_p = data_hora, ""

    canvas.drawString(PDF_MARGIN_LEFT, 0.95 * cm, f"Data: {data_p}    Hora: {hora_p}")
    if responsavel:
        canvas.drawString(PDF_MARGIN_LEFT, 0.55 * cm, f"Processado por: {responsavel}")

    canvas.drawRightString(largura - PDF_MARGIN_RIGHT, 0.75 * cm, f"Página {doc.page}")
    canvas.restoreState()


def desenhar_cabecalho_e_rodape(canvas, doc):
    """Desenha cabeçalho institucional e rodapé nas páginas internas."""
    canvas.saveState()
    largura, altura = A4
    y_elementos = altura - PDF_MARGIN_LEFT - HEADER_LOGO_HEIGHT

    # Logotipo
    if LOGO_PATH.exists():
        try:
            w_orig, h_orig = ImageReader(str(LOGO_PATH)).getSize()
            largura_logo = (w_orig / h_orig) * HEADER_LOGO_HEIGHT
            canvas.drawImage(
                str(LOGO_PATH), PDF_MARGIN_LEFT, y_elementos,
                width=largura_logo, height=HEADER_LOGO_HEIGHT,
                preserveAspectRatio=True, mask="auto", anchor="sw",
            )
        except Exception:
            pass

    # QR Code
    if QRCODE_PATH.exists():
        try:
            canvas.drawImage(
                str(QRCODE_PATH), largura - PDF_MARGIN_RIGHT - HEADER_QR_SIZE, y_elementos,
                width=HEADER_QR_SIZE, height=HEADER_QR_SIZE,
                preserveAspectRatio=True, mask="auto", anchor="sw",
            )
        except Exception:
            pass

    # Título do Cabeçalho
    canvas.setFont("Helvetica-Bold", 12)
    canvas.setFillColor(COLOR_VERDE_ESCURO)
    canvas.drawCentredString(largura / 2, altura - 2.0 * cm, NOME_EMPRESA)

    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawCentredString(largura / 2, altura - 2.4 * cm, SUBTITULO)

    # Linha Decorativa
    canvas.setStrokeColor(colors.HexColor(HEX_VERDE_GRAFICO))
    canvas.setLineWidth(1.2)
    y_linha = altura - PDF_MARGIN_LEFT - HEADER_LOGO_HEIGHT - 4
    canvas.line(PDF_MARGIN_LEFT, y_linha, largura - PDF_MARGIN_RIGHT, y_linha)

    canvas.restoreState()
    desenhar_rodape(canvas, doc)


# ============================================================
# CONSTRUÇÃO DAS TABELAS DO RELATÓRIO
# ============================================================

def tabela_respostas(estatisticas: dict, estilos: dict) -> Table:
    dist = estatisticas["distribuicao"]
    total = sum(dist.values())
    ordem = ["Concordo totalmente", "Concordo em parte", "Discordo"]

    dados = [
        [
            Paragraph("RESPOSTA", estilos["table_header"]),
            Paragraph("FREQUÊNCIA", estilos["table_header"]),
            Paragraph("%", estilos["table_header"]),
        ]
    ]

    for resposta in ordem:
        freq = dist[resposta]
        perc = (freq / total) * 100 if total > 0 else 0
        dados.append([
            Paragraph(html.escape(resposta), estilos["table_cell"]),
            Paragraph(str(freq), estilos["table_cell_center"]),
            Paragraph(f"{perc:.1f}%", estilos["table_cell_center"]),
        ])

    tabela = Table(dados, colWidths=[9.5 * cm, 3.5 * cm, 3.5 * cm], repeatRows=1)
    estilo = _estilo_tabela_base()
    estilo.add("BACKGROUND", (0, 1), (-1, 1), COLOR_VERDE_PROTETOR)
    estilo.add("BACKGROUND", (0, 2), (-1, 2), colors.HexColor(HEX_FUNDO_MODERADO))
    estilo.add("BACKGROUND", (0, 3), (-1, 3), colors.HexColor(HEX_FUNDO_ALTO_RISCO))
    tabela.setStyle(estilo)
    return tabela


def tabela_numerica_q15(estatisticas: dict, estilos: dict) -> Table:
    frequencias = estatisticas["frequencia_numerica"]
    total = sum(frequencias.values())

    dados = [
        [
            Paragraph("NOTA", estilos["table_header"]),
            Paragraph("FREQUÊNCIA", estilos["table_header"]),
            Paragraph("%", estilos["table_header"]),
        ]
    ]

    for nota in range(1, 6):
        freq = frequencias.get(nota, 0)
        perc = (freq / total) * 100 if total > 0 else 0
        dados.append([
            Paragraph(str(nota), estilos["table_cell_center"]),
            Paragraph(str(freq), estilos["table_cell_center"]),
            Paragraph(f"{perc:.1f}%", estilos["table_cell_center"]),
        ])

    tabela = Table(dados, colWidths=[4 * cm, 4 * cm, 4 * cm], repeatRows=1)
    estilo = _estilo_tabela_base(padding_v=4)
    estilo.add("ALIGN", (0, 0), (-1, -1), "CENTER")
    tabela.setStyle(estilo)
    return tabela


def tabela_criterio_interpretacao(estilos: dict) -> Table:
    dados = [
        [
            Paragraph("FAIXA", estilos["table_header"]),
            Paragraph("CLASSIFICAÇÃO", estilos["table_header"]),
            Paragraph("INTERPRETAÇÃO", estilos["table_header"]),
        ],
        [
            Paragraph("1,0 – 2,5", estilos["table_cell_center"]),
            Paragraph("ALTO RISCO", estilos["table_cell_center"]),
            Paragraph("Sinal crítico de risco psicossocial, exigindo análise e intervenção prioritária.", estilos["table_cell"]),
        ],
        [
            Paragraph("2,6 – 3,9", estilos["table_cell_center"]),
            Paragraph("RISCO MODERADO", estilos["table_cell_center"]),
            Paragraph("Condição de atenção que requer acompanhamento e medidas preventivas.", estilos["table_cell"]),
        ],
        [
            Paragraph("4,0 – 5,0", estilos["table_cell_center"]),
            Paragraph("BAIXO RISCO / FATOR PROTETOR", estilos["table_cell_center"]),
            Paragraph("Resultado favorável, indicando percepção predominantemente positiva do fator avaliado.", estilos["table_cell"]),
        ],
    ]

    tabela = Table(dados, colWidths=[3.3 * cm, 5.2 * cm, 8.2 * cm], repeatRows=1)
    estilo = _estilo_tabela_base(grid_color=colors.HexColor("#BFC9BF"), padding_v=8, padding_h=7)
    estilo.add("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(HEX_FUNDO_ALTO_RISCO))
    estilo.add("BACKGROUND", (0, 2), (-1, 2), colors.HexColor(HEX_FUNDO_MODERADO))
    estilo.add("BACKGROUND", (0, 3), (-1, 3), COLOR_VERDE_PROTETOR)
    tabela.setStyle(estilo)
    return tabela


# ============================================================
# GERAÇÃO DO DOCUMENTO PDF COMPLETO
# ============================================================

def gerar_pdf(df: pd.DataFrame, nome_arquivo_original: str, responsavel: str) -> Path:
    estilos = estilos_pdf()
    nome_empresa = obter_nome_empresa(nome_arquivo_original)
    nome_pdf = f"RAP_{nome_empresa}.pdf"
    caminho_pdf = BASE_DIR / nome_pdf
    pasta_graficos = Path(tempfile.mkdtemp(prefix="graficos_nr1_"))

    try:
        if len(df.columns) < 16:
            raise ValueError("O arquivo precisa possuir pelo menos 16 colunas: uma coluna inicial e 15 perguntas.")

        colunas_questoes = list(df.columns[1:16])
        if len(colunas_questoes) != 15:
            raise ValueError("Não foi possível identificar as 15 perguntas.")

        estatisticas_questoes = [
            {
                "numero": num,
                "coluna": col,
                "estatisticas": obter_estatisticas(df[col], num),
            }
            for num, col in enumerate(colunas_questoes, start=1)
        ]

        todas_respostas = [
            res
            for item in estatisticas_questoes
            for res in item["estatisticas"]["respostas_validas"]
        ]

        media_geral = (sum(todas_respostas) / len(todas_respostas)) if todas_respostas else None
        classificacao_geral, cor_geral = classificar_risco(media_geral)
        data_hora_proc = agora_str("%d/%m/%Y %H:%M")

        doc = BaseDocTemplate(
            str(caminho_pdf),
            pagesize=A4,
            rightMargin=PDF_MARGIN_RIGHT,
            leftMargin=PDF_MARGIN_LEFT,
            topMargin=PDF_MARGIN_TOP,
            bottomMargin=PDF_MARGIN_BOTTOM,
            title="Relatório de Avaliação de Fatores Psicossociais — NR-1",
            author=responsavel,
            subject=nome_empresa,
        )

        doc.data_hora_processamento = data_hora_proc
        doc.responsavel_relatorio = str(responsavel).strip()

        largura_frame = A4[0] - doc.leftMargin - doc.rightMargin
        altura_frame = A4[1] - doc.topMargin - doc.bottomMargin

        frame = Frame(doc.leftMargin, doc.bottomMargin, largura_frame, altura_frame, id="normal")
        template_capa = PageTemplate(id="Capa", frames=frame, onPage=desenhar_capa, autoNextPageTemplate="DemaisPaginas")
        template_demais = PageTemplate(id="DemaisPaginas", frames=frame, onPage=desenhar_cabecalho_e_rodape)
        doc.addPageTemplates([template_capa, template_demais])

        story = []

        # ----------------------------------------------------
        # CAPA (PÁGINA 1)
        # ----------------------------------------------------
        story.append(Spacer(1, 0.25 * cm))

        if LOGO_PATH.exists():
            logo = Image(
                str(LOGO_PATH),
                width=COVER_LOGO_WIDTH,
                height=COVER_LOGO_HEIGHT,
                kind="proportional",
                hAlign="CENTER",
            )
            story.append(_tabela_imagem_centralizada(logo, 17 * cm))

        story.append(Spacer(1, 0.65 * cm))
        story.append(Paragraph("RELATÓRIO DE AVALIAÇÃO DE FATORES PSICOSSOCIAIS — NR-1", estilos["capa_titulo"]))
        story.append(Paragraph(html.escape(nome_empresa.replace("_", " ")), estilos["capa_empresa"]))
        story.append(Paragraph("RISCO PSICOSSOCIAL", estilos["capa_risco"]))
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph("Avaliação baseada nas respostas coletadas no questionário de percepção dos fatores psicossociais.", estilos["capa_info"]))

        story.append(PageBreak())

        # ----------------------------------------------------
        # RESUMO EXECUTIVO (PÁGINA 2)
        # ----------------------------------------------------
        story.append(Paragraph("RESUMO EXECUTIVO", estilos["h1"]))

        media_texto = f"{media_geral:.2f}" if media_geral is not None else "Sem dados"
        resumo_dados = [
            [Paragraph("INDICADOR", estilos["table_header"]), Paragraph("RESULTADO", estilos["table_header"])],
            [Paragraph("Média geral dos indicadores", estilos["table_cell"]), Paragraph(media_texto, estilos["table_cell_center"])],
            [Paragraph("Classificação", estilos["table_cell"]), Paragraph(html.escape(classificacao_geral), estilos["table_cell_center"])],
            [Paragraph("Perguntas processadas", estilos["table_cell"]), Paragraph("15", estilos["table_cell_center"])],
        ]

        resumo_tabela = Table(resumo_dados, colWidths=[9.5 * cm, 7 * cm])
        estilo_resumo = _estilo_tabela_base(padding_v=7)
        estilo_resumo.add("BACKGROUND", (1, 2), (1, 2), colors.HexColor(cor_geral))
        resumo_tabela.setStyle(estilo_resumo)

        story.append(resumo_tabela)
        story.append(Spacer(1, 0.55 * cm))

        story.append(Paragraph("Objetivo", estilos["h2"]))
        story.append(Paragraph(
            "Apresentar a consolidação e a análise estatística dos resultados obtidos por meio do instrumento de "
            "percepção coletiva relacionado aos fatores psicossociais e organizacionais no contexto de trabalho. Este "
            "documento constitui parte integrante e obrigatória do processo de identificação de perigos e avaliação "
            "de riscos do Gerenciamento de Riscos Ocupacionais (GRO) da organização, servindo como subsídio técnico "
            "fundamental para a composição e atualização do Programa de Gerenciamento de Riscos (PGR) da empresa, em "
            "estrita conformidade com as diretrizes e exigências estabelecidas pela Norma Regulamentadora nº 1 (NR-1) "
            "do Ministério do Trabalho e Emprego.",
            estilos["normal"],
        ))

        story.append(Paragraph("CRITÉRIO DE INTERPRETAÇÃO", estilos["h2"]))
        story.append(Paragraph(
            "Para as respostas categóricas, foi utilizada a correspondência Discordo = 1, Concordo em parte = 3 "
            "e Concordo totalmente = 5. A Questão 15, quando apresentada numericamente de 1 a 5, é calculada "
            "diretamente nessa escala.",
            estilos["normal"],
        ))

        story.append(tabela_criterio_interpretacao(estilos))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "As classificações são aplicadas considerando a média obtida em cada indicador, com arredondamento "
            "para uma casa decimal para fins de enquadramento.",
            estilos["normal"],
        ))

        # ----------------------------------------------------
        # PÁGINAS DAS 15 QUESTÕES
        # ----------------------------------------------------
        for item in estatisticas_questoes:
            num = item["numero"]
            coluna = item["coluna"]
            estatisticas = item["estatisticas"]
            media = estatisticas["media"]
            classificacao, cor_classificacao = classificar_risco(media)
            analise = analise_tecnica(media)

            caminho_grafico = pasta_graficos / f"questao_{num}.png"
            if num == 15:
                criar_grafico_estrelas_q15(media, str(caminho_grafico))
                w_graf, h_graf = CHART_STAR_WIDTH, CHART_STAR_HEIGHT
            else:
                criar_grafico_donut(estatisticas["distribuicao"], media, num, str(caminho_grafico))
                w_graf, h_graf = CHART_DONUT_WIDTH, CHART_DONUT_HEIGHT

            story.append(PageBreak())

            if num == 15:
                story.append(Paragraph("QUESTÃO 15", estilos["h1"]))
                story.append(Paragraph("15- Qual nível de satisfação com a sua empresa atualmente?", estilos["questao"]))
            else:
                story.append(Paragraph(f"QUESTÃO {num}", estilos["h1"]))
                story.append(Paragraph(html.escape(str(coluna)), estilos["questao"]))

            story.append(Spacer(1, 0.1 * cm))
            img_grafico = Image(str(caminho_grafico), width=w_graf, height=h_graf, kind="proportional")
            story.append(_tabela_imagem_centralizada(img_grafico, 16.5 * cm))
            story.append(Spacer(1, 0.1 * cm))

            if num != 15:
                story.append(tabela_respostas(estatisticas, estilos))
                story.append(Spacer(1, 0.9 * cm))
            else:
                story.append(Spacer(1, 0.22 * cm))
                story.append(Paragraph("DISTRIBUIÇÃO NUMÉRICA", estilos["h2"]))
                story.append(tabela_numerica_q15(estatisticas, estilos))

            story.append(Spacer(1, 0.25 * cm))

            # Tabela de resultado da questão
            res_media_txt = f"{media:.2f}" if media is not None else "Sem dados"
            resultado_data = [
                [
                    Paragraph("MÉDIA DA QUESTÃO", estilos["table_header"]),
                    Paragraph("CLASSIFICAÇÃO", estilos["table_header"]),
                    Paragraph("Nº DE RESPOSTAS", estilos["table_header"]),
                ],
                [
                    Paragraph(res_media_txt, estilos["table_cell_center"]),
                    Paragraph(html.escape(classificacao), estilos["table_cell_center"]),
                    Paragraph(str(estatisticas["n"]), estilos["table_cell_center"]),
                ],
            ]
            resultado_tabela = Table(resultado_data, colWidths=[5.5 * cm, 7 * cm, 4 * cm])
            estilo_res = _estilo_tabela_base(padding_v=5)
            estilo_res.add("BACKGROUND", (1, 1), (1, 1), colors.HexColor(cor_classificacao))
            resultado_tabela.setStyle(estilo_res)

            story.append(resultado_tabela)
            story.append(Spacer(1, 0.9 * cm if num != 15 else 0.22 * cm))

            story.append(KeepTogether([
                Paragraph(html.escape(analise["titulo"]), estilos["h2"]),
                Paragraph(html.escape(analise["texto"]), estilos["analise"]),
            ]))

            if analise["recomendacoes"]:
                rec_flows = [Paragraph("RECOMENDAÇÕES PRÁTICAS", estilos["h2"])]
                for idx_rec, rec in enumerate(analise["recomendacoes"], start=1):
                    rec_flows.append(Paragraph(f"<b>{idx_rec}.</b> {html.escape(rec)}", estilos["recomendacao"]))
                story.append(KeepTogether(rec_flows))

        # ----------------------------------------------------
        # CONCLUSÃO (PÁGINA FINAL)
        # ----------------------------------------------------
        story.append(PageBreak())
        story.append(Paragraph("CONCLUSÃO", estilos["h1"]))

        media_txt_conc = f"{media_geral:.2f}" if media_geral is not None else "Sem dados"
        class_txt_conc = classificacao_geral if classificacao_geral else "SEM DADOS"

        story.append(Paragraph(
            f"A avaliação das 15 questões resultou em média geral de "
            f"<b>{html.escape(media_txt_conc)}</b>, classificada como "
            f"<b>{html.escape(class_txt_conc)}</b> segundo os critérios definidos neste relatório.",
            estilos["normal"],
        ))

        story.append(Paragraph(
            "A interpretação dos resultados deve integrar o processo de Gerenciamento de Riscos Ocupacionais (GRO) "
            "previsto na NR-1, considerando, de forma conjunta, os fatores de risco psicossocial relacionados ao trabalho, "
            "as condições e a organização do trabalho, as informações obtidas por outros instrumentos e as medidas de "
            "prevenção e controle adotadas pela organização. Este levantamento deve ser utilizado como uma fonte de "
            "evidências para apoiar decisões preventivas proporcionais ao contexto identificado, orientando a liderança na "
            "definição de prioridades, no acompanhamento das ações e na verificação de sua efetividade ao longo do tempo. "
            "Em consonância com as boas práticas de Saúde e Segurança do Trabalho e com os princípios de Higiene Ocupacional, "
            "especialmente o reconhecimento, a avaliação e o controle sistemático dos riscos ocupacionais quando aplicáveis, "
            "recomenda-se que os resultados sejam analisados em conjunto com a realidade observada nos ambientes e processos "
            "de trabalho, com a participação dos trabalhadores e com os demais registros e avaliações pertinentes. Dessa "
            "forma, o relatório funciona como ferramenta de apoio à melhoria contínua, contribuindo para o aperfeiçoamento "
            "das condições de trabalho e para o desenvolvimento de medidas de prevenção de maneira planejada, acompanhada "
            "e revisável, sem substituir a análise técnica integrada exigida pelos processos de gestão de riscos da organização.",
            estilos["normal"],
        ))

        # Fechamento Condicional por Classificação Geral
        if classificacao_geral in {"BAIXO RISCO / FATOR PROTETOR", "BAIXO RISCO / FATOR PROTETOR ATIVO"}:
            story.append(Paragraph(
                "Diante do enquadramento na categoria de Baixo Risco / Fator Protetor, constata-se que o ambiente "
                "organizacional avaliado apresenta um clima predominantemente favorável e equilibrado, demonstrando a "
                "presença de elementos estruturais e relacionais que atuam de forma positiva na preservação do "
                "bem-estar e da saúde dos trabalhadores. Sob a ótica da NR-1 e das diretrizes gerais de segurança e "
                "saúde no trabalho, tais resultados refletem o bom funcionamento dos fluxos de comunicação, do suporte das "
                "lideranças e da organização das tarefas diárias. No entanto, o gerenciamento de riscos prevê que o "
                "estado de baixo risco não deve ser encarado como um fator estático, mas sim como uma condição a ser "
                "mantida e aperfeiçoada ativamente.",
                estilos["normal"],
            ))
            story.append(Paragraph(
                "A consolidação deste patamar protetivo fortalece a imagem da organização como um ambiente seguro e "
                "sustentável, mitigando proativamente fatores causadores de desgaste interpessoal e operacional. Para "
                "assegurar a perenidade destes índices, recomenda-se a incorporação contínua do acompanhamento destes "
                "indicadores ao Programa de Gerenciamento de Riscos (PGR), priorizando medidas de manutenção preventiva, "
                "como a preservação de canais abertos de diálogo, o fortalecimento de práticas participativas previstas "
                "nas diretrizes de SST e o incentivo constante ao aperfeiçoamento dos processos produtivos. Desta forma, "
                "a organização cumpre não apenas os preceitos regulamentares com excelência, mas também consolida uma "
                "cultura organizacional sólida, eficiente e orientada à valorização humana e à produtividade consciente.",
                estilos["normal"],
            ))
        elif classificacao_geral in {"RISCO MODERADO", "RISCO PSICOSSOCIAL MODERADO"}:
            story.append(Paragraph(
                "A indicação do nível de Risco Moderado sinaliza uma oportunidade valiosa de atuação preventiva e "
                "alinhamento de processos antes do surgimento de impactos significativos na rotina operacional. De "
                "acordo com os preceitos do Gerenciamento de Riscos Ocupacionais (GRO) da NR-1, o nível moderado aponta "
                "para a existência de pontos de atenção pontuais na organização do trabalho, no ritmo das atividades ou "
                "nos fluxos interativos que, embora controlados no momento, beneficiam-se amplamente de ajustes finos "
                "e ações de otimização. Esse diagnóstico oferece à gestão uma radiografia clara e objetiva para direcionar "
                "investimentos preventivos com precisão, evitando desperdício de recursos e maximizando o bem-estar do "
                "ecossistema corporativo.",
                estilos["normal"],
            ))
            story.append(Paragraph(
                "Em conformidade com a lógica de melhoria contínua inerente aos sistemas de gestão de SST, o "
                "enquadramento neste patamar orienta a elaboração de um plano de ação simples, gradual e focado em causas "
                "prioritárias no âmbito do PGR. Adoções pontuais de melhorias ergonomicamente alinhadas às diretrizes "
                "da NR-17 — tais como o alinhamento de expectativas de desempenho, a revisão pontual da distribuição "
                "de demandas e o aprimoramento do suporte interdepartamental — tendem a reverter rapidamente os fatores "
                "de tensão detectados. Recomenda-se que a empresa incorpore esses pontos de atenção às rotinas normais "
                "de acompanhamento e diálogo com as equipes, promovendo um ambiente de trabalho cada vez mais harmonioso, "
                "previsível e produtivo, fortalecendo a governança e a segurança jurídica da organização.",
                estilos["normal"],
            ))
        elif classificacao_geral in {"ALTO RISCO", "RISCO PSICOSSOCIAL ALTO"}:
            story.append(Paragraph(
                "O resultado correspondente à classificação de Alto Risco representa um diagnóstico estratégico "
                "fundamental para orientar a tomada de decisões da alta direção de maneira assertiva, proativa e "
                "estruturada. Sob o prisma da NR-1 e das modernas práticas de Higiene Ocupacional, a identificação "
                "de um patamar elevado indica a necessidade de priorização no cronograma de ações do Gerenciamento "
                "de Riscos Ocupacionais (GRO), visando mitigar oscilações operacionais e reestabelecer o equilíbrio "
                "funcional do ambiente de trabalho. Este diagnóstico não deve ser encarado sob uma perspectiva "
                "punitiva ou alarmista, mas sim como um vetor de inteligência corporativa que antecipa gargalos na "
                "organização das tarefas, nos fluxos comunicacionais e nas dinâmicas de liderança.",
                estilos["normal"],
            ))
            story.append(Paragraph(
                "Para responder com eficácia a este cenário, o arcabouço normativo orienta a estruturação de um plano "
                "de ação preventivo proporcional, integrando intervenções técnicas, organizacionais e administrativas "
                "de forma cronológica e revisável. A implementação de ações direcionadas — como a capacitação de gestores, "
                "a readequação de processos operacionais com apoio nos conceitos da NR-17, e o fortalecimento de canais "
                "de escuta ativa e participação coletiva — permitirá atuar diretamente na raiz dos fatores identificados. "
                "A abordagem sistemática e acompanhada destas medidas assegura a evolução gradual dos indicadores, "
                "promovendo a sustentabilidade do negócio, a redução de custos invisíveis ligados à rotatividade ou ao "
                "desgaste da equipe, e a plena convergência com as exigências legais e normativas de Saúde e Segurança "
                "do Trabalho.",
                estilos["normal"],
            ))
        else:
            story.append(Paragraph(
                "Quando os dados não permitem um enquadramento conclusivo, recomenda-se que a organização considere "
                "este resultado como informação complementar ao processo de gerenciamento de riscos, promovendo a "
                "continuidade da coleta de evidências, a análise integrada das condições de trabalho e o acompanhamento "
                "das medidas preventivas pertinentes.",
                estilos["normal"],
            ))

        story.append(Spacer(1, 0.5 * cm))

        doc.build(story)

        if not caminho_pdf.exists():
            raise FileNotFoundError("O PDF não foi criado.")

        return caminho_pdf

    finally:
        # Remoção segura dos arquivos temporários de imagens dos gráficos
        try:
            if pasta_graficos.exists():
                for arq in pasta_graficos.iterdir():
                    try:
                        arq.unlink()
                    except Exception:
                        pass
                pasta_graficos.rmdir()
        except Exception:
            pass


# ============================================================
# INTERFACES STREAMLIT (TELAS)
# ============================================================

def tela_login():
    st.markdown(
        f"""
        <div class="caixa-marca">
            <div class="titulo-principal">{NOME_EMPRESA}</div>
            <div class="subtitulo-principal">{SUBTITULO}</div>
            <b>Sistema de Avaliação de Fatores Psicossociais — NR-1</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_esq, col_centro, col_dir = st.columns([1, 1.1, 1])

    with col_centro:
        st.subheader("🔐 Acesso ao sistema")
        usuario = st.text_input("Usuário", key="login_usuario")
        senha = st.text_input("Senha", type="password", key="login_senha")

        if st.button("ENTRAR", use_container_width=True, type="primary"):
            usuario_db = autenticar(usuario, senha)

            if usuario_db is None:
                encontrado = buscar_usuario(usuario)
                if encontrado is not None:
                    if encontrado["status"] == "PENDENTE":
                        st.warning("Seu cadastro está pendente de liberação pelo administrador.")
                    elif encontrado["status"] == "BLOQUEADO":
                        st.error("Seu acesso está bloqueado.")
                    else:
                        st.error("Usuário ou senha inválidos.")
                else:
                    st.error("Usuário ou senha inválidos.")
            else:
                st.session_state["logado"] = True
                st.session_state["logged_in"] = True
                st.session_state["usuario_id"] = usuario_db["id"]
                st.session_state["user_id"] = usuario_db["id"]
                st.session_state["usuario"] = usuario_db["usuario"]
                st.session_state["nome_usuario"] = usuario_db["nome"]
                st.session_state["perfil"] = usuario_db["perfil"]
                st.session_state["user_role"] = usuario_db["perfil"]
                st.session_state["current_page"] = "📊 Processamento"
                st.session_state["menu_navegacao"] = "📊 Processamento"

                registrar_auditoria(usuario_db["usuario"], "LOGIN REALIZADO")
                st.rerun()

        st.divider()
        st.markdown("**Ainda não possui acesso?**")

        if st.button("CRIAR CADASTRO DE COLABORADOR", use_container_width=True):
            st.session_state["tela_cadastro"] = True
            st.rerun()



def tela_cadastro():
    st.markdown(
        f"""
        <div class="caixa-marca">
            <div class="titulo-principal">Cadastro de colaborador</div>
            <div class="subtitulo-principal">{NOME_EMPRESA} — {SUBTITULO}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        nome = st.text_input("Nome completo", key="cad_nome")
        usuario = st.text_input("Usuário desejado", key="cad_usuario")
        senha = st.text_input("Senha", type="password", key="cad_senha")
        confirmar = st.text_input("Confirmar senha", type="password", key="cad_confirmar")

        if st.button("SOLICITAR CADASTRO", use_container_width=True, type="primary"):
            if senha != confirmar:
                st.error("As senhas não conferem.")
            else:
                sucesso, mensagem = cadastrar_colaborador(nome, usuario, senha)
                if sucesso:
                    st.success(mensagem)
                    st.session_state["tela_cadastro"] = False
                    st.rerun()
                else:
                    st.error(mensagem)

        if st.button("VOLTAR AO LOGIN", use_container_width=True):
            st.session_state["tela_cadastro"] = False
            st.rerun()


def tela_administracao():
    st.subheader("👥 Administração de acessos")
    usuarios = listar_usuarios()

    if not usuarios:
        st.info("Nenhum usuário cadastrado.")
        return

    for user in usuarios:
        if user["usuario"] == ADMIN_USUARIO:
            continue

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2.3, 1.4, 1.2, 2])

            with col1:
                st.write(f"**{user['nome']}**")
                st.caption(f"Usuário: {user['usuario']}")

            with col2:
                st.write(f"Perfil: **{user['perfil']}**")
                st.write(f"Status: **{user['status']}**")

            with col3:
                st.caption("Criado em:")
                st.caption(str(user["criado_em"]))

            with col4:
                btn_key_lib = f"liberar_{user['id']}"
                btn_key_bloq = f"bloquear_{user['id']}"

                if user["status"] in {"PENDENTE", "BLOQUEADO"}:
                    if st.button("LIBERAR", key=btn_key_lib, use_container_width=True):
                        alterar_status_usuario(user["id"], "LIBERADO", st.session_state.get("usuario", ""))
                        registrar_auditoria(st.session_state.get("usuario", ""), f"USUÁRIO LIBERADO: {user['usuario']}")
                        st.rerun()

                if user["status"] in {"PENDENTE", "LIBERADO"}:
                    if st.button("BLOQUEAR", key=btn_key_bloq, use_container_width=True):
                        alterar_status_usuario(user["id"], "BLOQUEADO", st.session_state.get("usuario", ""))
                        registrar_auditoria(st.session_state.get("usuario", ""), f"USUÁRIO BLOQUEADO: {user['usuario']}")
                        st.rerun()


def tela_auditoria():
    st.subheader("📋 Auditoria do sistema")

    with conectar_banco() as conn:
        registros = conn.execute(
            """
            SELECT usuario, acao, data_hora, arquivo
            FROM auditoria_nr1 ORDER BY id DESC
            """
        ).fetchall()

    if not registros:
        st.info("Nenhum registro de auditoria.")
        return

    dados = [
        {
            "Usuário": reg["usuario"] or "",
            "Ação": reg["acao"],
            "Data/Hora": reg["data_hora"],
            "Arquivo": reg["arquivo"] or "",
        }
        for reg in registros
    ]

    st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)


def limpar_processamento():
    for chave in ["arquivo_hash", "df", "nome_arquivo_original", "pdf_path"]:
        st.session_state.pop(chave, None)

    st.session_state["upload_version"] = st.session_state.get("upload_version", 0) + 1
    st.rerun()


def sair_do_sistema():
    usuario = st.session_state.get("usuario", "")
    if usuario:
        try:
            registrar_auditoria(usuario, "LOGOUT REALIZADO")
        except Exception:
            pass

    st.session_state.clear()
    st.session_state.update({
        "logado": False,
        "logged_in": False,
        "usuario_id": None,
        "user_id": None,
        "usuario": "",
        "nome_usuario": "",
        "perfil": "COLABORADOR",
        "user_role": "COLABORADOR",
        "tela_cadastro": False,
        "current_page": "login",
        "menu_navegacao": "📊 Processamento",
        "upload_version": 0,
        "arquivo_hash": None,
        "df": None,
        "dados_processados": None,
        "nome_arquivo_original": "",
        "pdf_path": None,
    })
    st.rerun()


def tela_processamento():
    st.markdown(
        f"""
        <div class="caixa-marca">
            <div class="titulo-principal">Avaliação de Fatores Psicossociais — NR-1</div>
            <div class="subtitulo-principal">{NOME_EMPRESA} — {SUBTITULO}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    upload_version = st.session_state.get("upload_version", 0)
    uploaded_file = st.file_uploader(
        "Selecione o arquivo exportado do Google Forms",
        type=["csv", "xlsx", "xls"],
        key=f"arquivo_questionario_{upload_version}",
    )

    # Toolbar de Ações
    st.markdown('<div class="toolbar">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1.4, 1.4, 1.4])

    with col1:
        gerar_clicado = st.button(
            "📄 GERAR RELATÓRIO PDF",
            use_container_width=True,
            type="primary",
            disabled=(uploaded_file is None),
        )

    caminho_pdf_atual = st.session_state.get("pdf_path")
    pdf_pronto = bool(caminho_pdf_atual) and Path(caminho_pdf_atual).exists()

    with col2:
        if pdf_pronto:
            caminho_pdf = Path(caminho_pdf_atual)
            with open(caminho_pdf, "rb") as arquivo_pdf:
                pdf_bytes = arquivo_pdf.read()

            st.download_button(
                "⬇️ BAIXAR PDF",
                data=pdf_bytes,
                file_name=caminho_pdf.name,
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.download_button(
                "⬇️ BAIXAR PDF",
                data=b"",
                file_name="relatorio.pdf",
                disabled=True,
                use_container_width=True,
            )

    with col3:
        if st.button("🧹 LIMPAR SESSÃO", use_container_width=True):
            limpar_processamento()

    st.markdown("</div>", unsafe_allow_html=True)

    # Execução da Geração do Relatório
    if gerar_clicado and uploaded_file is not None:
        try:
            with st.spinner("Processando dados e gerando relatório PDF..."):
                df = ler_arquivo(uploaded_file)
                responsavel = st.session_state.get("nome_usuario", "Usuário")
                caminho_pdf = gerar_pdf(df, uploaded_file.name, responsavel)

                st.session_state["pdf_path"] = str(caminho_pdf)
                st.session_state["nome_arquivo_original"] = uploaded_file.name

                registrar_auditoria(
                    st.session_state.get("usuario", ""),
                    "RELATÓRIO GERADO",
                    uploaded_file.name,
                )
                st.success("Relatório gerado com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():
    inicializar_banco()
    inicializar_session_state()

    if not st.session_state.get("logado", False):
        st.session_state["current_page"] = "login" if not st.session_state.get("tela_cadastro", False) else "cadastro"
        if st.session_state.get("tela_cadastro", False):
            tela_cadastro()
        else:
            tela_login()
        return

    # Sidebar com informações e navegação
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.get('nome_usuario') or 'Usuário'}")
        st.caption(f"Perfil: **{st.session_state.get('perfil') or 'COLABORADOR'}**")
        st.divider()

        opcoes = ["📊 Processamento"]
        if st.session_state.get("perfil", "COLABORADOR") == "ADMIN":
            opcoes.extend(["👥 Administração", "📋 Auditoria"])

        pagina_atual = st.session_state.get("current_page", "📊 Processamento")
        if pagina_atual not in opcoes:
            pagina_atual = "📊 Processamento"

        menu = st.radio(
            "Navegação",
            opcoes,
            index=opcoes.index(pagina_atual),
        )
        st.session_state["current_page"] = menu
        st.session_state["menu_navegacao"] = menu
        st.divider()

        if st.button("🚪 SAIR", use_container_width=True):
            sair_do_sistema()

    # Roteamento das telas
    if st.session_state.get("current_page") == "📊 Processamento":
        tela_processamento()
    elif st.session_state.get("current_page") == "👥 Administração":
        tela_administracao()
    elif st.session_state.get("current_page") == "📋 Auditoria":
        tela_auditoria()


if __name__ == "__main__":
    main()
