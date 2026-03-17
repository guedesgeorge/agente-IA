"""
LexAI — Gerenciador de Usuários (Terminal)
Execute: python gerenciar_usuarios.py
"""

import json, secrets, hashlib, os
from pathlib import Path
from datetime import datetime

USERS_FILE = Path("./data/users.json")
USERS_FILE.parent.mkdir(parents=True, exist_ok=True)

ROLES = {"1": "admin", "2": "advogado", "3": "paralegal"}
ROLE_LABEL = {"admin": "Administrador", "advogado": "Advogado", "paralegal": "Paralegal"}

# ── CORES ─────────────────────────────────────────────────────────────────────
def cor(texto, c):
    cores = {"gold":"\033[93m","green":"\033[92m","red":"\033[91m",
             "blue":"\033[94m","gray":"\033[90m","bold":"\033[1m","reset":"\033[0m"}
    return f"{cores.get(c,'')}{texto}{cores['reset']}"

def titulo(texto):
    print(f"\n{cor('═'*50,'gold')}")
    print(f"  {cor('⚖️  LexAI','gold')} {cor('— ' + texto,'bold')}")
    print(f"{cor('═'*50,'gold')}\n")

def ok(msg):   print(f"\n  {cor('✅ ' + msg, 'green')}\n")
def erro(msg): print(f"\n  {cor('⚠️  ' + msg, 'red')}\n")
def info(msg): print(f"  {cor(msg, 'gray')}")

# ── HASH ──────────────────────────────────────────────────────────────────────
def hash_senha(senha):
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{senha}".encode()).hexdigest()
    return f"{salt}:{h}"

def verificar_senha(senha, hash_armazenado):
    try:
        salt, h = hash_armazenado.split(":")
        return hashlib.sha256(f"{salt}{senha}".encode()).hexdigest() == h
    except:
        return False

# ── USUÁRIOS ──────────────────────────────────────────────────────────────────
def carregar():
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))

