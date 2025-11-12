import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados del conversation handler
NOMBRE, PRECIO, DESCRIPCION, TALLAS, IMAGEN = range(5)

# Variable para almacenar productos temporalmente
productos_temp = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de inicio"""
    await update.message.reply_text(
        "🛍️ *Bienvenido al Bot del Catálogo Premium*\n\n"
        "Comandos disponibles:\n"
        "/agregar - Agregar nuevo producto\n"
        "/listar - Ver todos los productos\n"
        "/eliminar - Eliminar un producto\n"
        "/ayuda - Ver ayuda detallada",
        parse_mode='Markdown'
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de ayuda"""
    await update.message.reply_text(
        "📚 *Guía de uso del bot*\n\n"
        "*Agregar producto:*\n"
        "1. Usa /agregar\n"
        "2. Ingresa el nombre\n"
        "3. Ingresa el precio (solo números)\n"
        "4. Ingresa la descripción\n"
        "5. Ingresa las tallas (ej: 36-42)\n"
        "6. Envía la imagen del producto\n\n"
        "*Otros comandos:*\n"
        "/listar - Ver productos actuales\n"
        "/eliminar [id] - Eliminar producto\n"
        "/cancelar - Cancelar operación actual",
        parse_mode='Markdown'
    )

async def agregar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de agregar producto"""
    await update.message.reply_text(
        "✨ *Agregar Nuevo Producto*\n\n"
        "Paso 1/5: ¿Cuál es el *nombre* del producto?\n"
        "(Envía /cancelar para cancelar)",
        parse_mode='Markdown'
    )
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre del producto"""
    user_id = update.effective_user.id
    nombre = update.message.text.strip()
    
    if not nombre:
        await update.message.reply_text("❌ El nombre no puede estar vacío. Intenta nuevamente:")
        return NOMBRE
    
    # Guardar en contexto temporal
    if user_id not in productos_temp:
        productos_temp[user_id] = {}
    productos_temp[user_id]['nombre'] = nombre
    
    await update.message.reply_text(
        f"✅ Nombre guardado: *{nombre}*\n\n"
        "Paso 2/5: ¿Cuál es el *precio* del producto?\n"
        "(Solo números, ej: 150000 o 150.50)",
        parse_mode='Markdown'
    )
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el precio del producto"""
    user_id = update.effective_user.id
    precio_text = update.message.text.strip()
    
    try:
        precio = float(precio_text.replace(',', ''))
        if precio <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Precio inválido. Debe ser un número positivo.\n"
            "Intenta nuevamente (ej: 150000 o 150.50):"
        )
        return PRECIO
    
    productos_temp[user_id]['precio'] = precio
    
    await update.message.reply_text(
        f"✅ Precio guardado: ${precio:,.2f}\n\n"
        "Paso 3/5: Escribe una *descripción* del producto\n"
        "(Puedes escribir '-' para omitir)",
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
    
    await update.message.reply_text(
        f"✅ Descripción guardada\n\n"
        "Paso 4/5: ¿Qué *tallas* están disponibles?\n"
        "(Ej: 36-42, o escribe '-' para omitir)",
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
        f"✅ Tallas guardadas: {tallas if tallas else 'No especificadas'}\n\n"
        "Paso 5/5: Envía una *foto* del producto\n"
        "(O escribe '-' para omitir)",
        parse_mode='Markdown'
    )
    return IMAGEN

async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la imagen del producto y guarda todo"""
    user_id = update.effective_user.id
    
    if update.message.photo:
        # Obtener la foto de mejor calidad
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_url = file.file_path
        productos_temp[user_id]['imagen'] = file_url
    elif update.message.text and update.message.text.strip() == '-':
        productos_temp[user_id]['imagen'] = ''
    else:
        await update.message.reply_text(
            "❌ Por favor envía una foto o '-' para omitir:"
        )
        return IMAGEN
    
    # Guardar producto en storage
    producto = productos_temp[user_id]
    producto_id = f"producto:{len(await obtener_productos()) + 1}"
    
    try:
        # Aquí deberías guardar en tu sistema de storage
        # Por ahora simulamos el guardado
        import json
        from datetime import datetime
        
        producto_data = {
            'id': producto_id,
            'nombre': producto['nombre'],
            'precio': producto['precio'],
            'descripcion': producto.get('descripcion', ''),
            'tallas': producto.get('tallas', ''),
            'imagen': producto.get('imagen', ''),
            'fecha': datetime.now().isoformat()
        }
        
        # Aquí usarías window.storage.set() en el frontend
        # Para el bot, guardamos en un archivo temporal o base de datos
        await guardar_producto(producto_data)
        
        await update.message.reply_text(
            "✅ *¡Producto agregado exitosamente!*\n\n"
            f"📦 *{producto['nombre']}*\n"
            f"💰 ${producto['precio']:,.2f}\n"
            f"📏 Tallas: {producto.get('tallas', 'N/A')}\n\n"
            "El producto ya está visible en el catálogo web.\n"
            "Usa /agregar para añadir otro producto.",
            parse_mode='Markdown'
        )
        
        # Limpiar datos temporales
        del productos_temp[user_id]
        
    except Exception as e:
        logger.error(f"Error guardando producto: {e}")
        await update.message.reply_text(
            "❌ Ocurrió un error al guardar el producto. Intenta nuevamente."
        )
    
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación actual"""
    user_id = update.effective_user.id
    if user_id in productos_temp:
        del productos_temp[user_id]
    
    await update.message.reply_text(
        "❌ Operación cancelada.\n"
        "Usa /start para ver los comandos disponibles."
    )
    return ConversationHandler.END

async def listar_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos los productos"""
    productos = await obtener_productos()
    
    if not productos:
        await update.message.reply_text(
            "📦 No hay productos en el catálogo.\n"
            "Usa /agregar para añadir el primero."
        )
        return
    
    mensaje = "📋 *Productos en el catálogo:*\n\n"
    for i, prod in enumerate(productos, 1):
        mensaje += (
            f"{i}. *{prod['nombre']}*\n"
            f"   💰 ${prod['precio']:,.2f}\n"
            f"   📏 {prod.get('tallas', 'N/A')}\n\n"
        )
    
    mensaje += f"Total: {len(productos)} productos"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def eliminar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un producto por ID"""
    if not context.args:
        await update.message.reply_text(
            "❌ Uso: /eliminar [número]\n"
            "Usa /listar para ver los números de productos."
        )
        return
    
    try:
        numero = int(context.args[0])
        productos = await obtener_productos()
        
        if numero < 1 or numero > len(productos):
            await update.message.reply_text(
                f"❌ Número inválido. Debe ser entre 1 y {len(productos)}"
            )
            return
        
        producto = productos[numero - 1]
        # Aquí eliminarías del storage
        await eliminar_producto_storage(producto['id'])
        
        await update.message.reply_text(
            f"✅ Producto *{producto['nombre']}* eliminado correctamente.",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Debes proporcionar un número válido."
        )
    except Exception as e:
        logger.error(f"Error eliminando producto: {e}")
        await update.message.reply_text(
            "❌ Error al eliminar el producto."
        )

# Funciones auxiliares (simuladas - debes implementar con tu storage real)
async def obtener_productos():
    """Obtiene todos los productos del storage"""
    # Aquí deberías implementar la lógica para leer desde tu storage
    # Por ahora retorna una lista vacía
    return []

async def guardar_producto(producto):
    """Guarda un producto en el storage"""
    # Implementar lógica de guardado
    pass

async def eliminar_producto_storage(producto_id):
    """Elimina un producto del storage"""
    # Implementar lógica de eliminación
    pass

def main():
    """Función principal"""
    # Obtener token desde variable de entorno
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ Error: TELEGRAM_BOT_TOKEN no configurado")
        return
    
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
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("listar", listar_productos))
    application.add_handler(CommandHandler("eliminar", eliminar_producto))
    
    # Iniciar bot
    logger.info("🤖 Bot iniciado correctamente")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
