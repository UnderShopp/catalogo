#!/usr/bin/env python3
"""
Under Shopp Bot - VERSIÓN CORREGIDA
Compatible con python-telegram-bot v20.7
Con flujo completo de video y manejo robusto de errores
"""
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from flask import Flask, jsonify

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

# ==================== SERVIDOR HTTP ====================
app = Flask(__name__)

@app.route('/')
def home():
    return f"""
    <html>
    <head>
        <title>Under Shopp Bot</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 700px;
                margin: 50px auto;
                padding: 30px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            .container {{
                background: rgba(255,255,255,0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            }}
            h1 {{ 
                margin: 0 0 20px 0;
                font-size: 2.5rem;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }}
            .status {{ 
                background: rgba(0,255,0,0.2);
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
                border: 2px solid rgba(0,255,0,0.4);
            }}
            .info {{
                background: rgba(255,255,255,0.05);
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
            }}
            a {{ 
                color: #ffd700;
                text-decoration: none;
                font-weight: bold;
            }}
            a:hover {{ color: #ffed4e; }}
            .emoji {{ font-size: 1.5rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Under Shopp Bot</h1>
            <div class="status">
                <strong>✅ Bot Activo y Funcionando</strong><br>
                <span class="emoji">📦</span> Productos en catálogo: <strong>{len(productos_db)}</strong>
            </div>
            <div class="info">
                <p><span class="emoji">🔧</span> <strong>Estado:</strong> Operativo</p>
                <p><span class="emoji">👥</span> <strong>Admins:</strong> {len(ADMIN_IDS)}</p>
                <p><span class="emoji">🌐</span> <strong>Repositorio:</strong> {GITHUB_USER}/{GITHUB_REPO}</p>
            </div>
            <p style="text-align: center; margin-top: 30px;">
                <a href="https://t.me/YourBotUsername" target="_blank">🚀 Abrir Bot en Telegram</a>
            </p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'productos': len(productos_db),
        'timestamp': datetime.utcnow().isoformat()
    }), 200

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
                capture_output=True,
                timeout=30
            )
            print("✅ Repositorio clonado exitosamente")
        else:
            print("🔄 Actualizando repositorio...")
            subprocess.run(
                ["git", "-C", str(LOCAL_REPO_PATH), "pull"], 
                check=True,
                capture_output=True,
                timeout=30
            )
            print("✅ Repositorio actualizado")
        return True
    except subprocess.TimeoutExpired:
        print("❌ Timeout al trabajar con git")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error con git: {e.stderr.decode() if e.stderr else str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado con git: {e}")
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
    except json.JSONDecodeError as e:
        print(f"❌ Error parseando JSON: {e}")
    except Exception as e:
        print(f"❌ Error leyendo productos.json: {e}")
    return {}

def save_and_push_productos():
    """Guarda productos y hace push a GitHub"""
    try:
        ok = ensure_repo()
        if not ok:
            print("⚠️ No se pudo actualizar el repositorio")
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
        mensaje = f"🤖 Actualización automática - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        subprocess.run(
            ["git", "-C", str(LOCAL_REPO_PATH), "commit", "-m", mensaje], 
            check=True,
            capture_output=True
        )
        
        # Push
        push_cmd = ["git", "-C", str(LOCAL_REPO_PATH), "push", repo_url_with_token(), REPO_BRANCH]
        subprocess.run(push_cmd, check=True, capture_output=True, timeout=30)
        
        print("✅ productos.json actualizado en GitHub")
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Timeout durante push a GitHub")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error durante commit/push: {e.stderr.decode() if e.stderr else str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
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
            target = update.message if update.message else update.callback_query
            if target:
                await target.reply_text(
                    f"🚫 *Acceso Denegado*\n\n"
                    f"Este bot es exclusivo para administradores de Under Shopp.\n"
                    f"Tu ID: `{uid}`\n\n"
                    f"Contacta al propietario si necesitas acceso.",
                    parse_mode="Markdown"
                )
            print(f"⚠️ Intento de acceso no autorizado - ID: {uid} - Nombre: {getattr(user, 'first_name', 'Desconocido')}")
            return
        return await func(update, context)
    return wrapper

# ==================== COMANDOS BÁSICOS ====================

@solo_admins
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 *¡Bienvenido a Under Shopp Bot!*\n\n"
        f"Hola {user.first_name}, aquí puedes gestionar tu catálogo de productos.\n\n"
        f"📋 *Comandos disponibles:*\n"
        f"• /agregar → Agregar nuevo producto (paso a paso)\n"
        f"• /listar → Ver todos los productos actuales\n"
        f"• /catalogo → Ver URL del catálogo web\n"
        f"• /ayuda → Guía de uso completa\n\n"
        f"💡 *Formato rápido:*\n"
        f"`Nombre | Precio | URL_imagen`\n\n"
        f"*Ejemplo:*\n"
        f"`Nike Air Max 270 | 250000 | https://ejemplo.com/foto.jpg`\n\n"
        f"🎥 *Nuevo:* Ahora puedes agregar videos a tus productos!",
        parse_mode="Markdown"
    )

@solo_admins
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda"""
    await update.message.reply_text(
        "📚 *Guía Completa de Uso*\n\n"
        "*🆕 Agregar productos:*\n"
        "• /agregar → Asistente interactivo paso a paso\n"
        "• `Nombre | Precio | URL` → Formato rápido\n\n"
        "*📊 Gestión:*\n"
        "• /listar → Ver catálogo completo\n"
        "• /catalogo → Obtener URL pública\n\n"
        "*🏷️ Categorías disponibles:*\n"
        "• 👟 Zapatillas\n"
        "• 👕 Ropa\n\n"
        "*📸 Multimedia soportada:*\n"
        "• Múltiples fotos por producto\n"
        "• Videos (directo o URL)\n"
        "• URLs de imágenes externas\n\n"
        "*💡 Consejos:*\n"
        "• Usa /saltar para omitir campos opcionales\n"
        "• Puedes cancelar con /cancelar en cualquier momento\n"
        "• Los cambios se sincronizan automáticamente con GitHub",
        parse_mode="Markdown"
    )

