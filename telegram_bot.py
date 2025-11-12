import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from git import Repo
import tempfile
import shutil

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados del conversation handler
NOMBRE, PRECIO, DESCRIPCION, TALLAS, IMAGEN = range(5)

# Archivo JSON para productos
PRODUCTOS_FILE = 'productos.json'

# Variable para almacenar productos temporalmente
productos_temp = {}

# Configuración de administradores
ADMIN_IDS = os.getenv('ADMIN_IDS', '')
ADMIN_LIST = [int(id.strip()) for id in ADMIN_IDS.split(',') if id.strip().isdigit()]

# Configuración de Git (usando las variables que ya tienes)
GITHUB_USER = os.getenv('GITHUB_USER')
GITHUB_REPO = os.getenv('GITHUB_REPO')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GIT_BRANCH = os.getenv('GIT_BRANCH', 'main')

# Construir URL del repositorio
GIT_REPO_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}.git" if GITHUB_USER and GITHUB_REPO else None

def get_repo_url_with_auth():
    """Obtiene la URL del repo con autenticación"""
    if not GIT_REPO_URL or not GITHUB_TOKEN:
        return None
    return GIT_REPO_URL.replace('https://', f'https://{GITHUB_TOKEN}@')

def push_to_github(productos):
    """Sube los cambios al repositorio GitHub"""
    try:
        repo_url = get_repo_url_with_auth()
        if not repo_url:
            logger.warning("⚠️ Git no configurado. Productos solo guardados localmente.")
            return False
        
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        
        try:
            logger.info("📥 Clonando repositorio...")
            repo = Repo.clone_from(repo_url, temp_dir, branch=GIT_BRANCH, depth=1)
            
            # Configurar usuario Git
            with repo.config_writer() as git_config:
                git_config.set_value('user', 'name', GITHUB_USER or 'Bot Telegram')
                git_config.set_value('user', 'email', f'{GITHUB_USER}@users.noreply.github.com' if GITHUB_USER else 'bot@telegram.com')
            
            # Actualizar productos.json en el repo
            productos_path = os.path.join(temp_dir, PRODUCTOS_FILE)
            with open(productos_path, 'w', encoding='utf-8') as f:
                json.dump(productos, f, ensure_ascii=False, indent=2)
            
            # Verificar si hay cambios
            if repo.is_dirty(untracked_files=True):
                # Agregar archivo
                repo.index.add([PRODUCTOS_FILE])
                
                # Commit
                commit_message = f"🤖 Actualización catálogo - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                repo.index.commit(commit_message)
                
                # Push
                origin = repo.remote('origin')
                origin.push()
                
                logger.info("✅ Cambios subidos a GitHub exitosamente")
                return True
            else:
                logger.info("ℹ️ No hay cambios para subir")
                return True
            
        except Exception as e:
            logger.error(f"❌ Error en operación Git: {e}")
            return False
            
        finally:
            # Limpiar directorio temporal
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
            
    except Exception as e:
        logger.error(f"❌ Error subiendo a GitHub: {e}")
        return False

