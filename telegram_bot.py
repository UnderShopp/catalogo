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

# Estados de conversación
NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN = range(6)
EDITAR_CAMPO, EDITAR_VALOR = range(6, 8)

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

def format_precio(precio):
    """Formatea el precio sin decimales si es entero"""
    try:
        precio_float = float(precio)
        if precio_float == int(precio_float):
            return f"{int(precio_float):,}"
        else:
            return f"{precio_float:,.2f}"
    except:
        return str(precio)

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
        f"📋 *Comandos disponibles:*\n\n"
        f"🆕 /agregar - Agregar producto\n"
        f"📋 /listar - Ver todos los productos\n"
        f"✏️ /editar - Editar un producto\n"
        f"🗑️ /eliminar - Eliminar un producto\n"
        f"🌐 /catalogo - Ver URL del catálogo\n"
        f"❓ /ayuda - Ver ayuda detallada\n\n"
        f"💡 Tienes acceso de administrador",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update, context):
    await update.message.reply_text(
        "📚 *Guía de Uso del Bot*\n\n"
        "*🆕 Agregar Producto:*\n"
        "1. Usa /agregar\n"
        "2. Sigue los pasos:\n"
        "   • Nombre del producto\n"
        "   • Precio (solo números)\n"
        "   • Descripción (opcional)\n"
        "   • Tallas disponibles (opcional)\n"
        "   • Categoría (zapatillas/ropa)\n"
        "   • Foto del producto (opcional)\n"
        "3. Usa /saltar para omitir campos opcionales\n"
        "4. Usa /cancelar para cancelar\n\n"
        "*📋 Ver Productos:*\n"
        "• /listar - Muestra todos los productos\n\n"
        "*✏️ Editar Producto:*\n"
        "1. Usa /editar\n"
        "2. Selecciona el producto\n"
        "3. Elige qué campo editar\n"
        "4. Ingresa el nuevo valor\n\n"
        "*🗑️ Eliminar Producto:*\n"
        "1. Usa /eliminar\n"
        "2. Selecciona el producto a eliminar\n"
        "3. Confirma la eliminación\n\n"
        "*🌐 Ver Catálogo Web:*\n"
        "• /catalogo - Muestra la URL de tu tienda\n\n"
        "*💡 Consejos:*\n"
        "• Las fotos mejoran las ventas\n"
        "• Descripciones claras atraen más clientes\n"
        "• Especifica todas las tallas disponibles\n"
        "• Revisa los precios antes de publicar",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update, context):
    url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO.split('/',1)[1] if '/' in GITHUB_REPO else GITHUB_REPO}/"
    await update.message.reply_text(
        f"🌐 *Catálogo Web:*\n\n"
        f"{url}\n\n"
        f"📱 Comparte este enlace con tus clientes",
        parse_mode="Markdown"
    )