def salvar(users):
    USERS_FILE.write_text(
        json.dumps(users, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def proximo_id(users):
    nums = [int(k.replace("user","")) for k in users if k.startswith("user") and k[4:].isdigit()]
    return f"user{max(nums)+1}" if nums else "user1"

# ── LISTAR ────────────────────────────────────────────────────────────────────
def listar_usuarios():
    titulo("Usuários Cadastrados")
    users = carregar()
    if not users:
        info("Nenhum usuário cadastrado ainda.")
        return

    print(f"  {'ID':<10} {'Nome':<22} {'Email':<30} {'Perfil':<14} {'Status'}")
    print(f"  {'-'*9} {'-'*21} {'-'*29} {'-'*13} {'-'*10}")
    for u in users.values():
        tem_senha = bool(u.get("senha_hash"))
        status = cor("● Ativo", "green") if tem_senha else cor("○ Pendente", "gray")
        role   = cor(ROLE_LABEL.get(u.get("role","advogado"), "?"), "gold") if u.get("role") == "admin" else ROLE_LABEL.get(u.get("role","advogado"), "?")
        email  = u.get("email","") or cor("(sem email)", "gray")
        print(f"  {u['id']:<10} {u['nome']:<22} {email:<30} {role:<14} {status}")
    print()

# ── CRIAR ─────────────────────────────────────────────────────────────────────
def criar_usuario():
    titulo("Criar Novo Usuário")
    users = carregar()

    nome = input("  Nome completo: ").strip()
    if not nome:
        erro("Nome obrigatório."); return

    email = input("  Email: ").strip().lower()
    if not email:
        erro("Email obrigatório."); return
    for u in users.values():
        if u.get("email","").lower() == email:
            erro("Email já cadastrado."); return

    print("\n  Perfil de acesso:")
    print("    1 - Administrador")
    print("    2 - Advogado")
    print("    3 - Paralegal")
    role_op = input("  Escolha (1-3) [padrão: 2]: ").strip() or "2"
    role = ROLES.get(role_op, "advogado")

    senha = input("  Senha inicial (mín. 6 caracteres): ").strip()
    if len(senha) < 6:
        erro("Senha muito curta."); return
    confirmar = input("  Confirmar senha: ").strip()
    if senha != confirmar:
        erro("Senhas não conferem."); return

    user_id = proximo_id(users)
    users[user_id] = {
        "id": user_id,
        "nome": nome,
        "email": email,
        "role": role,
        "senha_hash": hash_senha(senha),
        "criado_em": datetime.now().isoformat()
    }
    salvar(users)
    ok(f"Usuário '{nome}' criado com ID {user_id}!")
    info(f"Ele pode fazer login com: {email}")

# ── EDITAR ────────────────────────────────────────────────────────────────────
def editar_usuario():
    titulo("Editar Usuário")
    users = carregar()
    listar_usuarios()

    uid = input("  ID do usuário para editar: ").strip()
    if uid not in users:
        erro("Usuário não encontrado."); return

    u = users[uid]
    print(f"\n  Editando: {cor(u['nome'], 'bold')} — deixe em branco para manter o valor atual\n")

    novo_nome = input(f"  Nome [{u['nome']}]: ").strip()
    novo_email = input(f"  Email [{u.get('email','')}]: ").strip().lower()
    print("  Perfil: 1-Admin  2-Advogado  3-Paralegal")
    nova_role_op = input(f"  Perfil [{ROLE_LABEL.get(u.get('role','advogado'))}]: ").strip()

    if novo_nome:  users[uid]["nome"] = novo_nome
    if novo_email:
        for k, v in users.items():
            if k != uid and v.get("email","").lower() == novo_email:
                erro("Email já usado por outro usuário."); return
        users[uid]["email"] = novo_email
    if nova_role_op in ROLES:
        users[uid]["role"] = ROLES[nova_role_op]

    salvar(users)
    ok(f"Usuário '{users[uid]['nome']}' atualizado!")

# ── REDEFINIR SENHA ───────────────────────────────────────────────────────────
def redefinir_senha():
    titulo("Redefinir Senha")
    users = carregar()
    listar_usuarios()

    uid = input("  ID do usuário: ").strip()
    if uid not in users:
        erro("Usuário não encontrado."); return

    u = users[uid]
    print(f"\n  Redefinindo senha de: {cor(u['nome'], 'bold')}\n")

    nova = input("  Nova senha (mín. 6 caracteres): ").strip()
    if len(nova) < 6:
        erro("Senha muito curta."); return
    confirmar = input("  Confirmar senha: ").strip()
    if nova != confirmar:
        erro("Senhas não conferem."); return

    users[uid]["senha_hash"] = hash_senha(nova)
    salvar(users)
    ok(f"Senha de '{u['nome']}' redefinida com sucesso!")

# ── REMOVER ───────────────────────────────────────────────────────────────────
def remover_usuario():
    titulo("Remover Usuário")
    users = carregar()
    listar_usuarios()

    uid = input("  ID do usuário para remover: ").strip()
    if uid not in users:
        erro("Usuário não encontrado."); return
    if uid == "admin":
        erro("Não é possível remover o administrador principal."); return

    u = users[uid]
    confirmar = input(f"\n  Tem certeza que deseja remover '{cor(u['nome'],'bold')}'? (s/N): ").strip().lower()
    if confirmar != "s":
        info("Operação cancelada."); return

    del users[uid]
    salvar(users)
    ok(f"Usuário '{u['nome']}' removido.")

# ── CRIAR ADMIN INICIAL ───────────────────────────────────────────────────────
def setup_inicial():
    users = carregar()
    if "admin" in users and users["admin"].get("senha_hash"):
        return  # Admin já configurado

    titulo("Configuração Inicial — Criar Administrador")
    print("  Nenhum administrador encontrado. Vamos criar o primeiro acesso.\n")

    email = input("  Email do administrador: ").strip().lower()
    if not email:
        erro("Email obrigatório."); return

    senha = input("  Senha (mín. 6 caracteres): ").strip()
    if len(senha) < 6:
        erro("Senha muito curta."); return

    users["admin"] = {
        "id": "admin",
        "nome": "Administrador",
        "email": email,
        "role": "admin",
        "senha_hash": hash_senha(senha),
        "criado_em": datetime.now().isoformat()
    }
    salvar(users)
    ok("Administrador criado! Agora você pode fazer login no sistema.")

# ── MENU PRINCIPAL ────────────────────────────────────────────────────────────
def menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    titulo("Gerenciador de Usuários")

    # Setup automático se não tiver admin
    users = carregar()
    if not users or ("admin" not in users) or not users.get("admin", {}).get("senha_hash"):
        setup_inicial()

    while True:
        print(f"  {cor('1','gold')} — Listar usuários")
        print(f"  {cor('2','gold')} — Criar usuário")
        print(f"  {cor('3','gold')} — Editar usuário")
        print(f"  {cor('4','gold')} — Redefinir senha")
        print(f"  {cor('5','gold')} — Remover usuário")
        print(f"  {cor('0','gray')} — Sair\n")

        op = input("  Escolha: ").strip()
        os.system('cls' if os.name == 'nt' else 'clear')

        if op == "1": listar_usuarios()
        elif op == "2": criar_usuario()
        elif op == "3": editar_usuario()
        elif op == "4": redefinir_senha()
        elif op == "5": remover_usuario()
        elif op == "0":
            print(f"\n  {cor('Até logo!', 'gold')}\n"); break
        else:
            erro("Opção inválida.")

        input(f"\n  {cor('Pressione Enter para continuar...', 'gray')}")
        os.system('cls' if os.name == 'nt' else 'clear')
        titulo("Gerenciador de Usuários")

if __name__ == "__main__":
    menu()
