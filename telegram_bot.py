#!/usr/bin/env python3
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
    except ValueError:
        print("⚠️ Error parseando ADMIN_IDS")

GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

# Estados
NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN = range(6)

productos_db = {}

def repo_url_with_token():
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        if not LOCAL_REPO_PATH.exists():
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            print("Clonando repo...")
            subprocess.run(["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], check=True)
        else:
            print("Actualizando repo (pull)...")
            subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print("Error con git:", e)
        return False

def load_productos_from_disk():
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        return {}
    try:
        with ruta.open("r", encoding="utf-8") as f:
            arr = json.load(f)
            if isinstance(arr, list):
                return {p.get("id", f"prod_{i}"): p for i, p in enumerate(arr)}
            elif isinstance(arr, dict):
                return arr
    except Exception as e:
        print("Error leyendo productos.json:", e)
    return {}

def save_and_push_productos():
    try:
        ok = ensure_repo()
        if not ok:
            return False

        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)

        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@under-shopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)
        
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            print("No hay cambios para commitear.")
            return True

        mensaje = f"Automático: actualización catálogo {datetime.utcnow().isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], check=True)
        push_cmd = ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH]
        subprocess.run(push_cmd, check=True)
        print("✅ productos.json subido correctamente.")
        return True
    except subprocess.CalledProcessError as e:
        print("Error durante commit/push:", e)
        return False

def es_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = user.id if user else None
        
        if not es_admin(uid):
            await update.message.reply_text(
                f"🚫 *Acceso Denegado*\n\n"
                f"Este bot es solo para administradores de Under Shopp.\n"
                f"Tu ID: `{uid}`",
                parse_mode="Markdown"
            )
            print(f"⚠️ Acceso no autorizado - ID: {uid}")
            return
        
        return await func(update, context)
    return wrapper

@solo_admins
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Bienvenido a Under Shopp Bot*\n\n"
        f"Hola {user.first_name}!\n\n"
        f"📋 *Comandos:*\n"
        f"• /agregar → Agregar producto\n"
        f"• /listar → Ver productos\n"
        f"• /catalogo → Ver URL pública\n"
        f"• /ayuda → Ayuda\n\n"
        f"💡 Formato rápido:\n"
        f"`Nombre | Precio | URL`",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Ayuda*\n\n"
        "*Agregar productos:*\n"
        "• /agregar → Asistente paso a paso\n"
        "• `Nombre | Precio | URL` → Rápido\n\n"
        "*Gestión:*\n"
        "• /listar → Ver productos\n"
        "• /catalogo → Ver URL\n\n"
        "*Categorías disponibles:*\n"
        "• 👟 Zapatillas\n"
        "• 👕 Ropa",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1]}/"
    await update.message.reply_text(f"🌐 Catálogo:\n{url}")

@solo_admins
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos.")
        return
    
    texto = "📋 *Productos:*\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        cat_icon = "👟" if p.get("categoria") == "zapatillas" else "👕"
        texto += f"{i}. {cat_icon} *{p.get('nombre')}*\n   💰 ${p.get('precio')}\n\n"
    
    await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "✨ *Agregar Producto*\n\n"
        "Paso 1/6: Nombre del producto",
        parse_mode="Markdown"
    )
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 Paso 2/6: Precio (solo números)")
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido. Solo números:")
        return PRECIO
    
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text("📝 Paso 3/6: Descripción (o /saltar)")
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/6: Tallas (ej: 36-42) (o /saltar)")
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tallas'] = update.message.text.strip()
    
    # Botones para seleccionar categoría
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏷️ Paso 5/6: Selecciona la categoría:",
        reply_markup=reply_markup
    )
    return CATEGORIA

async def recibir_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace("cat_", "")
    context.user_data['categoria'] = categoria
    
    cat_emoji = "👟" if categoria == "zapatillas" else "👕"
    await query.edit_message_text(
        f"✅ Categoría: {cat_emoji} {categoria.capitalize()}\n\n"
        f"📸 Paso 6/6: Envía una foto del producto (o /saltar)"
    )
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    img_url = ""
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path
    else:
        img_url = update.message.text.strip()
    
    context.user_data['imagen'] = img_url
    return await finalizar_producto(update, context)

async def saltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("📏 Paso 4/6: Tallas (o /saltar)")
        return TALLAS
    
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [
            [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
            [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🏷️ Categoría:", reply_markup=reply_markup)
        return CATEGORIA
    
    context.user_data['imagen'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

async def finalizar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        temp = context.user_data
        user = update.effective_user
        
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": temp.get("nombre", ""),
            "precio": temp.get("precio", "0"),
            "descripcion": temp.get("descripcion", ""),
            "tallas": temp.get("tallas", ""),
            "categoria": temp.get("categoria", "zapatillas"),
            "imagen": temp.get("imagen", ""),
            "fecha": datetime.utcnow().isoformat(),
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
            await update.message.reply_text("⚠️ Error subiendo a GitHub")
        
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data.clear()
        return ConversationHandler.END

@solo_admins
async def texto_rapido_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    user = update.effective_user
    
    if "|" not in texto:
        return
    
    try:
        partes = texto.split("|")
        if len(partes) < 2:
            return
        
        nombre = partes[0].strip()
        precio = partes[1].strip().replace("$","").replace(",","").replace(".","")
        imagen = partes[2].strip() if len(partes) > 2 else ""
        
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": nombre,
            "precio": precio,
            "descripcion": "",
            "tallas": "",
            "categoria": "zapatillas",
            "imagen": imagen,
            "fecha": datetime.utcnow().isoformat(),
            "agregado_por": user.first_name or "Admin"
        }
        
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        
        if saved:
            await update.message.reply_text(
                f"✅ *Producto agregado*\n\n"
                f"👟 {nombre}\n"
                f"💰 ${precio}",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_USER: missing.append("GITHUB_USER")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS: missing.append("ADMIN_IDS")

    if missing:
        print(f"❌ Faltan variables: {', '.join(missing)}")
        return

    print(f"✅ Bot configurado")
    print(f"👥 Admins autorizados: {len(ADMIN_IDS)}")

    ensure_repo()
    global productos_db
    productos_db = load_productos_from_disk() or {}
    print(f"📦 Productos: {len(productos_db)}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
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
            IMAGEN: [
                MessageHandler(filters.PHOTO, recibir_imagen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen),
                CommandHandler("saltar", saltar)
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texto_rapido_handler))

    print("🤖 Bot iniciado...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
