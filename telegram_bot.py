#!/usr/bin/env python3
import os
import json
import subprocess
import base64
from datetime import datetime, timezone
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
import httpx

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
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")

if GITHUB_REPO and "/" in GITHUB_REPO:
    GITHUB_REPO = GITHUB_REPO.split("/")[-1]

print(f"\n🧩 CONFIGURACIÓN:")
print(f"   BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
print(f"   ADMIN_IDS: {ADMIN_IDS}")
print(f"   GITHUB_USER: {GITHUB_USER}")
print(f"   GITHUB_REPO: {GITHUB_REPO}")
print(f"   GITHUB_TOKEN: {'✅' if GITHUB_TOKEN else '❌'}")
print(f"   IMGBB_API_KEY: {'✅' if IMGBB_API_KEY else '⚠️'}\n")

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN, MAS_MEDIOS = range(7)
EDITAR_CAMPO, EDITAR_VALOR = range(7, 9)

productos_db = {}

def repo_url_with_token():
    if not GITHUB_USER or not GITHUB_REPO:
        return None
    return f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        repo_url = repo_url_with_token()
        if not repo_url:
            return False
        if not LOCAL_REPO_PATH.exists():
            print(f"📥 Clonando repositorio...")
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", "--depth", "1", repo_url, str(LOCAL_REPO_PATH)], capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                print(f"❌ Error clonando: {result.stderr}")
                return False
            print("✅ Repositorio clonado")
        else:
            git_dir = LOCAL_REPO_PATH / ".git"
            if not git_dir.exists():
                import shutil
                shutil.rmtree(LOCAL_REPO_PATH)
                return ensure_repo()
            subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "pull"], capture_output=True, timeout=30)
        return True
    except Exception as e:
        print(f"❌ Error git: {e}")
        return False

def load_productos_from_disk():
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        return []
    try:
        with ruta.open("r", encoding="utf-8") as f:
            productos = json.load(f)
            print(f"📦 Cargados {len(productos)} productos")
            return productos if isinstance(productos, list) else []
    except Exception as e:
        print(f"❌ Error leyendo: {e}")
    return []

def save_and_push_productos():
    try:
        if not LOCAL_REPO_PATH.exists():
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
        git_dir = LOCAL_REPO_PATH / ".git"
        if not git_dir.exists():
            ensure_repo()
        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        if not git_dir.exists():
            return True
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@local"], capture_output=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "Bot"], capture_output=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], capture_output=True)
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            return True
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", "Bot update"], capture_output=True)
        repo_url = repo_url_with_token()
        if repo_url:
            subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url, REPO_BRANCH], capture_output=True, timeout=30)
        print("✅ Push exitoso")
        return True
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return True

def format_precio(precio):
    try:
        p = float(precio)
        return f"{int(p):,}" if p == int(p) else f"{p:,.2f}"
    except:
        return str(precio)

async def subir_imagen_imgbb(file_bytes, filename="img.jpg"):
    if not IMGBB_API_KEY:
        return None
    try:
        img_b64 = base64.b64encode(file_bytes).decode('utf-8')
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_API_KEY, "image": img_b64, "name": filename})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data["data"]["display_url"]
        return None
    except Exception as e:
        print(f"❌ Error ImgBB: {e}")
        return None

def es_admin(user_id):
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update, context):
        user = update.effective_user
        if not es_admin(user.id if user else None):
            await update.message.reply_text(f"🚫 Acceso denegado. Tu ID: {user.id}")
            return
        return await func(update, context)
    return wrapper