@solo_admins
async def listar(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos en el catálogo")
        return
    
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    texto = f"📋 *Productos ({len(productos_ordenados)}):*\n\n"
    
    for i, p in enumerate(productos_ordenados, 1):
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        precio_fmt = format_precio(p.get('precio', '0'))
        texto += f"{i}. {cat_emoji} *{p.get('nombre')}*\n   💰 ${precio_fmt}\n"
        if p.get('tallas'):
            texto += f"   📏 Tallas: {p.get('tallas')}\n"
        texto += f"   🆔 ID: `{p.get('id')}`\n\n"
        
        # Telegram tiene límite de 4096 caracteres
        if len(texto) > 3500:
            await update.message.reply_text(texto, parse_mode="Markdown")
            texto = ""
    
    if texto:
        await update.message.reply_text(texto, parse_mode="Markdown")

@solo_admins
async def eliminar_comando(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos para eliminar")
        return
    
    # Crear botones con los productos
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    keyboard = []
    
    for p in productos_ordenados[:20]:  # Máximo 20 para no saturar
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        precio_fmt = format_precio(p.get('precio', '0'))
        texto_boton = f"{cat_emoji} {p.get('nombre')} - ${precio_fmt}"
        keyboard.append([InlineKeyboardButton(texto_boton, callback_data=f"del_{p.get('id')}")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="del_cancelar")])
    
    await update.message.reply_text(
        "🗑️ *Eliminar Producto*\n\nSelecciona el producto que deseas eliminar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def eliminar_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancelar":
        await query.edit_message_text("❌ Eliminación cancelada")
        return
    
    if query.data.startswith("del_confirm_"):
        producto_id = query.data.replace("del_confirm_", "")
        if producto_id in productos_db:
            producto = productos_db[producto_id]
            del productos_db[producto_id]
            
            if save_and_push_productos():
                cat_emoji = "👟" if producto.get("categoria") == "zapatillas" else "👕"
                await query.edit_message_text(
                    f"✅ *Producto eliminado*\n\n"
                    f"{cat_emoji} {producto.get('nombre')}\n"
                    f"💰 ${format_precio(producto.get('precio', '0'))}\n\n"
                    f"🌐 Cambios sincronizados con el catálogo web",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("⚠️ Error al guardar cambios en GitHub")
        else:
            await query.edit_message_text("❌ Producto no encontrado")
        return
    
    if query.data.startswith("del_"):
        producto_id = query.data.replace("del_", "")
        if producto_id in productos_db:
            producto = productos_db[producto_id]
            cat_emoji = "👟" if producto.get("categoria") == "zapatillas" else "👕"
            
            keyboard = [
                [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"del_confirm_{producto_id}")],
                [InlineKeyboardButton("❌ No, cancelar", callback_data="del_cancelar")]
            ]
            
            await query.edit_message_text(
                f"⚠️ *¿Confirmar eliminación?*\n\n"
                f"{cat_emoji} *{producto.get('nombre')}*\n"
                f"💰 ${format_precio(producto.get('precio', '0'))}\n"
                f"📏 Tallas: {producto.get('tallas', 'N/A')}\n\n"
                f"Esta acción no se puede deshacer.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

@solo_admins
async def editar_comando(update, context):
    if not productos_db:
        await update.message.reply_text("📭 No hay productos para editar")
        return ConversationHandler.END
    
    # Crear botones con los productos
    productos_ordenados = sorted(productos_db.values(), key=lambda x: x.get("fecha",""), reverse=True)
    keyboard = []
    
    for p in productos_ordenados[:20]:
        cat_emoji = "👟" if p.get("categoria") == "zapatillas" else "👕"
        precio_fmt = format_precio(p.get('precio', '0'))
        texto_boton = f"{cat_emoji} {p.get('nombre')} - ${precio_fmt}"
        keyboard.append([InlineKeyboardButton(texto_boton, callback_data=f"edit_{p.get('id')}")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")])
    
    await update.message.reply_text(
        "✏️ *Editar Producto*\n\nSelecciona el producto que deseas editar:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDITAR_CAMPO

async def editar_seleccionar_campo(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Edición cancelada")
        return ConversationHandler.END
    
    if query.data.startswith("edit_"):
        producto_id = query.data.replace("edit_", "")
        if producto_id in productos_db:
            context.user_data['edit_producto_id'] = producto_id
            producto = productos_db[producto_id]
            
            keyboard = [
                [InlineKeyboardButton("📝 Nombre", callback_data="editfield_nombre")],
                [InlineKeyboardButton("💰 Precio", callback_data="editfield_precio")],
                [InlineKeyboardButton("📄 Descripción", callback_data="editfield_descripcion")],
                [InlineKeyboardButton("📏 Tallas", callback_data="editfield_tallas")],
                [InlineKeyboardButton("🏷️ Categoría", callback_data="editfield_categoria")],
                [InlineKeyboardButton("📸 Imagen", callback_data="editfield_imagen")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")]
            ]
            
            cat_emoji = "👟" if producto.get("categoria") == "zapatillas" else "👕"
            await query.edit_message_text(
                f"✏️ *Editando:*\n\n"
                f"{cat_emoji} *{producto.get('nombre')}*\n"
                f"💰 ${format_precio(producto.get('precio', '0'))}\n\n"
                f"¿Qué campo deseas editar?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return EDITAR_CAMPO
    
    return ConversationHandler.END

async def editar_pedir_valor(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Edición cancelada")
        return ConversationHandler.END
    
    if query.data == "editfield_categoria":
        keyboard = [
            [InlineKeyboardButton("👟 Zapatillas", callback_data="editcat_zapatillas")],
            [InlineKeyboardButton("👕 Ropa", callback_data="editcat_ropa")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancelar")]
        ]
        await query.edit_message_text(
            "🏷️ Selecciona la nueva categoría:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDITAR_CAMPO
    
    campo = query.data.replace("editfield_", "")
    context.user_data['edit_campo'] = campo
    
    campos_nombres = {
        "nombre": "📝 Nombre",
        "precio": "💰 Precio",
        "descripcion": "📄 Descripción",
        "tallas": "📏 Tallas",
        "imagen": "📸 URL de imagen"
    }
    
    await query.edit_message_text(
        f"✏️ Ingresa el nuevo valor para {campos_nombres.get(campo, campo)}:\n\n"
        f"_(o envía /cancelar para cancelar)_",
        parse_mode="Markdown"
    )
    return EDITAR_VALOR

async def editar_guardar_valor(update, context):
    nuevo_valor = update.message.text.strip()
    producto_id = context.user_data.get('edit_producto_id')
    campo = context.user_data.get('edit_campo')
    
    if producto_id not in productos_db:
        await update.message.reply_text("❌ Producto no encontrado")
        return ConversationHandler.END
    
    # Validar precio
    if campo == "precio":
        try:
            precio_limpio = nuevo_valor.replace("$", "").replace(",", "").replace(".", "")
            precio_float = float(precio_limpio)
            nuevo_valor = f"{precio_float:.0f}"
        except:
            await update.message.reply_text("❌ Precio inválido. Edición cancelada.")
            return ConversationHandler.END
    
    # Guardar cambio
    productos_db[producto_id][campo] = nuevo_valor
    
    if save_and_push_productos():
        producto = productos_db[producto_id]
        cat_emoji = "👟" if producto.get("categoria") == "zapatillas" else "👕"
        await update.message.reply_text(
            f"✅ *Producto actualizado*\n\n"
            f"{cat_emoji} *{producto.get('nombre')}*\n"
            f"💰 ${format_precio(producto.get('precio', '0'))}\n\n"
            f"🌐 Cambios sincronizados con el catálogo web",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ Error al guardar cambios en GitHub")
    
    context.user_data.clear()
    return ConversationHandler.END

async def editar_guardar_categoria(update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancelar":
        await query.edit_message_text("❌ Edición cancelada")
        context.user_data.clear()
        return ConversationHandler.END
    
    producto_id = context.user_data.get('edit_producto_id')
    nueva_categoria = query.data.replace("editcat_", "")
    
    if producto_id in productos_db:
        productos_db[producto_id]['categoria'] = nueva_categoria
        
        if save_and_push_productos():
            producto = productos_db[producto_id]
            cat_emoji = "👟" if nueva_categoria == "zapatillas" else "👕"
            await query.edit_message_text(
                f"✅ *Producto actualizado*\n\n"
                f"{cat_emoji} *{producto.get('nombre')}*\n"
                f"💰 ${format_precio(producto.get('precio', '0'))}\n\n"
                f"🌐 Cambios sincronizados con el catálogo web",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Error al guardar cambios en GitHub")
    
    context.user_data.clear()
    return ConversationHandler.END

# AGREGAR PRODUCTO
@solo_admins
async def agregar_inicio(update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "✨ *Agregar Producto*\n\n"
        "Paso 1/6: Escribe el *nombre* del producto\n\n"
        "_(o /cancelar para cancelar)_",
        parse_mode="Markdown"
    )
    return NOMBRE

async def recibir_nombre(update, context):
    context.user_data['nombre'] = update.message.text.strip()
    await update.message.reply_text(
        "💰 Paso 2/6: Escribe el *precio*\n\n"
        "Ejemplos: 150000, 150.50, 1500",
        parse_mode="Markdown"
    )
    return PRECIO

async def recibir_precio(update, context):
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    try:
        precio = float(texto)
    except:
        await update.message.reply_text("❌ Precio inválido. Escribe solo números:")
        return PRECIO
    context.user_data['precio'] = f"{precio:.0f}"
    await update.message.reply_text(
        "📝 Paso 3/6: Escribe una *descripción*\n\n"
        "_(o /saltar para omitir)_",
        parse_mode="Markdown"
    )
    return DESCRIPCION

async def recibir_descripcion(update, context):
    context.user_data['descripcion'] = update.message.text.strip()
    await update.message.reply_text(
        "📏 Paso 4/6: ¿Qué *tallas* hay disponibles?\n\n"
        "Ejemplos: 36-42, 38,40,42, S,M,L,XL\n"
        "_(o /saltar para omitir)_",
        parse_mode="Markdown"
    )
    return TALLAS

async def recibir_tallas(update, context):
    context.user_data['tallas'] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    await update.message.reply_text(
        "🏷️ Paso 5/6: Selecciona la *categoría*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CATEGORIA

async def recibir_categoria(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data['categoria'] = query.data.replace("cat_", "")
    cat_emoji = "👟" if query.data == "cat_zapatillas" else "👕"
    await query.edit_message_text(
        f"✅ Categoría: {cat_emoji}\n\n"
        f"📸 Paso 6/6: Envía una *foto* del producto\n\n"
        f"_(o /saltar para omitir)_",
        parse_mode="Markdown"
    )
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
        await update.message.reply_text("📏 Paso 4/6: Tallas (o /saltar)")
        return TALLAS
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [
            [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
            [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
        ]
        await update.message.reply_text("🏷️ Paso 5/6: Categoría", reply_markup=InlineKeyboardMarkup(keyboard))
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
                f"✅ *Producto agregado exitosamente*\n\n"
                f"{cat_emoji} *{producto['nombre']}*\n"
                f"💰 ${format_precio(producto['precio'])}\n"
                f"📏 Tallas: {producto['tallas'] or 'N/A'}\n"
                f"👤 Por: {user.first_name}\n\n"
                f"🌐 Ya está visible en el catálogo web",
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
    
    # Cargar productos
    ensure_repo()
    global productos_db
    productos_lista = load_productos_from_disk()
    productos_db = {p.get("id", f"prod_{i}"): p for i, p in enumerate(productos_lista)}
    
    # Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Comandos básicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("catalogo", catalogo))
    app.add_handler(CommandHandler("eliminar", eliminar_comando))
    
    # Callbacks para eliminar
    app.add_handler(CallbackQueryHandler(eliminar_callback, pattern="^del_"))
    
    # Conversación para agregar producto
    conv_agregar = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            DESCRIPCION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion),
                CommandHandler("saltar", saltar)
            ],
            TALLAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas),
                CommandHandler("saltar", saltar)
            ],
            CATEGORIA: [CallbackQueryHandler(recibir_categoria, pattern="^cat_")],
            IMAGEN: [
                MessageHandler(filters.PHOTO, recibir_imagen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen),
                CommandHandler("saltar", saltar)
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    )
    
    # Conversación para editar producto
    conv_editar = ConversationHandler(
        entry_points=[CommandHandler("editar", editar_comando)],
        states={
            EDITAR_CAMPO: [
                CallbackQueryHandler(editar_seleccionar_campo, pattern="^edit_"),
                CallbackQueryHandler(editar_pedir_valor, pattern="^editfield_"),
                CallbackQueryHandler(editar_guardar_categoria, pattern="^editcat_")
            ],
            EDITAR_VALOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, editar_guardar_valor)
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    )
    
    app.add_handler(conv_agregar)
    app.add_handler(conv_editar)
    
    print("🤖 Bot iniciado")
    print(f"👥 Administradores: {ADMIN_IDS}")
    print(f"📁 Repositorio: {GITHUB_USER}/{GITHUB_REPO}")
    print(f"📦 Productos cargados: {len(productos_db)}")
    
    # Usar webhook en Render, polling en local
    RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
    PORT = int(os.getenv('PORT', 10000))
    
    if RENDER_EXTERNAL_URL:
        # Modo WEBHOOK (Render)
        print(f"🌐 Modo WEBHOOK en {RENDER_EXTERNAL_URL}")
        
        # Iniciar servidor HTTP en thread separado
        threading.Thread(target=start_health_server, daemon=True).start()
        
        # Configurar webhook
        webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        print(f"🔗 Webhook URL: {webhook_url}")
        
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url,
            drop_pending_updates=True
        )
    else:
        # Modo POLLING (desarrollo local)
        print("🔄 Modo POLLING (desarrollo local)\n")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
