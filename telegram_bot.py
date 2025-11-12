#!/usr/bin/env python3
import os
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

# --- Configuración del entorno ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
PORT = int(os.getenv("PORT", "10000"))

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

print(f"""
🧩 CONFIGURACIÓN:
- GITHUB_USER: {GITHUB_USER}
- GITHUB_REPO: {GITHUB_REPO}
- TOKEN: {'OK' if GITHUB_TOKEN else 'FALTA'}
- ADMIN_IDS: {ADMIN_IDS}
- URL Render: {RENDER_EXTERNAL_URL}
""")

# --- Variables globales ---
NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN = range(6)
productos_db = {}

# --- GitHub helpers ---
def repo_url_with_token():
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        if not LOCAL_REPO_PATH.exists():
            print("🌀 Clonando repo...")
            subprocess.run(["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], check=True)
        else:
            subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error git: {e}")
        return False

def save_and_push_productos():
    try:
        ok = ensure_repo()
        if not ok:
            print("⚠️ No se pudo acceder al repo.")
            return False

        ruta = LOCAL_REPO_PATH / JSON_FILENAME

        productos_existentes = []
        if ruta.exists():
            try:
                with ruta.open("r", encoding="utf-8") as f:
                    productos_existentes = json.load(f)
            except Exception:
                productos_existentes = []

        productos_actualizados = {p.get("id"): p for p in productos_existentes if isinstance(p, dict)}
        productos_actualizados.update(productos_db)

        with ruta.open("w", encoding="utf-8") as f:
            json.dump(list(productos_actualizados.values()), f, ensure_ascii=False, indent=2)

        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@undershopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)

        status = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"],
                                capture_output=True, text=True)
        if status.stdout.strip() == "":
            print("ℹ️ No hay cambios nuevos.")
            return True

        msg = f"🕒 Bot: actualización {datetime.now(timezone.utc).isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", msg], check=True)
        push = subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH],
            capture_output=True, text=True
        )

        if push.returncode != 0:
            print(f"❌ Push error: {push.stderr}")
            return False

        print("✅ Push a GitHub exitoso.")
        return True
    except Exception as e:
        print(f"💥 Error general al guardar: {e}")
        return False

# --- Funciones del bot ---
def es_admin(user_id): return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update, context):
        uid = update.effective_user.id
        if not es_admin(uid):
            await update.message.reply_text(f"🚫 Acceso denegado.\nTu ID: `{uid}`", parse_mode="Markdown")
            return
        return await func(update, context)
    return wrapper

@solo_admins
async def start(update, context):
    await update.message.reply_text(
        "👋 *Bienvenido al Bot UnderShopp*\n\n"
        "✨ Administra tus productos fácilmente.\n\n"
        "📋 *Comandos:*\n"
        "• `/agregar` → Añadir un producto\n"
        "• `/listar` → Ver todos los productos\n"
        "• `/catalogo` → Ver el catálogo online",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    repo_name = GITHUB_REPO.split("/", 1)[1] if "/" in GITHUB_REPO else GITHUB_REPO
    url = f"https://{GITHUB_USER}.github.io/{repo_name}/"
    await update.message.reply_text(f"🌐 *Catálogo público:*\n[{url}]({url})", parse_mode="Markdown")

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("⚠️ No hay productos aún.", parse_mode="Markdown")
        return
    texto = "🛍️ *Productos actuales:*\n\n"
    for p in productos_db.values():
        texto += f"📦 {p['nombre']} — 💰 ${p['precio']}\n📏 {p['tallas'] or 'N/A'}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    await update.message.reply_text("🧾 *Paso 1:* Escribe el *nombre del producto*.", parse_mode="Markdown")
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data["nombre"] = update.message.text.strip()
    await update.message.reply_text("💰 *Paso 2:* Ingresa el *precio* (solo números).", parse_mode="Markdown")
    return PRECIO

async def recibir_precio(update, context):
    try:
        context.user_data["precio"] = str(float(update.message.text.strip()))
        await update.message.reply_text("📝 *Paso 3:* Escribe una *descripción* o usa /saltar.", parse_mode="Markdown")
        return DESCRIPCION
    except:
        await update.message.reply_text("❌ Precio inválido.")
        return PRECIO

async def recibir_descripcion(update, context):
    context.user_data["descripcion"] = update.message.text.strip()
    await update.message.reply_text("📏 *Paso 4:* Ingresa *tallas disponibles* o usa /saltar.", parse_mode="Markdown")
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data["tallas"] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas"),
                 InlineKeyboardButton("🧥 Ropa", callback_data="cat_ropa")]]
    await update.message.reply_text("🗂️ *Paso 5:* Elige una *categoría:*",
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode="Markdown")
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["categoria"] = query.data.replace("cat_", "")
    await query.edit_message_text("📸 *Paso 6:* Envía una *foto del producto* o usa /saltar.", parse_mode="Markdown")
    return IMAGEN

