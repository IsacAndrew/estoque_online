# 📦 Sistema de Estoque — Web

Sistema de controle de estoque 100% web, pronto para deploy na internet via **Render**.

## Arquivos do projeto

```
app.py            ← Toda a aplicação (Flask + lógica + HTML)
requirements.txt  ← Dependências Python
render.yaml       ← Configuração automática do Render
.gitignore        ← Arquivos ignorados pelo Git
```

---

## 🚀 Passo a passo: Subir no GitHub e Render

### PARTE 1 — GitHub

**1. Crie uma conta no GitHub** (se ainda não tiver)
→ https://github.com

**2. Crie um repositório novo**
- Clique em **"New repository"**
- Nome sugerido: `sistema-estoque`
- Deixe **público** (necessário para o plano gratuito do Render)
- NÃO marque "Add a README" (já temos um)
- Clique em **"Create repository"**

**3. Suba os arquivos**

Você pode fazer isso de duas formas:

**Forma simples (pelo site do GitHub):**
- Na página do repositório vazio, clique em **"uploading an existing file"**
- Arraste os 4 arquivos: `app.py`, `requirements.txt`, `render.yaml`, `.gitignore`
- Clique em **"Commit changes"**

**Forma pelo terminal (se tiver Git instalado):**
```bash
git init
git add .
git commit -m "primeiro commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/sistema-estoque.git
git push -u origin main
```

---

### PARTE 2 — Render

**4. Crie uma conta no Render**
→ https://render.com (pode entrar com a conta do GitHub)

**5. Conecte seu GitHub**
- No Render, vá em **"New +"** → **"Blueprint"**
- Clique em **"Connect GitHub"** e autorize o acesso
- Selecione o repositório `sistema-estoque`

**6. Deploy automático**
- O Render vai ler o `render.yaml` automaticamente
- Ele vai criar:
  - Um **banco PostgreSQL gratuito** (`estoque-db`)
  - Um **serviço web** (`sistema-estoque`)
- Clique em **"Apply"** e aguarde ~3 minutos

**7. Acesse o sistema**
- Após o deploy, o Render te dará uma URL como:
  `https://sistema-estoque.onrender.com`
- Acesse essa URL de qualquer lugar do mundo! 🌍

---

## 🔑 Login padrão

| Campo  | Valor         |
|--------|---------------|
| Usuário | `isac`       |
| Senha   | `102030`     |
| Tipo    | Administrador |

> ⚠️ **Recomendado:** troque a senha após o primeiro acesso.

---

## ⚠️ Importante sobre o plano gratuito do Render

O plano gratuito tem uma limitação: o servidor **"adormece"** após 15 minutos sem acesso. O primeiro acesso após o sono pode demorar ~30 segundos para acordar. Após isso, funciona normalmente.

Para evitar isso, você pode usar um serviço como o **UptimeRobot** (gratuito) para fazer um ping a cada 10 minutos:
→ https://uptimerobot.com

---

## 🗄️ Banco de dados

- Os dados ficam no **PostgreSQL do Render** e **nunca se perdem** com reinicializações
- O banco é criado e populado automaticamente na primeira vez
- Catálogo inicial: **Baby Look** e **Body Manga Curta**
