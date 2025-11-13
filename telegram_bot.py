#!/usr/bin/env python3
import os
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# CONFIGURACIÓN
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
    except ValueError:
        print("Error parseando ADMIN_IDS")

GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

print(f"\n🧩 CONFIGURACIÓN:")
print(f"   BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
print(f"   ADMIN_IDS: {ADMIN_IDS}")
print(f"   GITHUB_USER: {GITHUB_USER}")
print(f"   GITHUB_REPO: {GITHUB_REPO}")
print(f"   GITHUB_TOKEN: {'✅' if GITHUB_TOKEN else '❌'}\n")

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN = range(6)

productos_db = {}

# GIT FUNCTIONS
def repo_url_with_token():
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        if not LOCAL_REPO_PATH.exists():
            print("📥 Clonando repositorio...")
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ Error clonando: {result.stderr}")
                return False
            print("✅ Repositorio clonado")
        else:
            print("🔄 Actualizando repositorio...")
            result = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"⚠️ Error en pull: {result.stderr}")
            else:
                print("✅ Repositorio actualizado")
        return True
    except Exception as e:
        print(f"❌ Error con git: {e}")
        return False

def load_productos_from_disk():
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        print("📄 productos.json no existe, creando...")
        return []
    try:
        with ruta.open("r", encoding="utf-8") as f:
            productos = json.load(f)
            print(f"📦 Cargados {len(productos)} productos")
            return productos if isinstance(productos, list) else []
    except Exception as e:
        print(f"❌ Error leyendo productos.json: {e}")
    return []

def save_and_push_productos():
    try:
        print("\n💾 Guardando productos...")
        ok = ensure_repo()
        if not ok:
            print("❌ No se pudo acceder al repositorio")
            return False
        
        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        print(f"📝 Escribiendo {len(lista)} productos")
        
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        print("✅ Archivo escrito")
        
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@undershopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)
        
        print("➕ Git add...")
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)
        
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            print("ℹ️ No hay cambios para commitear")
            return True
        
        print("📝 Git commit...")
        mensaje = f"Bot: actualizacion {datetime.now(timezone.utc).isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], check=True)
        
        print("☁️ Git push...")
        result = subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ ERROR EN PUSH:")
            print(f"   Return code: {result.returncode}")
            print(f"   Stdout: {result.stdout}")
            print(f"   Stderr: {result.stderr}")
            return False
        
        print("✅ Push exitoso\n")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# SECURITY
def es_admin(user_id):
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update, context):
        user = update.effective_user
        uid = user.id if user else None
        if not es_admin(uid):
            await update.message.reply_text(f"🚫 Acceso denegado. Tu ID: {uid}")
            print(f"⚠️ Acceso no autorizado - ID: {uid}")
            return
        return await func(update, context)
    return wrapper

# COMMANDS
@solo_admins
async def start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Bienvenido {user.first_name}*\n\n"
        f"📋 Comandos disponibles:\n"
        f"• /agregar - Agregar producto\n"
        f"• /listar - Ver productos\n"
        f"• /catalogo - Ver URL del catálogo\n\n"
        f"💡 Tienes acceso de administrador",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1] if '/' in GITHUB_REPO else GITHUB_REPO}/"
    await update.message.reply_text(f"🌐 *Catálogo web:*\n{url}", parse_mode="Markdown")

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos en el catálogo")
        return
    texto = "📋 *Productos:*\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        texto += f"{i}. {cat_emoji} *{p.get('nombre')}*\n   💰 ${p.get('precio')}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "✨ *Agregar Producto*\n\n"
        "Paso 1/6: Escribe el *nombre* del producto",
        parse_mode="Markdown"
    )
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 Paso 2/6: Escribe el *precio* (solo números)", parse_mode="Markdown")
    return PRECIO

async def recibir_precio(update, context):
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido. Escribe solo números:")
        return PRECIO
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text("📝 Paso 3/6: Escribe una *descripción*\n(o /saltar)", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_descripcion(update, context):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/6: ¿Qué *tallas* hay?\n(ej: 36-42 o /saltar)", parse_mode="Markdown")
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    await update.message.reply_text("🏷️ Paso 5/6: Selecciona la *categoría*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    cat_emoji = "👟" if query.data == "cat_zapatillas" else "👕"
    await query.edit_message_text(f"✅ Categoría: {cat_emoji}\n\n📸 Paso 6/6: Envía una *foto*\n(o /saltar)", parse_mode="Markdown")
    return IMAGEN

async def recibir_imagen(update, context):
    img_url = ""
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path
    else:
        img_url = update.message.text.strip() if update.message.text else ""
    context.user_data['imagen'] = img_url
    return await finalizar_producto(update, context)

async def saltar(update, context):
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("📏 Tallas (o /saltar)")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")], [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]]
        await update.message.reply_text("🏷️ Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORIA
    context.user_data['imagen'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada")
    return ConversationHandler.END

async def finalizar_producto(update, context):
    try:
        temp = context.user_data
        user = update.effective_user
        
        producto = {
            "id": f"producto_{int(datetime.now(timezone.utc).timestamp())}",
            "nombre": temp.get("nombre", ""),
            "precio": temp.get("precio", "0"),
            "descripcion": temp.get("descripcion", ""),
            "tallas": temp.get("tallas", ""),
            "categoria": temp.get("categoria", "zapatillas"),
            "imagen": temp.get("imagen", ""),
            "fecha": datetime.now(timezone.utc).isoformat(),
            "agregado_por": user.first_name or "Admin"
        }
        
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        
        cat_emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
        
        if saved:
            await update.message.reply_text(
                f"✅ *Producto agregado*\n\n"
                f"{cat_emoji} *{producto['nombre']}*\n"
                f"💰 ${producto['precio']}\n"
                f"👤 Por: {user.first_name}\n\n"
                f"🌐 Ya está en el catálogo web",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Error al guardar en GitHub. Revisa los logs.")
        
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data.clear()
        return ConversationHandler.END

# HEALTH SERVER
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot OK')
    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🩺 Servidor HTTP en puerto {port}")
    server.serve_forever()

# MAIN
def main():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_USER: missing.append("GITHUB_USER")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS: missing.append("ADMIN_IDS")
    
    if missing:
        print(f"❌ Faltan variables: {', '.join(missing)}")
        print("\n💡 Configura en Render > Environment:")
        for var in missing:
            print(f"   • {var}")
        return
    
    # Servidor HTTP en thread separado
    threading.Thread(target=start_health_server, daemon=True).start()
    
    # Cargar productos
    ensure_repo()
    global productos_db
    productos_lista = load_productos_from_disk()
    productos_db = {p.get("id", f"prod_{i}"): p for i, p in enumerate(productos_lista)}
    
    # Bot
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
            IMAGEN: [MessageHandler(filters.PHOTO, recibir_imagen), MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen), CommandHandler("saltar", saltar)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    )
    
    app.add_handler(conv)
    
    print("🤖 Bot iniciado (modo polling)\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