async def recibir_imagen(update, context):
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path
    else:
        img_url = ""
    context.user_data["imagen"] = img_url
    return await finalizar_producto(update, context)

async def saltar(update, context):
    keys = list(context.user_data.keys())
    if "descripcion" not in keys:
        context.user_data["descripcion"] = ""
        await update.message.reply_text("📏 Tallas (o /saltar):")
        return TALLAS
    elif "tallas" not in keys:
        context.user_data["tallas"] = ""
        keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas"),
                     InlineKeyboardButton("🧥 Ropa", callback_data="cat_ropa")]]
        await update.message.reply_text("🗂️ Selecciona categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORIA
    context.user_data["imagen"] = ""
    return await finalizar_producto(update, context)

async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

async def finalizar_producto(update, context):
    try:
        data = context.user_data
        producto = {
            "id": f"prod_{int(datetime.now().timestamp())}",
            "nombre": data.get("nombre", ""),
            "precio": data.get("precio", "0"),
            "descripcion": data.get("descripcion", ""),
            "tallas": data.get("tallas", ""),
            "categoria": data.get("categoria", "zapatillas"),
            "imagen": data.get("imagen", ""),
            "fecha": datetime.now(timezone.utc).isoformat()
        }

        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()

        if saved:
            msg = (
                "✅ ¡Producto agregado exitosamente!\n\n"
                f"📦 {producto['nombre']}\n"
                f"💰 ${float(producto['precio']):,.2f}\n"
                f"📏 Tallas: {producto['tallas'] or 'N/A'}\n"
                f"👕 Categoría: {producto['categoria'].capitalize()}\n\n"
                "El producto ya está visible en el catálogo web.\n"
                "Usa /agregar para añadir otro producto."
            )
            if producto["imagen"]:
                await update.message.reply_photo(photo=producto["imagen"], caption=msg, parse_mode="Markdown")
            else:
                await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Error al guardar en GitHub. Verifica token o conexión.")
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"💥 Error: {e}")
        return ConversationHandler.END

# --- Servidor HTTP de salud ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot OK")

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"🩺 Servidor de salud en puerto {PORT}")

# --- Main ---
def main():
    if not all([BOT_TOKEN, GITHUB_USER, GITHUB_REPO, GITHUB_TOKEN, ADMIN_IDS]):
        print("⚠️ Faltan variables de entorno necesarias.")
        return

    start_health_server()
    ensure_repo()

    global productos_db
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if ruta.exists():
        with ruta.open("r", encoding="utf-8") as f:
            productos_lista = json.load(f)
            productos_db = {p.get("id", f"id_{i}"): p for i, p in enumerate(productos_lista)}

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("catalogo", catalogo))

    conv = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion), CommandHandler("saltar", saltar)],
            TALLAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas), CommandHandler("saltar", saltar)],
            CATEGORIA: [CallbackQueryHandler(recibir_categoria, pattern="^cat_")],
            IMAGEN: [MessageHandler(filters.PHOTO, recibir_imagen), CommandHandler("saltar", saltar)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    )
    app.add_handler(conv)

    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        print(f"🌐 Modo webhook activo: {webhook_url}")
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=webhook_url)
    else:
        print("📡 Modo polling local activo")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