def cargar_productos():
    """Carga productos desde el archivo JSON local"""
    try:
        if os.path.exists(PRODUCTOS_FILE):
            with open(PRODUCTOS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content or content == '[]':
                    return []
                data = json.loads(content)
                return data if isinstance(data, list) else []
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error decodificando JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Error cargando productos: {e}")
        return []

def guardar_productos(productos):
    """Guarda productos localmente y en GitHub"""
    try:
        # Guardar localmente primero
        with open(PRODUCTOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(productos, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Guardados {len(productos)} productos localmente")
        
        # Intentar subir a GitHub
        git_success = push_to_github(productos)
        
        return True
    except Exception as e:
        logger.error(f"❌ Error guardando productos: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de inicio"""
    user = update.effective_user
    
    git_status = "✅ Conectado" if GITHUB_USER and GITHUB_REPO and GITHUB_TOKEN else "⚠️ No configurado"
    
    await update.message.reply_text(
        f"🛍️ *Bienvenido al Bot del Catálogo Premium*\n\n"
        f"Hola {user.first_name}! 👋\n\n"
        f"🔗 GitHub: {git_status}\n"
        f"📁 Repo: {GITHUB_REPO or 'No configurado'}\n\n"
        "Comandos disponibles:\n"
        "🆕 /agregar - Agregar nuevo producto\n"
        "📋 /listar - Ver todos los productos\n"
        "🗑️ /eliminar - Eliminar un producto\n"
        "ℹ️ /ayuda - Ver ayuda detallada\n"
        "📊 /stats - Ver estadísticas\n"
        "🔧 /config - Ver configuración",
        parse_mode='Markdown'
    )

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la configuración actual"""
    git_configured = "✅ Sí" if GITHUB_USER and GITHUB_REPO and GITHUB_TOKEN else "❌ No"
    
    await update.message.reply_text(
        f"🔧 *Configuración del Bot*\n\n"
        f"👤 Usuario GitHub: `{GITHUB_USER or 'No configurado'}`\n"
        f"📁 Repositorio: `{GITHUB_REPO or 'No configurado'}`\n"
        f"🌿 Rama: `{GIT_BRANCH}`\n"
        f"🔗 Git configurado: {git_configured}\n\n"
        f"📝 *Variables de entorno necesarias en Render:*\n"
        f"• TELEGRAM_BOT_TOKEN ✅\n"
        f"• GITHUB_USER {'✅' if GITHUB_USER else '❌'}\n"
        f"• GITHUB_REPO {'✅' if GITHUB_REPO else '❌'}\n"
        f"• GITHUB_TOKEN {'✅' if GITHUB_TOKEN else '❌'}\n"
        f"• GIT_BRANCH (opcional, default: main)\n\n"
        f"💡 Configura las variables en:\n"
        f"Render → Tu servicio → Environment",
        parse_mode='Markdown'
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de ayuda"""
    await update.message.reply_text(
        "📚 *Guía de uso del bot*\n\n"
        "*🆕 Agregar producto:*\n"
        "1. Usa /agregar\n"
        "2. Ingresa el nombre del producto\n"
        "3. Ingresa el precio (solo números)\n"
        "4. Ingresa la descripción (o '-' para omitir)\n"
        "5. Ingresa las tallas disponibles (ej: 36-42 o '-')\n"
        "6. Envía la imagen del producto (o '-' para omitir)\n\n"
        "*📋 Otros comandos:*\n"
        "/listar - Ver todos los productos\n"
        "/eliminar [número] - Eliminar producto\n"
        "/stats - Ver estadísticas del catálogo\n"
        "/config - Ver configuración de Git\n"
        "/cancelar - Cancelar operación actual\n\n"
        "*💡 Consejos:*\n"
        "• Las imágenes mejoran la presentación\n"
        "• Usa descripciones claras y concisas\n"
        "• Especifica todas las tallas disponibles",
        parse_mode='Markdown'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas del catálogo"""
    productos = cargar_productos()
    
    if not productos:
        await update.message.reply_text(
            "📊 *Estadísticas del Catálogo*\n\n"
            "No hay productos registrados aún.",
            parse_mode='Markdown'
        )
        return
    
    total = len(productos)
    con_imagen = sum(1 for p in productos if p.get('imagen'))
    precio_promedio = sum(float(p.get('precio', 0)) for p in productos) / total
    precio_min = min(float(p.get('precio', 0)) for p in productos)
    precio_max = max(float(p.get('precio', 0)) for p in productos)
    
    await update.message.reply_text(
        f"📊 *Estadísticas del Catálogo*\n\n"
        f"📦 Total de productos: {total}\n"
        f"🖼️ Con imagen: {con_imagen}\n"
        f"💰 Precio promedio: ${precio_promedio:,.2f}\n"
        f"💵 Precio mínimo: ${precio_min:,.2f}\n"
        f"💎 Precio máximo: ${precio_max:,.2f}",
        parse_mode='Markdown'
    )

async def agregar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de agregar producto"""
    await update.message.reply_text(
        "✨ *Agregar Nuevo Producto*\n\n"
        "Paso 1/5: ¿Cuál es el *nombre* del producto?\n\n"
        "_(Envía /cancelar en cualquier momento para cancelar)_",
        parse_mode='Markdown'
    )
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre del producto"""
    user_id = update.effective_user.id
    nombre = update.message.text.strip()
    
    if not nombre or len(nombre) < 3:
        await update.message.reply_text(
            "❌ El nombre debe tener al menos 3 caracteres.\n"
            "Intenta nuevamente:"
        )
        return NOMBRE
    
    if user_id not in productos_temp:
        productos_temp[user_id] = {}
    productos_temp[user_id]['nombre'] = nombre
    
    await update.message.reply_text(
        f"✅ Nombre guardado: *{nombre}*\n\n"
        "Paso 2/5: ¿Cuál es el *precio* del producto?\n\n"
        "Ejemplos válidos:\n"
        "• 150000\n"
        "• 150.50\n"
        "• 1500",
        parse_mode='Markdown'
    )
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el precio del producto"""
    user_id = update.effective_user.id
    precio_text = update.message.text.strip()
    
    try:
        precio = float(precio_text.replace(',', '').replace('$', ''))
        if precio <= 0:
            raise ValueError("Precio debe ser positivo")
    except ValueError:
        await update.message.reply_text(
            "❌ Precio inválido. Debe ser un número positivo.\n\n"
            "Ejemplos: 150000, 150.50, 1500\n"
            "Intenta nuevamente:"
        )
        return PRECIO
    
    productos_temp[user_id]['precio'] = precio
    
    await update.message.reply_text(
        f"✅ Precio guardado: *${precio:,.2f}*\n\n"
        "Paso 3/5: Escribe una *descripción* del producto\n\n"
        "La descripción ayuda a los clientes a conocer mejor el producto.\n"
        "_(Escribe '-' para omitir)_",
        parse_mode='Markdown'
    )
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la descripción del producto"""
    user_id = update.effective_user.id
    descripcion = update.message.text.strip()
    
    if descripcion == '-':
        descripcion = ''
    
    productos_temp[user_id]['descripcion'] = descripcion
    
    desc_preview = f": {descripcion[:50]}..." if descripcion else ""
    await update.message.reply_text(
        f"✅ Descripción guardada{desc_preview}\n\n"
        "Paso 4/5: ¿Qué *tallas* están disponibles?\n\n"
        "Ejemplos:\n"
        "• 36-42\n"
        "• 38, 40, 42\n"
        "• S, M, L, XL\n"
        "_(Escribe '-' para omitir)_",
        parse_mode='Markdown'
    )
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe las tallas del producto"""
    user_id = update.effective_user.id
    tallas = update.message.text.strip()
    
    if tallas == '-':
        tallas = ''
    
    productos_temp[user_id]['tallas'] = tallas
    
    await update.message.reply_text(
        f"✅ Tallas guardadas: *{tallas if tallas else 'No especificadas'}*\n\n"
        "Paso 5/5: Envía una *foto* del producto 📸\n\n"
        "Una buena imagen aumenta las ventas.\n"
        "_(Escribe '-' para omitir)_",
        parse_mode='Markdown'
    )
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la imagen del producto y guarda todo"""
    user_id = update.effective_user.id
    
    imagen_url = ''
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        imagen_url = file.file_path
    elif update.message.text and update.message.text.strip() == '-':
        imagen_url = ''
    else:
        await update.message.reply_text(
            "❌ Por favor envía una foto o escribe '-' para omitir:"
        )
        return IMAGEN
    
    # Crear producto
    producto = productos_temp[user_id].copy()
    producto['imagen'] = imagen_url
    producto['fecha'] = datetime.now().isoformat()
    
    # Cargar productos existentes
    productos = cargar_productos()
    
    # Generar ID único
    producto_id = len(productos) + 1
    producto['id'] = str(producto_id)
    
    # Agregar nuevo producto
    productos.append(producto)
    
    # Guardar (local y GitHub)
    await update.message.reply_text("⏳ Guardando producto y sincronizando con GitHub...")
    
    if guardar_productos(productos):
        # Crear mensaje de confirmación
        mensaje = (
            "✅ *¡Producto agregado exitosamente!*\n\n"
            f"📦 *{producto['nombre']}*\n"
            f"💰 Precio: ${producto['precio']:,.2f}\n"
        )
        
        if producto.get('descripcion'):
            mensaje += f"📝 {producto['descripcion'][:100]}\n"
        
        if producto.get('tallas'):
            mensaje += f"👟 Tallas: {producto['tallas']}\n"
        
        if imagen_url:
            mensaje += "📸 Con imagen\n"
        
        mensaje += (
            f"\n🆔 ID: {producto_id}\n"
            f"📊 Total en catálogo: {len(productos)}\n\n"
        )
        
        if GITHUB_USER and GITHUB_REPO and GITHUB_TOKEN:
            mensaje += (
                "🔗 Producto sincronizado con GitHub\n"
                "🌐 Visible en tu página web en 1-2 minutos\n\n"
            )
        else:
            mensaje += "⚠️ Git no configurado - solo guardado localmente\n\n"
        
        mensaje += "Usa /agregar para añadir otro producto."
        
        await update.message.reply_text(mensaje, parse_mode='Markdown')
        
        # Limpiar datos temporales
        del productos_temp[user_id]
    else:
        await update.message.reply_text(
            "❌ Error al guardar el producto. Por favor intenta nuevamente."
        )
    
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación actual"""
    user_id = update.effective_user.id
    if user_id in productos_temp:
        del productos_temp[user_id]
    
    await update.message.reply_text(
        "❌ *Operación cancelada*\n\n"
        "Usa /start para ver los comandos disponibles.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def listar_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos los productos"""
    productos = cargar_productos()
    
    if not productos:
        await update.message.reply_text(
            "📦 *Catálogo vacío*\n\n"
            "No hay productos registrados.\n"
            "Usa /agregar para añadir el primero.",
            parse_mode='Markdown'
        )
        return
    
    # Enviar en bloques de 10
    bloques = [productos[i:i+10] for i in range(0, len(productos), 10)]
    
    for idx_bloque, bloque in enumerate(bloques):
        mensaje = f"📋 *Productos en el catálogo* (Parte {idx_bloque + 1}/{len(bloques)})\n\n"
        
        for i, prod in enumerate(bloque, idx_bloque * 10 + 1):
            mensaje += (
                f"*{i}.* {prod['nombre']}\n"
                f"   💰 ${float(prod.get('precio', 0)):,.2f}"
            )
            
            if prod.get('tallas'):
                mensaje += f" | 👟 {prod['tallas']}"
            
            if prod.get('imagen'):
                mensaje += " | 📸"
            
            mensaje += "\n\n"
        
        if idx_bloque == len(bloques) - 1:
            mensaje += f"📊 Total: *{len(productos)}* productos"
        
        await update.message.reply_text(mensaje, parse_mode='Markdown')

async def eliminar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un producto por número"""
    if not context.args:
        await update.message.reply_text(
            "❌ *Uso incorrecto*\n\n"
            "Formato: /eliminar [número]\n\n"
            "Ejemplo: /eliminar 3\n\n"
            "Usa /listar para ver los números de productos.",
            parse_mode='Markdown'
        )
        return
    
    try:
        numero = int(context.args[0])
        productos = cargar_productos()
        
        if numero < 1 or numero > len(productos):
            await update.message.reply_text(
                f"❌ Número inválido.\n\n"
                f"Debe ser entre 1 y {len(productos)}.\n"
                f"Usa /listar para ver los productos.",
                parse_mode='Markdown'
            )
            return
        
        producto_eliminado = productos.pop(numero - 1)
        
        await update.message.reply_text("⏳ Eliminando producto y sincronizando...")
        
        if guardar_productos(productos):
            mensaje = (
                f"✅ *Producto eliminado*\n\n"
                f"📦 {producto_eliminado['nombre']}\n"
                f"💰 ${float(producto_eliminado.get('precio', 0)):,.2f}\n\n"
                f"📊 Quedan {len(productos)} productos en el catálogo."
            )
            
            if GITHUB_USER and GITHUB_REPO and GITHUB_TOKEN:
                mensaje += "\n🔗 Cambios sincronizados con GitHub"
            
            await update.message.reply_text(mensaje, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "❌ Error al eliminar el producto."
            )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Debes proporcionar un número válido.\n\n"
            "Ejemplo: /eliminar 3"
        )
    except Exception as e:
        logger.error(f"Error eliminando producto: {e}")
        await update.message.reply_text(
            "❌ Error al eliminar el producto."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores"""
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado.\n"
            "Por favor intenta nuevamente."
        )

def main():
    """Función principal"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ Error: TELEGRAM_BOT_TOKEN no configurado")
        logger.info("💡 Configura el token en las variables de entorno de Render")
        return
    
    # Verificar configuración de Git
    if not GITHUB_USER or not GITHUB_REPO or not GITHUB_TOKEN:
        logger.warning("⚠️ Git no configurado completamente")
        logger.info("💡 Para sincronizar con GitHub, configura:")
        logger.info("   - GITHUB_USER: Tu usuario de GitHub")
        logger.info("   - GITHUB_REPO: Nombre del repositorio (sin .git)")
        logger.info("   - GITHUB_TOKEN: Token de acceso personal de GitHub")
        logger.info("   - GIT_BRANCH: Rama (opcional, default: main)")
        logger.info("")
        logger.info("🔑 Crear token en: https://github.com/settings/tokens")
        logger.info("   Permisos necesarios: repo (acceso completo)")
    else:
        logger.info(f"✅ Git configurado: {GITHUB_USER}/{GITHUB_REPO}")
        logger.info(f"🌿 Rama: {GIT_BRANCH}")
    
    # Inicializar archivo de productos si no existe
    if not os.path.exists(PRODUCTOS_FILE):
        guardar_productos([])
        logger.info(f"✅ Archivo {PRODUCTOS_FILE} creado")
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler para agregar productos
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('agregar', agregar_start)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion)],
            TALLAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas)],
            IMAGEN: [
                MessageHandler(filters.PHOTO, recibir_imagen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_imagen)
            ],
        },
        fallbacks=[CommandHandler('cancelar', cancelar)],
    )
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("config", config))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("listar", listar_productos))
    application.add_handler(CommandHandler("eliminar", eliminar_producto))
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    logger.info("="*50)
    logger.info("🤖 Bot de Catálogo Premium iniciado")
    logger.info("="*50)
    logger.info("✅ Bot listo para recibir comandos")
    logger.info("📱 Escribe /start en Telegram para comenzar")
    logger.info("="*50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