@solo_admins
async def start(update, context):
    await update.message.reply_text(
        f"👋 *Bienvenido*\n\n"
        f"🆕 /agregar - Agregar producto\n"
        f"📋 /listar - Ver productos\n"
        f"✏️ /editar - Editar\n"
        f"🗑️ /eliminar - Eliminar\n"
        f"🌐 /catalogo - Ver URL",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/"
    await update.message.reply_text(f"🌐 *Catálogo:*\n{url}", parse_mode="Markdown")

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos")
        return
    texto = f"📋 *Productos ({len(productos_db)}):*\n\n"
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True), 1):
        emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        medios = 1 if p.get('imagen') else 0
        medios += len(p.get('imagenes', [])) + len(p.get('videos', []))
        texto += f"{i}. {emoji} *{p.get('nombre')}* - ${format_precio(p.get('precio', '0'))} ({medios} 📷)\n"
        if len(texto) > 3500:
            await update.message.reply_text(texto, parse_mode="Markdown")
            texto = ""
    if texto:
        await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def eliminar_comando(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos")
        return
    keyboard = [[InlineKeyboardButton(f"{'👟' if p.get('categoria')=='zapatillas' else '👕'} {p.get('nombre')}", callback_data=f"del_{p.get('id')}")] for p in sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)[:20]]
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")])
    await update.message.reply_text("🗑️ *Selecciona:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def eliminar_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "del_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return
    if query.data.startswith("del_confirm_"):
        pid = query.data.replace("del_confirm_", "")
        if pid in productos_db:
            nombre = productos_db[pid].get('nombre')
            del productos_db[pid]
            save_and_push_productos()
            await query.edit_message_text(f"✅ *{nombre}* eliminado", parse_mode="Markdown")
        return
    if query.data.startswith("del_"):
        pid = query.data.replace("del_", "")
        if pid in productos_db:
            keyboard = [[InlineKeyboardButton("✅ Sí", callback_data=f"del_confirm_{pid}")], [InlineKeyboardButton("❌ No", callback_data="del_cancelar")]]
            await query.edit_message_text(f"⚠️ ¿Eliminar *{productos_db[pid].get('nombre')}*?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

@solo_admins
async def editar_comando(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(f"{p.get('nombre')}", callback_data=f"edit_{p.get('id')}")] for p in sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)[:20]]
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")])
    await update.message.reply_text("✏️ *Selecciona:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return EDITAR_CAMPO

async def editar_seleccionar_campo(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return ConversationHandler.END
    if query.data.startswith("edit_"):
        pid = query.data.replace("edit_", "")
        if pid in productos_db:
            context.user_data['edit_producto_id'] = pid
            keyboard = [[InlineKeyboardButton("📝 Nombre", callback_data="ef_nombre")], [InlineKeyboardButton("💰 Precio", callback_data="ef_precio")], [InlineKeyboardButton("📄 Descripción", callback_data="ef_descripcion")], [InlineKeyboardButton("📏 Tallas", callback_data="ef_tallas")], [InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")]]
            await query.edit_message_text("¿Qué editar?", reply_markup=InlineKeyboardMarkup(keyboard))
            return EDITAR_CAMPO
    return ConversationHandler.END

async def editar_pedir_valor(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return ConversationHandler.END
    campo = query.data.replace("ef_", "")
    context.user_data['edit_campo'] = campo
    await query.edit_message_text(f"Escribe nuevo {campo}:")
    return EDITAR_VALOR

async def editar_guardar_valor(update, context):
    valor = update.message.text.strip()
    pid = context.user_data.get('edit_producto_id')
    campo = context.user_data.get('edit_campo')
    if pid in productos_db:
        if campo == "precio":
            try:
                valor = f"{float(valor.replace('$','').replace(',','').replace('.','')):.0f}"
            except:
                await update.message.reply_text("❌ Precio inválido")
                return ConversationHandler.END
        productos_db[pid][campo] = valor
        save_and_push_productos()
        await update.message.reply_text("✅ Actualizado")
    context.user_data.clear()
    return ConversationHandler.END

@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    context.user_data['imagenes'] = []
    context.user_data['videos'] = []
    await update.message.reply_text("✨ *Nuevo Producto*\n\nPaso 1/6: *Nombre*", parse_mode="Markdown")
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 Paso 2/6: *Precio*", parse_mode="Markdown")
    return PRECIO

async def recibir_precio(update, context):
    try:
        precio = float(update.message.text.strip().replace("$","").replace(",","").replace(".",""))
        context.user_data['precio'] = f"{precio:.0f}"
    except:
        await update.message.reply_text("❌ Inválido, solo números:")
        return PRECIO
    await update.message.reply_text("📝 Paso 3/6: *Descripción* (/saltar)", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_descripcion(update, context):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/6: *Tallas* (/saltar)", parse_mode="Markdown")
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")], [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]]
    await update.message.reply_text("🏷️ Paso 5/6: *Categoría*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    await query.edit_message_text("📸 Paso 6/6: Envía *fotos/videos*\n\nPuedes enviar varios.\n(/saltar para omitir)", parse_mode="Markdown")
    return IMAGEN

async def recibir_imagen(update, context):
    if 'imagenes' not in context.user_data:
        context.user_data['imagenes'] = []
    if 'videos' not in context.user_data:
        context.user_data['videos'] = []
    
    url = ""
    es_video = False
    
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        if IMGBB_API_KEY:
            await update.message.reply_text("📤 Subiendo...")
            try:
                fbytes = await file.download_as_bytearray()
                url = await subir_imagen_imgbb(fbytes)
                if url:
                    await update.message.reply_text("✅ Subida")
            except Exception as e:
                print(f"Error: {e}")
    elif update.message.video:
        file = await update.message.video.get_file()
        url = file.file_path
        es_video = True
        await update.message.reply_text("✅ Video agregado")
    elif update.message.text and update.message.text.startswith("http"):
        url = update.message.text.strip()
        es_video = any(x in url.lower() for x in ['.mp4', '.mov', '.webm'])
    
    if url:
        if es_video:
            context.user_data['videos'].append(url)
        elif not context.user_data.get('imagen'):
            context.user_data['imagen'] = url
        else:
            context.user_data['imagenes'].append(url)
    
    total = (1 if context.user_data.get('imagen') else 0) + len(context.user_data.get('imagenes', [])) + len(context.user_data.get('videos', []))
    keyboard = [[InlineKeyboardButton("📸 Más fotos", callback_data="mas_fotos")], [InlineKeyboardButton("🎬 Video", callback_data="mas_video")], [InlineKeyboardButton("✅ Finalizar", callback_data="finalizar_medios")]]
    await update.message.reply_text(f"📷 *Medios: {total}*\n\n¿Agregar más?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAS_MEDIOS

async def procesar_mas_medios(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "finalizar_medios":
        await query.edit_message_text("✅ Guardando...")
        return await finalizar_producto_callback(query, context)
    await query.edit_message_text(f"📸 Envía {'foto' if query.data == 'mas_fotos' else 'video'} (/saltar para finalizar)")
    return MAS_MEDIOS

async def recibir_mas_medios(update, context):
    url = ""
    es_video = False
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        if IMGBB_API_KEY:
            await update.message.reply_text("📤 Subiendo...")
            try:
                url = await subir_imagen_imgbb(await file.download_as_bytearray())
                if url:
                    await update.message.reply_text("✅ Agregada")
            except:
                pass
    elif update.message.video:
        file = await update.message.video.get_file()
        url = file.file_path
        es_video = True
        await update.message.reply_text("✅ Video agregado")
    elif update.message.text and update.message.text.startswith("http"):
        url = update.message.text.strip()
        es_video = any(x in url.lower() for x in ['.mp4', '.mov', '.webm'])
    
    if url:
        if es_video:
            context.user_data.setdefault('videos', []).append(url)
        else:
            context.user_data.setdefault('imagenes', []).append(url)
    
    total = (1 if context.user_data.get('imagen') else 0) + len(context.user_data.get('imagenes', [])) + len(context.user_data.get('videos', []))
    keyboard = [[InlineKeyboardButton("📸 Más fotos", callback_data="mas_fotos")], [InlineKeyboardButton("🎬 Video", callback_data="mas_video")], [InlineKeyboardButton("✅ Finalizar", callback_data="finalizar_medios")]]
    await update.message.reply_text(f"📷 *Medios: {total}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAS_MEDIOS

async def finalizar_producto_callback(query, context):
    temp = context.user_data
    user = query.from_user
    producto = {
        "id": f"producto_{int(datetime.now(timezone.utc).timestamp())}",
        "nombre": temp.get("nombre", ""),
        "precio": temp.get("precio", "0"),
        "descripcion": temp.get("descripcion", ""),
        "tallas": temp.get("tallas", ""),
        "categoria": temp.get("categoria", "zapatillas"),
        "imagen": temp.get("imagen", ""),
        "imagenes": temp.get("imagenes", []),
        "videos": temp.get("videos", []),
        "fecha": datetime.now(timezone.utc).isoformat(),
        "agregado_por": user.first_name or "Admin"
    }
    productos_db[producto["id"]] = producto
    save_and_push_productos()
    total = (1 if producto['imagen'] else 0) + len(producto['imagenes']) + len(producto['videos'])
    emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
    await query.message.reply_text(f"✅ *Producto agregado*\n\n{emoji} *{producto['nombre']}*\n💰 ${format_precio(producto['precio'])}\n📷 {total} medios\n\n🌐 Visible en catálogo", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def finalizar_producto(update, context):
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
        "imagenes": temp.get("imagenes", []),
        "videos": temp.get("videos", []),
        "fecha": datetime.now(timezone.utc).isoformat(),
        "agregado_por": user.first_name or "Admin"
    }
    productos_db[producto["id"]] = producto
    save_and_push_productos()
    total = (1 if producto['imagen'] else 0) + len(producto['imagenes']) + len(producto['videos'])
    emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
    await update.message.reply_text(f"✅ *Producto agregado*\n\n{emoji} *{producto['nombre']}*\n💰 ${format_precio(producto['precio'])}\n📷 {total} medios\n\n🌐 Visible en catálogo", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def saltar(update, context):
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("📏 Paso 4/6: *Tallas* (/saltar)", parse_mode="Markdown")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [[InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")], [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]]
        await update.message.reply_text("🏷️ Paso 5/6: *Categoría*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return CATEGORIA
    context.user_data.setdefault('imagen', '')
    context.user_data.setdefault('imagenes', [])
    context.user_data.setdefault('videos', [])
    return await finalizar_producto(update, context)

async def cancelar(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado")
    return ConversationHandler.END

def main():
    missing = [v for v in ["BOT_TOKEN", "GITHUB_USER", "GITHUB_REPO", "GITHUB_TOKEN", "ADMIN_IDS"] if not os.getenv(v)]
    if missing:
        print(f"❌ Faltan: {missing}")
        return
    
    ensure_repo()
    global productos_db
    productos_db = {p.get("id", f"p_{i}"): p for i, p in enumerate(load_productos_from_disk())}
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("catalogo", catalogo))
    app.add_handler(CommandHandler("eliminar", eliminar_comando))
    app.add_handler(CallbackQueryHandler(eliminar_callback, pattern="^del_"))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion), CommandHandler("saltar", saltar)],
            TALLAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas), CommandHandler("saltar", saltar)],
            CATEGORIA: [CallbackQueryHandler(recibir_categoria, pattern="^cat_")],
            IMAGEN: [MessageHandler(filters.PHOTO, recibir_imagen), MessageHandler(filters.VIDEO, recibir_imagen), MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen), CommandHandler("saltar", saltar)],
            MAS_MEDIOS: [CallbackQueryHandler(procesar_mas_medios, pattern="^(mas_fotos|mas_video|finalizar_medios)$"), MessageHandler(filters.PHOTO, recibir_mas_medios), MessageHandler(filters.VIDEO, recibir_mas_medios), MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mas_medios), CommandHandler("saltar", saltar)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("editar", editar_comando)],
        states={
            EDITAR_CAMPO: [CallbackQueryHandler(editar_seleccionar_campo, pattern="^edit_"), CallbackQueryHandler(editar_pedir_valor, pattern="^ef_")],
            EDITAR_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, editar_guardar_valor)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    ))
    
    print(f"🤖 Bot iniciado | Admins: {ADMIN_IDS} | Productos: {len(productos_db)}")
    
    RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')
    PORT = int(os.getenv('PORT', 10000))
    
    if RENDER_URL:
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"{RENDER_URL}/{BOT_TOKEN}", drop_pending_updates=True)
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
