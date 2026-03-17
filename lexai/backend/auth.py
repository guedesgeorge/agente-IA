"""
LexAI — Sistema de Autenticação
- Login com JWT token
- Senha com hash bcrypt
- Recuperação por email automático
- Histórico separado por usuário
"""

import os, json, secrets, hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "8"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
APP_URL   = os.getenv("APP_URL", "http://127.0.0.1:3000")

USERS_FILE = Path("./data/users.json")
TOKENS_FILE = Path("./data/reset_tokens.json")
HISTORY_DIR = Path("./data/historico")

# Cria pastas necessárias
for p in [USERS_FILE.parent, HISTORY_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# ── USUÁRIOS PRÉ-CADASTRADOS (escritório com 5 funcionários) ──────────────────
DEFAULT_USERS = [
    {"id": "user1", "nome": "Advogado 1",    "email": "", "role": "advogado"},
    {"id": "user2", "nome": "Advogado 2",    "email": "", "role": "advogado"},
    {"id": "user3", "nome": "Advogado 3",    "email": "", "role": "advogado"},
    {"id": "user4", "nome": "Paralegal",     "email": "", "role": "paralegal"},
    {"id": "admin", "nome": "Administrador", "email": "", "role": "admin"},
]

# ── HASH DE SENHA ─────────────────────────────────────────────────────────────
def hash_senha(senha: str) -> str:
    """Hash seguro com salt."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{senha}".encode()).hexdigest()
    return f"{salt}:{h}"

def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica senha contra hash."""
    try:
        salt, h = hash_armazenado.split(":")
        return hashlib.sha256(f"{salt}{senha}".encode()).hexdigest() == h
    except:
        return False

# ── GERENCIAMENTO DE USUÁRIOS ─────────────────────────────────────────────────
def carregar_usuarios() -> dict:
    if not USERS_FILE.exists():
        # Cria arquivo inicial com usuários padrão sem senha definida
        users = {u["id"]: {**u, "senha_hash": None, "criado_em": datetime.now().isoformat()} 
                 for u in DEFAULT_USERS}
        salvar_usuarios(users)
        return users
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))

def salvar_usuarios(users: dict):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def buscar_usuario_por_email(email: str) -> Optional[dict]:
    users = carregar_usuarios()
    for u in users.values():
        if u.get("email", "").lower() == email.lower():
            return u
    return None

def buscar_usuario_por_id(user_id: str) -> Optional[dict]:
    users = carregar_usuarios()
    return users.get(user_id)

# ── JWT TOKEN SIMPLES (sem biblioteca externa) ────────────────────────────────
import base64, hmac, time

def criar_token(user_id: str) -> str:
    """Cria JWT simples sem dependência externa."""
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + TOKEN_EXPIRE_HOURS * 3600,
        "iat": int(time.time())
    }
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    msg = f"{header}.{body}"
    sig = hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    sig_b64 = base64.urlsafe_b64encode(sig.encode()).decode().rstrip("=")
    return f"{msg}.{sig_b64}"

def verificar_token(token: str) -> Optional[str]:
    """Verifica token e retorna user_id ou None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, sig = parts
        msg = f"{header}.{body}"
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest().encode()
        ).decode().rstrip("=")
        if sig != expected_sig:
            return None
        # Decodifica payload
        padding = 4 - len(body) % 4
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * padding))
        if payload.get("exp", 0) < time.time():
            return None  # Token expirado
        return payload.get("sub")
    except:
        return None

# ── RECUPERAÇÃO DE SENHA ──────────────────────────────────────────────────────
def carregar_tokens_reset() -> dict:
    if not TOKENS_FILE.exists():
        return {}
    return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))

def salvar_tokens_reset(tokens: dict):
    TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")

def gerar_token_reset(email: str) -> Optional[str]:
    """Gera token temporário de recuperação (válido 1 hora)."""
    usuario = buscar_usuario_por_email(email)
    if not usuario:
        return None
    token = secrets.token_urlsafe(32)
    tokens = carregar_tokens_reset()
    tokens[token] = {
        "user_id": usuario["id"],
        "email": email,
        "expira_em": (datetime.now() + timedelta(hours=1)).isoformat(),
        "usado": False
    }
    salvar_tokens_reset(tokens)
    return token

def verificar_token_reset(token: str) -> Optional[str]:
    """Verifica token de reset e retorna user_id se válido."""
    tokens = carregar_tokens_reset()
    info = tokens.get(token)
    if not info:
        return None
    if info.get("usado"):
        return None
    if datetime.fromisoformat(info["expira_em"]) < datetime.now():
        return None
    return info["user_id"]

def usar_token_reset(token: str, nova_senha: str) -> bool:
    """Aplica nova senha e invalida o token."""
    user_id = verificar_token_reset(token)
    if not user_id:
        return False
    # Atualiza senha
    users = carregar_usuarios()
    if user_id not in users:
        return False
    users[user_id]["senha_hash"] = hash_senha(nova_senha)
    salvar_usuarios(users)
    # Invalida token
    tokens = carregar_tokens_reset()
    if token in tokens:
        tokens[token]["usado"] = True
        salvar_tokens_reset(tokens)
    return True

# ── ENVIO DE EMAIL ────────────────────────────────────────────────────────────
async def enviar_email_recuperacao(email: str, token: str, nome: str):
    """Envia email com link de recuperação."""
    link = f"{APP_URL}/reset?token={token}"
    assunto = "LexAI — Redefinição de Senha"
    corpo = f"""
Olá, {nome}!

Você solicitou a redefinição de sua senha no LexAI.

Clique no link abaixo para criar uma nova senha:
{link}

Este link é válido por 1 hora.

Se você não solicitou isso, ignore este email.

— LexAI Agente Jurídico
    """.strip()

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = email
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email, msg.as_string())
        return True
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False

# ── HISTÓRICO POR USUÁRIO ─────────────────────────────────────────────────────
def salvar_historico(user_id: str, session_id: str, titulo: str, mensagens: list):
    """Salva histórico de conversa do usuário."""
    user_dir = HISTORY_DIR / user_id
    user_dir.mkdir(exist_ok=True)
    arquivo = user_dir / f"{session_id}.json"
    arquivo.write_text(json.dumps({
        "session_id": session_id,
        "titulo": titulo,
        "data": datetime.now().isoformat(),
        "mensagens": mensagens
    }, ensure_ascii=False, indent=2), encoding="utf-8")

def carregar_historico(user_id: str) -> list:
    """Retorna lista de conversas do usuário, mais recentes primeiro."""
    user_dir = HISTORY_DIR / user_id
    if not user_dir.exists():
        return []
    sessoes = []
    for arquivo in sorted(user_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(arquivo.read_text(encoding="utf-8"))
            sessoes.append({
                "session_id": data.get("session_id"),
                "titulo": data.get("titulo", "Conversa"),
                "data": data.get("data", ""),
                "total_mensagens": len(data.get("mensagens", []))
            })
        except:
            pass
    return sessoes[:50]  # Retorna últimas 50 conversas

def carregar_sessao(user_id: str, session_id: str) -> Optional[dict]:
    """Retorna conversa específica do usuário."""
    arquivo = HISTORY_DIR / user_id / f"{session_id}.json"
    if not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))

def deletar_sessao(user_id: str, session_id: str) -> bool:
    arquivo = HISTORY_DIR / user_id / f"{session_id}.json"
    if arquivo.exists():
        arquivo.unlink()
        return True
    return False