@solo_admins
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /catalogo - muestra la URL pública"""
    if not GITHUB_USER or not GITHUB_REPO:
        await update.message.reply_text(
            "⚠️ *Configuración Incompleta*\n\n"
            "Faltan variables de entorno de GitHub.",
            parse_mode="Markdown"
        )
        return
    
    repo_name = GITHUB_REPO.split('/')[-1] if '/' in GITHUB_REPO else GITHUB_REPO
    url = f"https://{GITHUB_USER}.github.io/{repo_name}/"
    
    await update.message.reply_text(
        f"🌐 *Tu Catálogo Público*\n\n"
        f"📱 URL para compartir:\n"
        f"`{url}`\n\n"
        f"💡 *Cómo usarlo:*\n"
        f"• Comparte este link con tus clientes\n"
        f"• Se actualiza automáticamente al agregar productos\n"
        f"• Funciona en móviles y computadoras\n\n"
        f"📊 Productos actuales: *{len(productos_db)}*",
        parse_mode="Markdown"
    )

@solo_admins
async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /listar - muestra todos los productos"""
    if not productos_db:
        await update.message.reply_text(
            "📭 *Catálogo Vacío*\n\n"
            "No hay productos en el catálogo.\n"
            "Usa /agregar para comenzar.",
            parse_mode="Markdown"
        )
        return
    
    texto = f"📋 *Productos en Catálogo ({len(productos_db)}):*\n\n"
    
    productos_ordenados = sorted(
        productos_db.values(), 
        key=lambda x: x.get("fecha", ""), 
        reverse=True
    )
    
    for i, p in enumerate(productos_ordenados, 1):
        cat_icon = "👟" if p.get("categoria") == "zapatillas" else "👕"
        video_icon = " 🎥" if p.get("video") else ""
        
        # Contar imágenes
        img_count = 0
        if isinstance(p.get("imagen"), list):
            img_count = len(p.get("imagen"))
        elif p.get("imagen"):
            img_count = 1
        
        precio_formateado = "{:,}".format(int(float(p.get('precio', 0)))).replace(',', '.')
        
        texto += (
            f"{i}. {cat_icon} *{p.get('nombre', 'Sin nombre')}*{video_icon}\n"
            f"   💰 ${precio_formateado} | 📷 {img_count} foto(s)\n"
        )
        
        if p.get('tallas'):
            texto += f"   📏 {p.get('tallas')}\n"
        
        texto += "\n"
    
    # Telegram tiene límite de 4096 caracteres
    if len(texto) > 4000:
        texto = texto[:4000] + "\n\n... *(lista truncada)*"
    
    await update.message.reply_text(texto, parse_mode="Markdown")

