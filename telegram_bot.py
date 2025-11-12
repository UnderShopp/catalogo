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

print(f"\nCONFIG:")
print(f"GITHUB_USER: {GITHUB_USER}")
print(f"GITHUB_REPO: {GITHUB_REPO}")
print(f"GITHUB_TOKEN: {'OK' if GITHUB_TOKEN else 'FALTA'}")
print(f"ADMIN_IDS: {ADMIN_IDS}\n")

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN = range(6)

productos_db = {}

def repo_url_with_token():
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        if not LOCAL_REPO_PATH.exists():
            print("🌀 Clonando repo...")
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ Error clonando: {result.stderr}")
                return False
            print("✅ Repo clonado correctamente.")
        else:
            print("🔄 Actualizando repo...")
            result = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"⚠️ Error en pull: {result.stderr}")
            else:
                print("📦 Repo actualizado correctamente.")
        return True
    except Exception as e:
        print(f"💥 Error con git: {e}")
        return False

def load_productos_from_disk():
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        print("⚠️ productos.json no existe.")
        return []
    try:
        with ruta.open("r", encoding="utf-8") as f:
            productos = json.load(f)
            print(f"✅ Cargados {len(productos)} productos del archivo.")
            return productos if isinstance(productos, list) else []
    except Exception as e:
        print(f"❌ Error leyendo productos.json: {e}")
    return []

def save_and_push_productos():
    try:
        print("\n💾 Guardando productos...")
        ok = ensure_repo()
        if not ok:
            print("⚠️ No se pudo acceder al repo.")
            return False
        
        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        print(f"✍️ Escribiendo {len(lista)} productos...")
        
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        print("✅ Archivo JSON actualizado.")
        
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@undershopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)
        
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)
        
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            print("ℹ️ No hay cambios para guardar.")
            return True
        
        mensaje = f"🕒 Bot: actualización {datetime.now(timezone.utc).isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], check=True)
        print("✅ Commit creado.")
        
        result = subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"❌ ERROR EN PUSH:")
            print(f"{result.stderr}")
            return False
        
        print("🚀 Push exitoso.\n")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"💥 Error en comando git: {e}")
        return False
    except Exception as e:
        print(f"💥 Error general: {e}")
        return False

def es_admin(user_id):
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update, context):
        user = update.effective_user
        uid = user.id if user else None
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
        "📋 *Comandos disponibles:*\n"
        "• `/agregar` → Agregar un producto nuevo\n"
        "• `/listar` → Ver todos los productos\n"
        "• `/catalogo` → Ver el catálogo online\n\n"
        "🧾 Usa `/cancelar` para detener cualquier acción.",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1] if '/' in GITHUB_REPO else GITHUB_REPO}/"
    await update.message.reply_text(f"🌐 *Catálogo público:*\n[{url}]({url})", parse_mode="Markdown")

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("⚠️ *No hay productos registrados aún.*", parse_mode="Markdown")
        return
    texto = "🛍️ *Catálogo actual:*\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        texto += f"*{i}. {p.get('nombre')}*  💵 ${p.get('precio')}\n📦 {p.get('categoria').capitalize()}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    await update.message.reply_text("🧾 *Paso 1/6:* Escribe el *nombre del producto*", parse_mode="Markdown")
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 *Paso 2/6:* Ingresa el *precio* (solo números)", parse_mode="Markdown")
    return PRECIO

async def recibir_precio(update, context):
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido. Intenta nuevamente.")
        return PRECIO
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text("📝 *Paso 3/6:* Escribe una *descripción* o usa /saltar", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_descripcion(update, context):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 *Paso 4/6:* Ingresa *tallas disponibles* o usa /saltar", parse_mode="Markdown")
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas"),
         InlineKeyboardButton("🧥 Ropa", callback_data="cat_ropa")]
    ]
    await update.message.reply_text("🗂️ *Paso 5/6:* Selecciona una *categoría:*", 
                                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    await query.edit_message_text("📸 *Paso 6/6:* Envía una *foto del producto* o usa /saltar", parse_mode="Markdown")
    return IMAGEN

async def recibir_imagen(update, context):
    img_url = ""
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path
    else:
        img_url = update.message.text.strip()
    context.user_data['imagen'] = img_url
    return await finalizar_producto(update, context)

async def saltar(update, context):
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("📏 Tallas disponibles (o /saltar):")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas"),
                     InlineKeyboardButton("🧥 Ropa", callback_data="cat_ropa")]]
        await update.message.reply_text("🗂️ Selecciona una categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORIA
    context.user_data['imagen'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ *Operación cancelada.*", parse_mode="Markdown")
    return ConversationHandler.END

async def finalizar_producto(update, context):
    try:
        temp = context.user_data
        producto = {
            "id": f"producto_{int(datetime.now(timezone.utc).timestamp())}",
            "nombre": temp.get("nombre", "").strip(),
            "precio": temp.get("precio", "0").strip(),
            "descripcion": temp.get("descripcion", "").strip(),
            "tallas": temp.get("tallas", "").strip(),
            "categoria": temp.get("categoria", "zapatillas").strip(),
            "imagen": temp.get("imagen", "").strip(),
            "fecha": datetime.now(timezone.utc).isoformat()
        }

        # ✅ Guardar en memoria antes de escribir al JSON
        productos_db[producto["id"]] = producto

        # 💾 Guardar en productos.json y subir a GitHub
        saved = save_and_push_productos()

        if saved:
            mensaje = (
                "✅ ¡Producto agregado exitosamente!\n\n"
                f"📦 *{producto['nombre']}*\n"
                f"💰 ${float(producto['precio']):,.2f}\n"
                f"📏 *Tallas:* {producto['tallas'] or 'N/A'}\n"
                f"👕 *Categoría:* {producto['categoria'].capitalize()}\n\n"
                "🛍️ El producto ya está visible en el catálogo web.\n"
                "Usa /agregar para añadir otro producto."
            )

            # Si el producto tiene imagen, mostrarla junto con el texto
            if producto["imagen"]:
                await update.message.reply_photo(
                    photo=producto["imagen"],
                    caption=mensaje,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(mensaje, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "⚠️ *Error al guardar en GitHub.*\nVerifica conexión o credenciales.",
                parse_mode="Markdown"
            )

        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"💥 Error: {e}")
        context.user_data.clear()
        return ConversationHandler.END


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
    print(f"🩺 Servidor HTTP de salud en puerto {port}")
    server.serve_forever()

def main():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_USER: missing.append("GITHUB_USER")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS: missing.append("ADMIN_IDS")
    if missing:
        print(f"⚠️ Faltan variables de entorno: {', '.join(missing)}")
        return
    
    threading.Thread(target=start_health_server, daemon=True).start()
    
    ensure_repo()
    global productos_db
    productos_lista = load_productos_from_disk()
    productos_db = {p.get("id", f"prod_{i}"): p for i, p in enumerate(productos_lista)}
    
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
    print("🤖 Bot iniciado correctamente.\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
