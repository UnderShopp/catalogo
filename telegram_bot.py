#!/usr/bin/env python3
"""
Under Shopp Bot - Con servidor HTTP para Render.com Web Service (GRATIS)
"""
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Thread
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
from flask import Flask

# ==================== CONFIGURACIÓN ====================
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

# Estados del ConversationHandler
NOMBRE, PRECIO, DESCRIPCION, TALLAS, CATEGORIA, IMAGEN, VIDEO = range(7)

productos_db = {}

# ==================== SERVIDOR HTTP MÍNIMO ====================
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
    <head>
        <title>Under Shopp Bot</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }
            h1 { margin: 0 0 20px 0; }
            .status { 
                background: rgba(0,255,0,0.2);
                padding: 10px;
                border-radius: 8px;
                margin: 15px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Under Shopp Bot</h1>
            <div class="status">
                <strong>✅ Bot Activo</strong><br>
                📦 Productos: """ + str(len(productos_db)) + """
            </div>
            <p>Este bot está corriendo correctamente en Render.com</p>
            <p>🔗 <a href="https://t.me/""" + (BOT_TOKEN.split(':')[0] if BOT_TOKEN else '') + """" style="color: #ffd700;">Abrir en Telegram</a></p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {'status': 'ok', 'productos': len(productos_db)}, 200

# ==================== FUNCIONES GIT ====================

def repo_url_with_token():
    """URL del repo con token de autenticación"""
    return f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

def ensure_repo():
    """Clona o actualiza el repositorio"""
    try:
        if not LOCAL_REPO_PATH.exists():
            LOCAL_REPO_PATH.mkdir(parents=True, exist_ok=True)
            print("📦 Clonando repositorio...")
            subprocess.run(
                ["git", "clone", repo_url_with_token(), str(LOCAL_REPO_PATH)], 
                check=True,
                capture_output=True
            )
            print("✅ Repositorio clonado")
        else:
            print("🔄 Actualizando repositorio...")
            subprocess.run(
                ["git", "-C", str(LOCAL_REPO_PATH), "pull"], 
                check=True,
                capture_output=True
            )
            print("✅ Repositorio actualizado")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error con git: {e}")
        return False

def load_productos_from_disk():
    """Carga productos desde productos.json"""
    ruta = LOCAL_REPO_PATH / JSON_FILENAME
    if not ruta.exists():
        print("⚠️ productos.json no existe, creando vacío...")
        return {}
    
    try:
        with ruta.open("r", encoding="utf-8") as f:
            arr = json.load(f)
            if isinstance(arr, list):
                return {p.get("id", f"prod_{i}"): p for i, p in enumerate(arr)}
            elif isinstance(arr, dict):
                return arr
    except Exception as e:
        print(f"❌ Error leyendo productos.json: {e}")
    return {}

def save_and_push_productos():
    """Guarda productos y hace push a GitHub"""
    try:
        ok = ensure_repo()
        if not ok:
            return False

        ruta = LOCAL_REPO_PATH / JSON_FILENAME
        lista = list(productos_db.values())
        
        with ruta.open("w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)

        # Configurar git
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "config", "user.email", "bot@under-shopp.local"], 
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "config", "user.name", "UnderShoppBot"], 
            check=True,
            capture_output=True
        )
        
        # Add
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "add", JSON_FILENAME], 
            check=True,
            capture_output=True
        )
        
        # Verificar si hay cambios
        res = subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "status", "--porcelain"], 
            capture_output=True, 
            text=True
        )
        
        if res.stdout.strip() == "":
            print("ℹ️ No hay cambios para commitear")
            return True

        # Commit
        mensaje = f"🤖 Actualización automática - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], 
            check=True,
            capture_output=True
        )
        
        # Push
        push_cmd = ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH]
        subprocess.run(push_cmd, check=True, capture_output=True)
        
        print("✅ productos.json actualizado en GitHub")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error durante commit/push: {e}")
        return False

# ==================== FUNCIONES DE SEGURIDAD ====================

def es_admin(user_id: int) -> bool:
    """Verifica si el usuario es administrador"""
    return user_id in ADMIN_IDS

def solo_admins(func):
    """Decorador para restringir comandos solo a admins"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = user.id if user else None
        
        if not es_admin(uid):
            await update.message.reply_text(
                f"🚫 *Acceso Denegado*\n\n"
                f"Este bot es solo para administradores de Under Shopp.\n"
                f"Tu ID: `{uid}`\n\n"
                f"Contacta al propietario si necesitas acceso.",
                parse_mode="Markdown"
            )
            print(f"⚠️ Intento de acceso no autorizado - ID: {uid} - Nombre: {user.first_name}")
            return
        
        return await func(update, context)
    return wrapper

# ==================== COMANDOS BÁSICOS ====================

@solo_admins
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *Bienvenido a Under Shopp Bot*\n\n"
        f"Hola {user.first_name}!\n\n"
        f"📋 *Comandos disponibles:*\n"
        f"• /agregar → Agregar nuevo producto\n"
        f"• /listar → Ver todos los productos\n"
        f"• /catalogo → Ver URL del catálogo web\n"
        f"• /ayuda → Ayuda detallada\n\n"
        f"💡 *Formato rápido:*\n"
        f"`Nombre | Precio | URL_imagen`\n\n"
        f"Ejemplo:\n"
        f"`Nike Air Max | 250000 | https://...`",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda"""
    await update.message.reply_text(
        "📚 *Guía de Uso*\n\n"
        "*Agregar productos:*\n"
        "• /agregar → Asistente paso a paso\n"
        "• `Nombre | Precio | URL` → Formato rápido\n\n"
        "*Gestión:*\n"
        "• /listar → Ver productos actuales\n"
        "• /catalogo → Ver URL pública\n\n"
        "*Categorías:*\n"
        "• 👟 Zapatillas\n"
        "• 👕 Ropa\n\n"
        "*Multimedia:*\n"
        "• Soporta múltiples fotos\n"
        "• Puedes agregar videos\n"
        "• URLs directas o archivos",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /catalogo - muestra la URL pública"""
    repo_name = GITHUB_REPO.split('/')[-1] if '/' in GITHUB_REPO else GITHUB_REPO
    url = f"https://{GITHUB_USER}.github.io/{repo_name}/"
    
    await update.message.reply_text(
        f"🌐 *Catálogo Público*\n\n"
        f"Tu catálogo está en:\n"
        f"{url}\n\n"
        f"📱 Comparte este link con tus clientes",
        parse_mode="Markdown"
    )

@solo_admins
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /listar - muestra todos los productos"""
    if not productos_db:
        await update.message.reply_text(
            "📭 *No hay productos*\n\n"
            "Usa /agregar para agregar tu primer producto",
            parse_mode="Markdown"
        )
        return
    
    texto = f"📋 *Productos ({len(productos_db)}):*\n\n"
    
    for i, p in enumerate(sorted(productos_db.values(), key=lambda x: x.get("fecha", ""), reverse=True), 1):
        cat_icon = "👟" if p.get("categoria") == "zapatillas" else "👕"
        video_icon = " 🎥" if p.get("video") else ""
        
        img_count = 0
        if isinstance(p.get("imagen"), list):
            img_count = len(p.get("imagen"))
        elif p.get("imagen"):
            img_count = 1
        
        texto += (
            f"{i}. {cat_icon} *{p.get('nombre')}*{video_icon}\n"
            f"   💰 ${p.get('precio')} | 📷 {img_count} foto(s)\n\n"
        )
    
    await update.message.reply_text(texto, parse_mode="Markdown")

# ==================== CONVERSACIÓN AGREGAR PRODUCTO ====================

@solo_admins
async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de agregar producto"""
    context.user_data.clear()
    context.user_data['imagenes'] = []
    
    await update.message.reply_text(
        "✨ *Agregar Nuevo Producto*\n\n"
        "📝 Paso 1/7: ¿Cuál es el nombre del producto?\n\n"
        "Ejemplo: Nike Air Max 270",
        parse_mode="Markdown"
    )
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre del producto"""
    context.user_data['nombre'] = update.message.text.strip()
    
    await update.message.reply_text(
        "💰 Paso 2/7: ¿Cuál es el precio?\n\n"
        "Solo números (sin $ ni puntos)\n"
        "Ejemplo: 250000"
    )
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el precio del producto"""
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    
    try:
        precio = float(texto)
    except:
        await update.message.reply_text(
            "❌ Precio inválido\n\n"
            "Por favor ingresa solo números:\n"
            "Ejemplo: 250000"
        )
        return PRECIO
    
    context.user_data['precio'] = f"{precio:.0f}"
    
    await update.message.reply_text(
        "📝 Paso 3/7: Descripción del producto\n\n"
        "Escribe una breve descripción o /saltar"
    )
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la descripción"""
    context.user_data['descripcion'] = update.message.text.strip()
    
    await update.message.reply_text(
        "📏 Paso 4/7: Tallas disponibles\n\n"
        "Ejemplo: 36-42 o /saltar"
    )
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe las tallas"""
    context.user_data['tallas'] = update.message.text.strip()
    
    keyboard = [
        [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
        [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏷️ Paso 5/7: Selecciona la categoría:",
        reply_markup=reply_markup
    )
    return CATEGORIA

async def recibir_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la categoría seleccionada"""
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace("cat_", "")
    context.user_data['categoria'] = categoria
    
    cat_emoji = "👟" if categoria == "zapatillas" else "👕"
    
    await query.edit_message_text(
        f"✅ Categoría: {cat_emoji} {categoria.capitalize()}\n\n"
        f"📸 Paso 6/7: Envía las fotos del producto\n\n"
        f"Puedes enviar:\n"
        f"• Una o varias fotos\n"
        f"• URLs de imágenes\n\n"
        f"Cuando termines: /continuar\n"
        f"Si no tienes fotos: /saltar"
    )
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe fotos (directas o URLs)"""
    if 'imagenes' not in context.user_data:
        context.user_data['imagenes'] = []
    
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        img_url = file.file_path
        context.user_data['imagenes'].append(img_url)
        
        count = len(context.user_data['imagenes'])
        await update.message.reply_text(
            f"✅ Foto {count} guardada\n\n"
            f"Envía más fotos o /continuar"
        )
        return IMAGEN
    
    elif update.message.text and update.message.text.startswith('http'):
        img_url = update.message.text.strip()
        context.user_data['imagenes'].append(img_url)
        
        count = len(context.user_data['imagenes'])
        await update.message.reply_text(
            f"✅ URL {count} guardada\n\n"
            f"Envía más fotos o /continuar"
        )
        return IMAGEN
    
    return IMAGEN

async def continuar_a_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pasa al paso del video"""
    count = len(context.user_data.get('imagenes', []))
    
    await update.message.reply_text(
        f"📷 {count} foto(s) guardada(s)\n\n"
        f"🎥 Paso 7/7: ¿Tienes un video?\n\n"
        f"Puedes enviar:\n"
        f"• Video directo\n"
        f"• URL del video\n\n"
        f"O escribe /saltar"
    )
    return VIDEO

async def recibir_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el video"""
    video_url = ""
    
    if update.message.video:
        file = await update.message.video.get_file()
        video_url = file.file_path
    elif update.message.text and update.message.text.startswith('http'):
        video_url = update.message.text.strip()
    
    context.user_data['video'] = video_url
    return await finalizar_producto(update, context)

async def saltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salta un paso opcional"""
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text("📏 Paso 4/7: Tallas (o /saltar)")
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
    
    if 'categoria' in context.user_data and len(context.user_data.get('imagenes', [])) == 0:
        await update.message.reply_text(
            "🎥 Paso 7/7: Video (opcional) o /saltar"
        )
        return VIDEO
    
    context.user_data['video'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Operación cancelada\n\n"
        "Usa /agregar para comenzar de nuevo"
    )
    return ConversationHandler.END

async def finalizar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el producto final"""
    try:
        temp = context.user_data
        user = update.effective_user
        
        imagenes = temp.get('imagenes', [])
        if len(imagenes) == 0:
            imagen_field = ""
        elif len(imagenes) == 1:
            imagen_field = imagenes[0]
        else:
            imagen_field = imagenes
        
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": temp.get("nombre", ""),
            "precio": temp.get("precio", "0"),
            "descripcion": temp.get("descripcion", ""),
            "tallas": temp.get("tallas", ""),
            "categoria": temp.get("categoria", "zapatillas"),
            "imagen": imagen_field,
            "video": temp.get("video", ""),
            "fecha": datetime.utcnow().isoformat(),
            "agregado_por": user.first_name or "Admin"
        }
        
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        
        cat_emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
        img_count = len(imagenes)
        video_emoji = "🎥" if producto['video'] else ""
        
        if saved:
            await update.message.reply_text(
                f"✅ *Producto Agregado*\n\n"
                f"{cat_emoji} *{producto['nombre']}*\n"
                f"💰 ${producto['precio']}\n"
                f"📷 {img_count} foto(s) {video_emoji}\n"
                f"👤 Por: {user.first_name}\n\n"
                f"🌐 Ya está visible en el catálogo web",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⚠️ *Producto guardado localmente*\n\n"
                "Hubo un problema al subir a GitHub.\n"
                "Reintentando en el próximo push...",
                parse_mode="Markdown"
            )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        context.user_data.clear()
        return ConversationHandler.END

# ==================== FORMATO RÁPIDO ====================

@solo_admins
async def texto_rapido_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el formato rápido: Nombre | Precio | URL"""
    texto = update.message.text
    user = update.effective_user
    
    if "|" not in texto:
        return
    
    try:
        partes = texto.split("|")
        if len(partes) < 2:
            return
        
        nombre = partes[0].strip()
        precio = partes[1].strip().replace("$", "").replace(",", "").replace(".", "")
        imagen = partes[2].strip() if len(partes) > 2 else ""
        
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": nombre,
            "precio": precio,
            "descripcion": "",
            "tallas": "",
            "categoria": "zapatillas",
            "imagen": imagen,
            "video": "",
            "fecha": datetime.utcnow().isoformat(),
            "agregado_por": user.first_name or "Admin"
        }
        
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        
        if saved:
            await update.message.reply_text(
                f"✅ *Agregado Rápido*\n\n"
                f"👟 {nombre}\n"
                f"💰 ${precio}",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ==================== BOT EN THREAD ====================

def run_bot():
    """Ejecuta el bot en un thread separado"""
    print("="*50)
    print("🤖 UNDER SHOPP BOT")
    print("="*50)
    print(f"✅ Bot Token: Configurado")
    print(f"✅ GitHub: {GITHUB_USER}/{GITHUB_REPO}")
    print(f"👥 Admins autorizados: {len(ADMIN_IDS)}")
    print(f"🔑 IDs: {', '.join(map(str, ADMIN_IDS))}")
    print("="*50)

    print("\n📦 Preparando repositorio...")
    ensure_repo()
    
    global productos_db
    productos_db = load_productos_from_disk() or {}
    print(f"📊 Productos cargados: {len(productos_db)}")

    print("\n🚀 Iniciando bot...")
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("ayuda", ayuda))
    bot_app.add_handler(CommandHandler("listar", listar))
    bot_app.add_handler(CommandHandler("catalogo", catalogo))

    conv = ConversationHandler(
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
                CommandHandler("continuar", continuar_a_video),
                CommandHandler("saltar", saltar)
            ],
            VIDEO: [
                MessageHandler(filters.VIDEO, recibir_video),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_video),
                CommandHandler("saltar", saltar)
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    
    bot_app.add_handler(conv)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texto_rapido_handler))

    print("✅ Bot iniciado correctamente")
    print("⏳ Esperando mensajes...\n")
    
    bot_app.run_polling(drop_pending_updates=True)

# ==================== MAIN ====================

def main():
    """Función principal"""
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_USER: missing.append("GITHUB_USER")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS: missing.append("ADMIN_IDS")

    if missing:
        print(f"❌ Faltan variables de entorno: {', '.join(missing)}")
        return

    # Iniciar bot en thread separado
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar servidor Flask en el thread principal
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Servidor HTTP iniciando en puerto {port}...")
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