# ==================== CONVERSACIÓN AGREGAR PRODUCTO ====================

@solo_admins
async def agregar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de agregar producto"""
    context.user_data.clear()
    context.user_data['imagenes'] = []
    
    await update.message.reply_text(
        "✨ *Nuevo Producto - Paso 1/7*\n\n"
        "📝 ¿Cuál es el *nombre* del producto?\n\n"
        "*Ejemplo:*\n"
        "Nike Air Max 270 Triple Black\n\n"
        "💡 Usa /cancelar para abortar",
        parse_mode="Markdown"
    )
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre del producto"""
    nombre = update.message.text.strip()
    
    if len(nombre) < 3:
        await update.message.reply_text(
            "⚠️ El nombre debe tener al menos 3 caracteres.\n"
            "Por favor intenta de nuevo:"
        )
        return NOMBRE
    
    context.user_data['nombre'] = nombre
    
    await update.message.reply_text(
        "💰 *Paso 2/7: Precio*\n\n"
        "¿Cuál es el precio del producto?\n\n"
        "*Solo números* (sin $ ni puntos)\n\n"
        "*Ejemplos válidos:*\n"
        "• 250000\n"
        "• 150000\n"
        "• 89900",
        parse_mode="Markdown"
    )
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el precio del producto"""
    texto = update.message.text.strip().replace("$", "").replace(",", "").replace(".", "")
    
    try:
        precio = float(texto)
        if precio <= 0:
            raise ValueError("Precio debe ser positivo")
    except:
        await update.message.reply_text(
            "❌ *Precio inválido*\n\n"
            "Por favor ingresa solo números positivos:\n\n"
            "*Ejemplo correcto:*\n"
            "250000",
            parse_mode="Markdown"
        )
        return PRECIO
    
    context.user_data['precio'] = f"{precio:.0f}"
    
    await update.message.reply_text(
        "📝 *Paso 3/7: Descripción*\n\n"
        "Escribe una breve descripción del producto.\n\n"
        "*Ejemplo:*\n"
        "Zapatillas deportivas para running, suela air, máxima comodidad\n\n"
        "O escribe /saltar si no quieres agregar descripción",
        parse_mode="Markdown"
    )
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la descripción"""
    context.user_data['descripcion'] = update.message.text.strip()
    
    await update.message.reply_text(
        "📏 *Paso 4/7: Tallas*\n\n"
        "¿Qué tallas están disponibles?\n\n"
        "*Ejemplos:*\n"
        "• 36-42\n"
        "• S, M, L, XL\n"
        "• 38, 40, 42\n\n"
        "O escribe /saltar si no aplica",
        parse_mode="Markdown"
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
        "🏷️ *Paso 5/7: Categoría*\n\n"
        "Selecciona la categoría del producto:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
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
        f"✅ Categoría seleccionada: {cat_emoji} *{categoria.capitalize()}*\n\n"
        f"📸 *Paso 6/7: Fotos*\n\n"
        f"Ahora envía las fotos del producto.\n\n"
        f"Puedes enviar:\n"
        f"• Una o varias fotos (directamente)\n"
        f"• URLs de imágenes\n\n"
        f"*Cuando termines:* /continuar\n"
        f"*Sin fotos:* /saltar",
        parse_mode="Markdown"
    )
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe fotos (directas o URLs)"""
    if 'imagenes' not in context.user_data:
        context.user_data['imagenes'] = []
    
    # Recibir foto directa
    if update.message.photo:
        try:
            file = await update.message.photo[-1].get_file()
            img_url = file.file_path
            context.user_data['imagenes'].append(img_url)
            
            count = len(context.user_data['imagenes'])
            await update.message.reply_text(
                f"✅ *Foto {count} guardada*\n\n"
                f"Envía más fotos o escribe /continuar para avanzar",
                parse_mode="Markdown"
            )
            return IMAGEN
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error al procesar foto: {e}")
            return IMAGEN
    
    # Recibir URL
    elif update.message.text and update.message.text.startswith('http'):
        img_url = update.message.text.strip()
        context.user_data['imagenes'].append(img_url)
        
        count = len(context.user_data['imagenes'])
        await update.message.reply_text(
            f"✅ *URL {count} guardada*\n\n"
            f"Envía más fotos/URLs o escribe /continuar",
            parse_mode="Markdown"
        )
        return IMAGEN
    
    # Mensaje inválido
    await update.message.reply_text(
        "⚠️ Por favor envía:\n"
        "• Una foto\n"
        "• Una URL que comience con http\n"
        "• O escribe /continuar"
    )
    return IMAGEN

async def continuar_a_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pasa al paso del video"""
    count = len(context.user_data.get('imagenes', []))
    
    await update.message.reply_text(
        f"📷 *{count} foto(s) guardada(s)*\n\n"
        f"🎥 *Paso 7/7: Video (Opcional)*\n\n"
        f"¿Tienes un video del producto?\n\n"
        f"Puedes enviar:\n"
        f"• Video directo (Telegram)\n"
        f"• URL del video\n\n"
        f"*Sin video:* /saltar",
        parse_mode="Markdown"
    )
    return VIDEO

