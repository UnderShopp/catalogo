#!/usr/bin/env python3
import os
import json
import subprocess
import base64
from datetime import datetime, timezone
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
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
print(f"   IMGBB_API_KEY: {'✅' if IMGBB_API_KEY else '⚠️ (opcional)'}\n")

LOCAL_REPO_PATH = Path("/tmp/catalogo")
JSON_FILENAME = "productos.json"
REPO_BRANCH = "main"

# Estados de conversación
NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN, MAS_MEDIOS = range(7)
EDITAR_CAMPO, EDITAR_VALOR = range(7, 9)

productos_db = {}

# GIT FUNCTIONS
def repo_url_with_token():
    if not GITHUB_USER or not GITHUB_REPO:
        return None
    return f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"

def ensure_repo():
    try:
        repo_url = repo_url_with_token()
        if not repo_url:
            print("❌ No se puede construir URL del repositorio")
            return False
        
        if not LOCAL_REPO_PATH.exists():
            print(f"📥 Clonando repositorio desde {GITHUB_USER}/{GITHUB_REPO}...")
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", "--branch", REPO_BRANCH, repo_url, str(LOCAL_REPO_PATH)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                print(f"❌ Error clonando: {result.stderr}")
                import shutil
                if LOCAL_REPO_PATH.exists():
                    shutil.rmtree(LOCAL_REPO_PATH)
                LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
                return False
            print("✅ Repositorio clonado")
        else:
            git_dir = LOCAL_REPO_PATH / ".git"
            if not git_dir.exists():
                print("⚠️ No es un repo válido, eliminando y clonando de nuevo...")
                import shutil
                shutil.rmtree(LOCAL_REPO_PATH)
                return ensure_repo()
            
            print("🔄 Actualizando repositorio...")
            result = subprocess.run(
                ["git", "-C", str(LOCAL_REPO_PATH), "pull", "origin", REPO_BRANCH],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"⚠️ Error en pull: {result.stderr}")
                subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "fetch", "origin"], timeout=30)
                subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "reset", "--hard", f"origin/{REPO_BRANCH}"])
            else:
                print("✅ Repositorio actualizado")
        return True
    except subprocess.TimeoutExpired:
        print("❌ Timeout en operación Git")
        return False
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
        if not LOCAL_REPO_PATH.exists():
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
        
        git_dir = LOCAL_REPO_PATH / ".git"
        if not git_dir.exists():
            ok = ensure_repo()
            if not ok:
                ruta = LOCAL_REPO_PATH / JSON_FILENAME
                lista = list(productos_db.values())
                with ruta.open("w", encoding="utf-8") as f:
                    json.dump(lista, f, ensure_ascii=False, indent=2)
                return True
        
        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        print(f"📝 Escribiendo {len(lista)} productos")
        
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        print("✅ Archivo escrito")
        
        if not git_dir.exists():
            return True
        
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@undershopp.local"], capture_output=True)
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], capture_output=True)
        
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], capture_output=True)
        
        res = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], capture_output=True, text=True)
        if res.stdout.strip() == "":
            print("ℹ️ No hay cambios")
            return True
        
        mensaje = f"Bot: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], capture_output=True)
        
        repo_url = repo_url_with_token()
        if repo_url:
            result = subprocess.run(["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url, REPO_BRANCH], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print("✅ Push exitoso\n")
        return True
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return True

def format_precio(precio):
    try:
        precio_float = float(precio)
        if precio_float == int(precio_float):
            return f"{int(precio_float):,}"
        return f"{precio_float:,.2f}"
    except:
        return str(precio)

async def subir_imagen_imgbb(file_bytes, filename="producto.jpg"):
    if not IMGBB_API_KEY:
        return None
    try:
        image_base64 = base64.b64encode(file_bytes).decode('utf-8')
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY, "image": image_base64, "name": filename}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    url = data["data"]["display_url"]
                    print(f"✅ Imagen subida: {url}")
                    return url
        return None
    except Exception as e:
        print(f"❌ Error subiendo imagen: {e}")
        return None

# SECURITY
def es_admin(user_id):
    return user_id in ADMIN_IDS

def solo_admins(func):
    async def wrapper(update, context):
        user = update.effective_user
        uid = user.id if user else None
        if not es_admin(uid):
            await update.message.reply_text(f"🚫 Acceso denegado. Tu ID: {uid}")
            return
        return await func(update, context)
    return wrapper

# COMMANDS
@solo_admins
async def start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Bienvenido {user.first_name}*\n\n"
        f"📋 *Comandos:*\n\n"
        f"🆕 /agregar - Agregar producto\n"
        f"📋 /listar - Ver productos\n"
        f"✏️ /editar - Editar producto\n"
        f"🗑️ /eliminar - Eliminar producto\n"
        f"🌐 /catalogo - Ver URL\n"
        f"❓ /ayuda - Ayuda",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update, context):
    await update.message.reply_text(
        "📚 *Guía del Bot*\n\n"
        "*Agregar:* /agregar\n"
        "• Nombre, precio, descripción, tallas\n"
        "• Categoría y fotos/videos\n"
        "• Puedes agregar múltiples fotos y videos\n\n"
        "*Comandos útiles:*\n"
        "• /saltar - Omitir campo opcional\n"
        "• /cancelar - Cancelar operación",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/"
    await update.message.reply_text(f"🌐 *Catálogo:*\n\n{url}", parse_mode="Markdown")

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos")
        return
    
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    texto = f"📋 *Productos ({len(productos_ordenados)}):*\n\n"
    
    for i, p in enumerate(productos_ordenados, 1):
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        texto += f"{i}. {cat_emoji} *{p.get('nombre')}*\n   💰 ${format_precio(p.get('precio', '0'))}\n"
        
        # Contar medios
        medios = 1 if p.get('imagen') else 0
        medios += len(p.get('imagenes', []))
        medios += len(p.get('videos', []))
        if medios > 0:
            texto += f"   📷 {medios} medios\n"
        texto += "\n"
        
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
    
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    keyboard = []
    for p in productos_ordenados[:20]:
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        keyboard.append([InlineKeyboardButton(f"{cat_emoji} {p.get('nombre')}", callback_data=f"del_{p.get('id')}")])
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")])
    
    await update.message.reply_text("🗑️ *Selecciona producto:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def eliminar_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return
    
    if query.data.startswith("del_confirm_"):
        producto_id = query.data.replace("del_confirm_", "")
        if producto_id in productos_db:
            producto = productos_db[producto_id]
            del productos_db[producto_id]
            if save_and_push_productos():
                await query.edit_message_text(f"✅ *{producto.get('nombre')}* eliminado", parse_mode="Markdown")
        return
    
    if query.data.startswith("del_"):
        producto_id = query.data.replace("del_", "")
        if producto_id in productos_db:
            producto = productos_db[producto_id]
            keyboard = [
                [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"del_confirm_{producto_id}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")]
            ]
            await query.edit_message_text(
                f"⚠️ *¿Eliminar {producto.get('nombre')}?*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

@solo_admins
async def editar_comando(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos")
        return ConversationHandler.END
    
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    keyboard = []
    for p in productos_ordenados[:20]:
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        keyboard.append([InlineKeyboardButton(f"{cat_emoji} {p.get('nombre')}", callback_data=f"edit_{p.get('id')}")])
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")])
    
    await update.message.reply_text("✏️ *Selecciona producto:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return EDITAR_CAMPO

async def editar_seleccionar_campo(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return ConversationHandler.END
    
    if query.data.startswith("edit_"):
        producto_id = query.data.replace("edit_", "")
        if producto_id in productos_db:
            context.user_data['edit_producto_id'] = producto_id
            keyboard = [
                [InlineKeyboardButton("📝 Nombre", callback_data="editfield_nombre")],
                [InlineKeyboardButton("💰 Precio", callback_data="editfield_precio")],
                [InlineKeyboardButton("📄 Descripción", callback_data="editfield_descripcion")],
                [InlineKeyboardButton("📏 Tallas", callback_data="editfield_tallas")],
                [InlineKeyboardButton("🏷️ Categoría", callback_data="editfield_categoria")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")]
            ]
            await query.edit_message_text("¿Qué editar?", reply_markup=InlineKeyboardMarkup(keyboard))
            return EDITAR_CAMPO
    return ConversationHandler.END

async def editar_pedir_valor(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return ConversationHandler.END
    
    if query.data == "editfield_categoria":
        keyboard = [
            [InlineKeyboardButton("👟 Zapatillas", callback_data="editcat_zapatillas")],
            [InlineKeyboardButton("👕 Ropa", callback_data="editcat_ropa")]
        ]
        await query.edit_message_text("Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDITAR_CAMPO
    
    campo = query.data.replace("editfield_", "")
    context.user_data['edit_campo'] = campo
    await query.edit_message_text(f"Ingresa nuevo valor para {campo}:")
    return EDITAR_VALOR

async def editar_guardar_valor(update, context):
    nuevo_valor = update.message.text.strip()
    producto_id = context.user_data.get('edit_producto_id')
    campo = context.user_data.get('edit_campo')
    
    if producto_id not in productos_db:
        await update.message.reply_text("❌ Producto no encontrado")
        return ConversationHandler.END
    
    if campo == "precio":
        try:
            precio_limpio = nuevo_valor.replace("$", "").replace(",", "").replace(".", "")
            nuevo_valor = f"{float(precio_limpio):.0f}"
        except:
            await update.message.reply_text("❌ Precio inválido")
            return ConversationHandler.END
    
    productos_db[producto_id][campo] = nuevo_valor
    save_and_push_productos()
    await update.message.reply_text("✅ Actualizado")
    context.user_data.clear()
    return ConversationHandler.END

async def editar_guardar_categoria(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Cancelado")
        return ConversationHandler.END
    
    producto_id = context.user_data.get('edit_producto_id')
    nueva_categoria = query.data.replace("editcat_", "")
    
    if producto_id in productos_db:
        productos_db[producto_id]['categoria'] = nueva_categoria
        save_and_push_productos()
        await query.edit_message_text("✅ Categoría actualizada")
    
    context.user_data.clear()
    return ConversationHandler.END

# AGREGAR PRODUCTO
@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    context.user_data['imagenes'] = []
    context.user_data['videos'] = []
    await update.message.reply_text("✨ *Agregar Producto*\n\nPaso 1/6: *Nombre*", parse_mode="Markdown")
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text("💰 Paso 2/6: *Precio*", parse_mode="Markdown")
    return PRECIO

async def recibir_precio(update, context):
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido")
        return PRECIO
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text("📝 Paso 3/6: *Descripción* (o /saltar)", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_descripcion(update, context):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text("📏 Paso 4/6: *Tallas* (o /saltar)", parse_mode="Markdown")
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    await update.message.reply_text("🏷️ Paso 5/6: *Categoría*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    await query.edit_message_text(
        "📸 Paso 6/6: Envía *fotos o videos*\n\n"
        "Puedes enviar múltiples archivos.\n"
        "_(o /saltar para omitir)_",
        parse_mode="Markdown"
    )
    return IMAGEN

async def recibir_imagen(update, context):
    if 'imagenes' not in context.user_data:
        context.user_data['imagenes'] = []
    if 'videos' not in context.user_data:
        context.user_data['videos'] = []
    
    img_url = ""
    es_video = False
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        if IMGBB_API_KEY:
            try:
                await update.message.reply_text("📤 Subiendo imagen...")
                file_bytes = await file.download_as_bytearray()
                img_url = await subir_imagen_imgbb(file_bytes, f"prod_{int(datetime.now().timestamp())}.jpg")
                if img_url:
                    await update.message.reply_text("✅ Imagen subida")
            except Exception as e:
                print(f"Error: {e}")
    
    elif update.message.video:
        video = update.message.video
        file = await video.get_file()
        img_url = file.file_path
        es_video = True
        await update.message.reply_text("✅ Video agregado")
    
    elif update.message.text:
        texto = update.message.text.strip()
        if texto.startswith("http"):
            img_url = texto
            es_video = any(ext in texto.lower() for ext in ['.mp4', '.mov', '.webm'])
    
    if img_url:
        if es_video:
            context.user_data['videos'].append(img_url)
        elif not context.user_data.get('imagen'):
            context.user_data['imagen'] = img_url
        else:
            context.user_data['imagenes'].append(img_url)
    
    keyboard = [
        [InlineKeyboardButton("📸 Más fotos", callback_data="mas_fotos")],
        [InlineKeyboardButton("🎬 Agregar video", callback_data="mas_video")],
        [InlineKeyboardButton("✅ Finalizar", callback_data="finalizar_medios")]
    ]
    
    total = 1 if context.user_data.get('imagen') else 0
    total += len(context.user_data.get('imagenes', []))
    total += len(context.user_data.get('videos', []))
    
    await update.message.reply_text(
        f"📷 *Medios: {total}*\n\n¿Agregar más?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return MAS_MEDIOS

async def procesar_mas_medios(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "finalizar_medios":
        await query.edit_message_text("✅ Guardando producto...")
        return await finalizar_producto_callback(query, context)
    
    elif query.data in ["mas_fotos", "mas_video"]:
        tipo = "foto" if query.data == "mas_fotos" else "video"
        await query.edit_message_text(f"📸 Envía {tipo} (o /saltar para finalizar)")
        return MAS_MEDIOS
    
    return MAS_MEDIOS

async def recibir_mas_medios(update, context):
    img_url = ""
    es_video = False
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        if IMGBB_API_KEY:
            try:
                await update.message.reply_text("📤 Subiendo...")
                file_bytes = await file.download_as_bytearray()
                img_url = await subir_imagen_imgbb(file_bytes, f"extra_{int(datetime.now().timestamp())}.jpg")
                if img_url:
                    await update.message.reply_text("✅ Agregada")
            except:
                pass
    
    elif update.message.video:
        file = await update.message.video.get_file()
        img_url = file.file_path
        es_video = True
        await update.message.reply_text("✅ Video agregado")
    
    elif update.message.text:
        texto = update.message.text.strip()
        if texto.startswith("http"):
            img_url = texto
            es_video = any(ext in texto.lower() for ext in ['.mp4', '.mov', '.webm'])
    
    if img_url:
        if es_video:
            context.user_data.setdefault('videos', []).append(img_url)
        else:
            context.user_data.setdefault('imagenes', []).append(img_url)
    
    keyboard = [
        [InlineKeyboardButton("📸 Más fotos", callback_data="mas_fotos")],
        [InlineKeyboardButton("🎬 Agregar video", callback_data="mas_video")],
        [InlineKeyboardButton("✅ Finalizar", callback_data="finalizar_medios")]
    ]
    
    total = 1 if context.user_data.get('imagen') else 0
    total += len(context.user_data.get('imagenes', []))
    total += len(context.user_data.get('videos', []))
    
    await update.message.reply_text(f"📷 *Medios: {total}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MAS_MEDIOS

async def finalizar_producto_callback(query, context):
    try:
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
        saved = save_and_push_productos()
        
        total = 1 if producto['imagen'] else 0
        total += len(producto['imagenes']) + len(producto['videos'])
        
        if saved:
            cat_emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
            await query.message.reply_text(
                f"✅ *Producto agregado*\n\n"
                f"{cat_emoji} *{producto['nombre']}*\n"
                f"💰 ${format_precio(producto['precio'])}\n"
                f"📷 {total} medios\n\n"
                f"🌐 Visible en el catálogo",
                parse_mode="Markdown"
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")
        context.user_data.clear()
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
            "tallas": temp.get
