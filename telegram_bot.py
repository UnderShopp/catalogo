import os, json, random, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# ==============================
# CONFIGURACIÓN
# ==============================
TOKEN = os.getenv("BOT_TOKEN", "TU_TOKEN_AQUI")
ADMIN_IDS = [6254127927, 8092255120]
JSON_FILE = "productos.json"
PORT = int(os.getenv("PORT", 10000))

# ==============================
# LOGGING
# ==============================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def guardar_producto(producto):
    """Guarda un producto en productos.json"""
    try:
        if not os.path.exists(JSON_FILE):
            with open(JSON_FILE, "w") as f:
                json.dump([], f, indent=2)

        with open(JSON_FILE, "r") as f:
            productos = json.load(f)

        productos.append(producto)

        with open(JSON_FILE, "w") as f:
            json.dump(productos, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        logging.error(f"Error al guardar producto: {e}")
        return False


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bienvenido al catálogo UnderShopp!\nUsa /agregar para añadir un nuevo producto.")


# ==============================
# AGREGAR PRODUCTO
# ==============================
NOMBRE, PRECIO, TALLAS = range(3)

async def agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Ingresa el nombre del producto:")
    return NOMBRE

async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nombre"] = update.message.text
    await update.message.reply_text("💰 Ingresa el precio del producto:")
    return PRECIO

async def recibir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["precio"] = update.message.text
    await update.message.reply_text("📏 Ingresa las tallas disponibles (ej: 36-42):")
    return TALLAS

async def recibir_tallas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tallas"] = update.message.text

    producto = {
        "nombre": context.user_data["nombre"],
        "precio": context.user_data["precio"],
        "tallas": context.user_data["tallas"]
    }

    if guardar_producto(producto):
        await update.message.reply_text(
            f"✅ ¡Producto agregado exitosamente!\n\n"
            f"📦 {producto['nombre']}\n"
            f"💰 ${producto['precio']}\n"
            f"📏 Tallas: {producto['tallas']}\n\n"
            f"El producto ya está visible en el catálogo web.\n"
            f"Usa /agregar para añadir otro producto."
        )
    else:
        await update.message.reply_text("⚠️ Error al guardar el producto. Intenta de nuevo.")

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


# ==============================
# SERVIDOR DE SALUD (Render)
# ==============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"🩺 Servidor de salud en puerto {PORT}")


# ==============================
# MAIN
# ==============================
def main():
    print("🧩 CONFIGURACIÓN:")
    print(f"- TOKEN: {'OK' if TOKEN else '❌ Faltante'}")
    print(f"- ADMIN_IDS: {ADMIN_IDS}")

    start_health_server()

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            TALLAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tallas)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", iniciar))
    app.add_handler(conv)

    # Render usa Webhook, local usa polling
    if os.getenv("RENDER") == "true":
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
        print(f"🌐 Modo webhook activo: {webhook_url}")
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=webhook_url)
    else:
        print("💻 Modo polling local activo.")
        app.run_polling()


if __name__ == "__main__":
    main()