async def recibir_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el video"""
    video_url = ""
    
    # Video directo
    if update.message.video:
        try:
            file = await update.message.video.get_file()
            video_url = file.file_path
            context.user_data['video'] = video_url
            await update.message.reply_text("✅ *Video guardado*", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error al procesar video: {e}")
            return VIDEO
    
    # URL de video
    elif update.message.text and update.message.text.startswith('http'):
        video_url = update.message.text.strip()
        context.user_data['video'] = video_url
        await update.message.reply_text("✅ *URL de video guardada*", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "⚠️ Por favor envía:\n"
            "• Un video\n"
            "• Una URL que comience con http\n"
            "• O escribe /saltar"
        )
        return VIDEO
    
    return await finalizar_producto(update, context)

async def saltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salta un paso opcional"""
    # Saltar descripción
    if 'descripcion' not in context.user_data:
        context.user_data['descripcion'] = ""
        await update.message.reply_text(
            "📏 *Paso 4/7: Tallas*\n\n"
            "¿Qué tallas disponibles? (o /saltar)",
            parse_mode="Markdown"
        )
        return TALLAS
    
    # Saltar tallas
    if 'tallas' not in context.user_data:
        context.user_data['tallas'] = ""
        keyboard = [
            [InlineKeyboardButton("👟 Zapatillas", callback_data="cat_zapatillas")],
            [InlineKeyboardButton("👕 Ropa", callback_data="cat_ropa")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🏷️ *Paso 5/7: Categoría*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return CATEGORIA
    
    # Saltar fotos (ir a video)
    if 'categoria' in context.user_data and 'video' not in context.user_data:
        await update.message.reply_text(
            "🎥 *Paso 7/7: Video*\n\n"
            "¿Tienes un video? (opcional)\n"
            "O escribe /saltar nuevamente",
            parse_mode="Markdown"
        )
        return VIDEO
    
    # Saltar video (finalizar)
    context.user_data['video'] = ""
    return await finalizar_producto(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ *Operación Cancelada*\n\n"
        "El producto no fue agregado.\n"
        "Usa /agregar para comenzar de nuevo.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def finalizar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el producto final"""
    try:
        temp = context.user_data
        user = update.effective_user
        
        # Procesar imágenes
        imagenes = temp.get('imagenes', [])
        if len(imagenes) == 0:
            imagen_field = ""
        elif len(imagenes) == 1:
            imagen_field = imagenes[0]
        else:
            imagen_field = imagenes
        
        # Crear producto
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
        
        # Guardar y pushear
        productos_db[producto["id"]] = producto
        saved = save_and_push_productos()
        
        # Preparar mensaje de confirmación
        cat_emoji = "👟" if producto['categoria'] == "zapatillas" else "👕"
        img_count = len(imagenes)
        video_emoji = "🎥" if producto['video'] else ""
        precio_formateado = "{:,}".format(int(float(producto['precio']))).replace(',', '.')
        
        if saved:
            mensaje = (
                f"✅ *¡Producto Agregado Exitosamente!*\n\n"
                f"{cat_emoji} *{producto['nombre']}* {video_emoji}\n"
                f"💰 Precio: ${precio_formateado}\n"
                f"📷 Fotos: {img_count}\n"
                f"👤 Agregado por: {user.first_name}\n\n"
                f"🌐 *Ya está visible en tu catálogo web*\n"
                f"📊 Total de productos: {len(productos_db)}"
            )
        else:
            mensaje = (
                f"⚠️ *Producto Guardado Localmente*\n\n"
                f"{cat_emoji} {producto['nombre']}\n\n"
                f"Hubo un problema al sincronizar con GitHub.\n"
                f"Se reintentará automáticamente."
            )
        
        await update.message.reply_text(mensaje, parse_mode="Markdown")
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        print(f"❌ Error al finalizar producto: {e}")
        await update.message.reply_text(
            f"❌ *Error Inesperado*\n\n"
            f"No se pudo guardar el producto.\n"
            f"Detalles: `{str(e)}`\n\n"
            f"Por favor intenta nuevamente con /agregar",
            parse_mode="Markdown"
        )
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
        
        # Validar precio
        try:
            precio_num = float(precio)
            if precio_num <= 0:
                raise ValueError()
        except:
            await update.message.reply_text(
                "❌ Precio inválido en formato rápido\n\n"
                "Usa: `Nombre | 250000 | URL`",
                parse_mode="Markdown"
            )
            return
        
        producto = {
            "id": f"producto_{int(datetime.utcnow().timestamp())}",
            "nombre": nombre,
            "precio": f"{precio_num:.0f}",
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
        
        precio_formateado = "{:,}".format(int(precio_num)).replace(',', '.')
        
        if saved:
            await update.message.reply_text(
                f"⚡ *Agregado Rápido Exitoso*\n\n"
                f"👟 {nombre}\n"
                f"💰 ${precio_formateado}\n\n"
                f"✅ Sincronizado con GitHub",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"⚡ *Agregado Rápido (Local)*\n\n"
                f"👟 {nombre}\n"
                f"💰 ${precio_formateado}\n\n"
                f"⚠️ Pendiente de sincronización",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        print(f"❌ Error en formato rápido: {e}")
        await update.message.reply_text(
            f"❌ Error al procesar formato rápido\n\n"
            f"Formato correcto:\n"
            f"`Nombre | Precio | URL`",
            parse_mode="Markdown"
        )

# ==================== MANEJO DE ERRORES ====================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores globales del bot"""
    print(f"❌ Error capturado: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Ocurrió un error inesperado.\n"
                "Por favor intenta de nuevo o contacta al administrador."
            )
        except:
            pass

# ==================== INICIALIZACIÓN DEL BOT ====================

def run_bot():
    """Ejecuta el bot en un thread separado"""
    print("="*60)
    print("🤖 UNDER SHOPP BOT - VERSIÓN CORREGIDA")
    print("="*60)
    print(f"✅ Bot Token: {'✓ Configurado' if BOT_TOKEN else '✗ FALTA'}")
    print(f"✅ GitHub User: {GITHUB_USER or '✗ FALTA'}")
    print(f"✅ GitHub Repo: {GITHUB_REPO or '✗ FALTA'}")
    print(f"✅ GitHub Token: {'✓ Configurado' if GITHUB_TOKEN else '✗ FALTA'}")
    print(f"👥 Administradores: {len(ADMIN_IDS)}")
    if ADMIN_IDS:
        print(f"🔑 IDs autorizados: {', '.join(map(str, ADMIN_IDS))}")
    print("="*60)

    # Preparar repositorio
    print("\n📦 Preparando repositorio Git...")
    if ensure_repo():
        print("✅ Repositorio listo")
    else:
        print("⚠️ Advertencia: No se pudo preparar el repositorio")
    
    # Cargar productos
    global productos_db
    productos_db = load_productos_from_disk() or {}
    print(f"📊 Productos cargados: {len(productos_db)}")

    # Construir aplicación
    print("\n🚀 Construyendo aplicación del bot...")
    try:
        bot_app = Application.builder().token(BOT_TOKEN).build()
        print("✅ Aplicación construida exitosamente")
    except Exception as e:
        print(f"❌ Error construyendo aplicación: {e}")
        return

    # Registrar handlers
    print("📝 Registrando comandos...")
    
    # Comandos básicos
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("ayuda", ayuda))
    bot_app.add_handler(CommandHandler("listar", listar))
    bot_app.add_handler(CommandHandler("catalogo", catalogo))

    # Conversación para agregar productos
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_inicio)],
        states={
            NOMBRE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)
            ],
            PRECIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)
            ],
            DESCRIPCION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion),
                CommandHandler("saltar", saltar)
            ],
            TALLAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas),
                CommandHandler("saltar", saltar)
            ],
            CATEGORIA: [
                CallbackQueryHandler(recibir_categoria, pattern="^cat_")
            ],
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
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_user=True,
        per_chat=True,
        allow_reentry=True
    )
    
    bot_app.add_handler(conv_handler)
    
    # Formato rápido
    bot_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, texto_rapido_handler)
    )
    
    # Error handler
    bot_app.add_error_handler(error_handler)

    print("✅ Todos los handlers registrados")
    print("\n🎉 Bot iniciado correctamente")
    print("⏳ Esperando mensajes de usuarios autorizados...\n")
    
    # Iniciar polling
    bot_app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

# ==================== PUNTO DE ENTRADA ====================

def main():
    """Función principal"""
    # Verificar variables de entorno requeridas
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GITHUB_USER:
        missing.append("GITHUB_USER")
    if not GITHUB_REPO:
        missing.append("GITHUB_REPO")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not ADMIN_IDS:
        missing.append("ADMIN_IDS")

    if missing:
        print("="*60)
        print("❌ ERROR: CONFIGURACIÓN INCOMPLETA")
        print("="*60)
        print(f"Faltan las siguientes variables de entorno:")
        for var in missing:
            print(f"  • {var}")
        print("\nPor favor configura estas variables en Render.com")
        print("="*60)
        return

    # Iniciar bot en thread daemon
    print("🚀 Iniciando Under Shopp Bot...\n")
    bot_thread = Thread(target=run_bot, daemon=True, name="BotThread")
    bot_thread.start()
    
    # Iniciar servidor HTTP
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Servidor HTTP iniciando en puerto {port}...")
    print(f"📍 Accesible en: http://0.0.0.0:{port}")
    print("="*60)
    
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except KeyboardInterrupt:
        print("\n\n👋 Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error en servidor HTTP: {e}")

if __name__ == "__main__":
    main()
