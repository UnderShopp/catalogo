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

print(f"\n🔧 CONFIG:")
print(f"   GITHUB_USER: {GITHUB_USER}")
print(f"   GITHUB_REPO: {GITHUB_REPO}")
print(f"   GITHUB_TOKEN: {'✅' if GITHUB_TOKEN else '❌'}")
print(f"   ADMIN_IDS: {ADMIN_IDS}\n")

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
            print("📥 Clonando repositorio...")
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ Error clonando: {result.stderr}")
                return False
            print("✅ Repo clonado")
        else:
            print("🔄 Actualizando repo...")
            result = subprocess.run(
                ["git", "-C", str(LOCAL_REPO_PATH), "pull"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"⚠️ Error en pull: {result.stderr}")
            else:
                print("✅ Repo actualizado")
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
            print("❌ No se pudo acceder al repo")
            return False

        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        
        print(f"📝 Escribiendo {len(lista)} productos en {JSON_FILENAME}")
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        print("✅ Archivo escrito")

        # Config git
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@undershopp.local"], check=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], check=True)
        
        # Add
        print("➕ Git add...")
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], check=True)
        
        # Check status
        res = subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"],
            capture_output=True,
            text=True
        )
        
        if res.stdout.strip() == "":
            print("ℹ️ No hay cambios para commitear")
            return True

        # Commit
        print("📝 Git commit...")
        mensaje = f"Bot: actualización {datetime.utcnow().isoformat()}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], check=True)
        
        # Push
        print("☁️ Git push...")
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH],
            check=True,
            capture_output=True
        )
        print("✅ Push exitoso!\n")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error en git: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            print(f"   Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error general: {e}")
        return False

def es_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = user.id if user else None
        if not es_admin(uid):
            await update.message.reply_text(f"🚫 Acceso denegado. Tu ID: {uid}")
            return
        return await func(update, context)
    return wrapper

@solo_admins
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 *Under Shopp Bot*\n\n"
        f"/agregar - Agregar producto\n"
        f"/listar - Ver productos\n"
        f"/catalogo - Ver URL",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1] if '/' in GITHUB_REPO else GITHUB_REPO}/"
    await update.message.reply_text(f"🌐 {url}")

@solo_admins
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not productos_db:
        await update.message.reply_text("📭 Sin productos")
        return
    texto = "📋 *Productos:*\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        texto += f"{i}. *{p.get('nombre')}* - ${p.get('precio')}\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("✨ Paso 1/6: Nombre del producto")
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
        await update.message.reply_text("❌ Precio inválido")
        return PRECIO
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text("📝 Paso 3/6: Descripción (o /saltar)")
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/6: Tallas (o /saltar)")
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    await update.message.reply_text(
        "🏷️ Paso 5/6: Categoría:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORIA

async def recibir_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    await query.edit_message_text("📸 Paso 6/6: Envía foto (o /saltar)")
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
        await update.message.reply_text("📏 Tallas (o /saltar)")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
                    [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]]
        await update.message.reply_text("🏷️ Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CATEGORIA
    context.user_data['imagen'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado")
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
            "fecha": datetime.utcnow().isoformat()
        }
        
        productos_db[producto["id"]] = producto
        
        saved = save_and_push_productos()
        
        if saved:
            await update.message.reply_text(
                f"✅ *Producto agregado*\n\n"
                f"👟 {producto['nombre']}\n"
                f"💰 ${producto['precio']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Error al guardar en GitHub")
        
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data.clear()
        return ConversationHandler.END

def main():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_USER: missing.append("GITHUB_USER")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS: missing.append("ADMIN_IDS")

    if missing:
        print(f"❌ Faltan: {', '.join(missing)}")
        return

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
            IMAGEN: [
                MessageHandler(filters.PHOTO, recibir_imagen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen),
                CommandHandler("saltar", saltar)
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    
    app.add_handler(conv)

    print("🤖 Bot iniciado...\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
```

