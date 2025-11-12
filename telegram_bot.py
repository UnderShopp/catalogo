#!/usr/bin/env python3
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# -------------------------
# CONFIG (desde env vars)
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # ejemplo: S0David7G/catalogo
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Path en Render (temporal)
LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

# Conversación estados
NOMBRE, PRECIO, DESCRIPCION, TALLAS, IMAGEN = range(5)

# In-memory cache (se carga desde productos.json al arrancar)
productos_db = {}

# -------------------------
# Utilidades Git / FS
# -------------------------
def repo_url_with_token():
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    """
    Clona el repo en /tmp/catalogo si no existe. Si existe, hace git pull.
    """
    try:
        if not LOCAL_REPO_PATH.exists():
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            print("Clonando repo...")
            subprocess.run(["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], check=True)
        else:
            print("Actualizando repo (pull)...")
            # Ejecutar git pull en el directorio
            subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print("Error con git (clone/pull):", e)
        return False

def load_productos_from_disk():
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        return {}
    try:
        with ruta.open("r", encoding="utf-8") as f:
            arr = json.load(f)
            # Convertir a dict por id si el archivo contiene lista
            if isinstance(arr, list):
                return {p.get("id", f"prod_{i}"): p for i, p in enumerate(arr)}
            elif isinstance(arr, dict):
                return arr
    except Exception as e:
        print("Error leyendo productos.json:", e)
    return {}

def save_and_push_productos():
    """
    Escribe productos.json en el repo local, hace commit y push.
    """
    try:
        # Asegurarnos repo disponible
        ok = ensure_repo()
        if not ok:
            print("No se pudo acceder al repo para guardar.")
            return False

        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        # Convertir dict -> lista para compatibilidad con frontend
        lista = list(productos_db.values())
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)

        # Config git local temporal (no toques config global del sistema)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@under-shopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)

        # Añadir, commit y push (usando URL con token para autenticación)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)
        # Commit solo si hay cambios (evitar error cuando no hay modificaciones)
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            print("No hay cambios para commitear.")
            return True

        mensaje = f"Automático: actualización catálogo {datetime.utcnow().isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], check=True)
        # Push usando token (remote ya apunta a origin con URL normal; usar push con URL autenticada)
        push_cmd = ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH]
        subprocess.run(push_cmd, check=True)
        print("✅ productos.json subido correctamente.")
        return True
    except subprocess.CalledProcessError as e:
        print("Error durante commit/push:", e)
        return False

# -------------------------
# Seguridad
# -------------------------
def es_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def solo_admins(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = user.id if user else None
        if not es_admin(uid):
            await update.message.reply_text("🚫 Acceso denegado. Solo administradores.")
            return
        return await func(update, context)
    return wrapper

# -------------------------
# Handlers
# -------------------------
@solo_admins
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido a *Under Shopp Bot*\n\n"
        "Envía /agregar para añadir un producto (con conversación guiada).\n"
        "También puedes usar formato simple: Nombre | Precio | ImagenURL",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Ayuda*\n\n"
        "• /agregar → Iniciar asistente para agregar producto\n"
        "• /listar → Ver productos actuales\n"
        "• /catalogo → Obtener URL pública\n\n"
        "Formato rápido (texto):\nNombre | Precio | URL_imagen",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1]}/"
    await update.message.reply_text(f"🌐 Catálogo público:\n{url}")

@solo_admins
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos aún.")
        return
    texto = "📋 Productos actuales:\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        texto += f"{i}. {p.get('nombre')} — ${p.get('precio')}\n   id: {p.get('id')}\n\n"
    await update.message.reply_text(texto)

# Conversación para agregar producto paso a paso
@solo_admins
async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🆕 Paso 1/5 - Nombre del producto (o /cancelar):")
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 Paso 2/5 - Precio (solo números):")
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().replace("$", "").replace(",", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido. Escribe solo números. Ej: 189.99")
        return PRECIO
    context.user_data['precio'] = f"{precio:.2f}"
    await update.message.reply_text("📝 Paso 3/5 - Descripción (o /saltar):")
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/5 - Tallas (ej: 36-44 o 38,40,42) (o /saltar):")
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tallas'] = update.message.text.strip()
    await update.message.reply_text("🖼️ Paso 5/5 - URL de la imagen (o /saltar):")
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Acepta texto con URL o si envían foto, obtener file URL (opcional)
    img_url = ""
    if update.message.photo:
        # Si envían foto, obtener file_path (nota: en polling esto requiere descargar vía get_file y alojarla en un host accesible)
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path  # esto no es persistente público; mejor enviar URL externa
    else:
        img_url = update.message.text.strip()
    context.user_data['imagen'] = img_url
    # Finalizar
    return await finalizar_producto(update, context)

async def saltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Avanza al siguiente paso según lo que falte
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("⏭️ Descripción omitida.\n📏 Tallas (o /saltar):")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        await update.message.reply_text("⏭️ Tallas omitidas.\n🖼️ URL de imagen (o /saltar):")
        return IMAGEN
    context.user_data['imagen'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Proceso cancelado.")
    return ConversationHandler.END

async def finalizar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        temp = context.user_data
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": temp.get("nombre", ""),
            "precio": temp.get("precio", "0.00"),
            "descripcion": temp.get("descripcion", ""),
            "tallas": temp.get("tallas", ""),
            "imagen": temp.get("imagen", ""),
            "fecha": datetime.utcnow().isoformat()
        }
        productos_db[producto["id"]] = producto

        saved = save_and_push_productos()
        if saved:
            await update.message.reply_text(f"✅ Producto *{producto['nombre']}* agregado y publicado.\n🌐 Se actualizó el catálogo público.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Producto guardado localmente, pero hubo un error subiendo a GitHub. Revisa logs.")
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error al guardar: {e}")
        context.user_data.clear()
        return ConversationHandler.END

# Handler simple para formato rápido "Nombre | Precio | URL"
@solo_admins
async def texto_rapido_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if "|" not in texto:
        await update.message.reply_text("Formato no reconocido. Usa /agregar o: Nombre | Precio | URL")
        return
    try:
        nombre, precio, imagen = [x.strip() for x in texto.split("|", 2)]
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": nombre,
            "precio": precio.replace("$",""),
            "descripcion": "",
            "tallas": "",
            "imagen": imagen,
            "fecha": datetime.utcnow().isoformat()
        }
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        if saved:
            await update.message.reply_text(f"✅ Producto *{nombre}* agregado y publicado.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Error subiendo a GitHub, producto guardado localmente.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# -------------------------
# ARRANQUE
# -------------------------
def main():
    # Validaciones iniciales
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GITHUB_USER:
        missing.append("GITHUB_USER")
    if not GITHUB_REPO:
        missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if ADMIN_ID == 0:
        missing.append("ADMIN_ID")

    if missing:
        print("ERROR: faltan variables de entorno:", ", ".join(missing))
        return

    # Intentar clonar/pull repo y cargar productos.json existente (si hay)
    ensure_repo()
    global productos_db
    productos_db = load_productos_from_disk() or {}

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("catalogo", catalogo))

    # Conversación /agregar
    conv = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion), CommandHandler("saltar", saltar)],
            TALLAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas), CommandHandler("saltar", saltar)],
            IMAGEN: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, recibir_imagen), CommandHandler("saltar", saltar)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    app.add_handler(conv)

    # Modo rápido (texto con barras)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texto_rapido_handler))

    print("🤖 Bot iniciado. Esperando mensajes...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
