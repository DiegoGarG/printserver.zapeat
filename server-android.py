import subprocess
from flask import Flask, jsonify
from flask_cors import CORS
from escpos.printer import Usb

app = Flask(__name__)
CORS(app)  # Habilitar CORS para toda la aplicación

def get_connected_printer():
    """Detecta la impresora USB usando ADB desde Termux."""
    print("🔍 Ejecutando ADB para detectar dispositivos USB...")

    try:
        # Ejecutar el comando ADB para obtener la lista de dispositivos USB
        result = subprocess.run(["adb", "shell", "lsusb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Verificar si el comando se ejecutó correctamente
        if result.returncode != 0:
            print(f"❌ Error al ejecutar ADB: {result.stderr.decode()}")
            return None
        
        # Obtener la salida del comando
        output = result.stdout.decode()
        print(f"🔌 Dispositivos USB detectados:\n{output}")

        # Aquí, analicemos la salida de lsusb para encontrar la impresora
        # Debemos buscar la impresora específica en la salida del comando lsusb
        if "Impresora" in output:  # Aquí debe ir el nombre o ID de tu impresora
            print(f"✅ Impresora detectada!")
            # Dependiendo de cómo esté configurada tu impresora, intenta conectarla usando la librería escpos
            printer = Usb(0, 0, device="/dev/usb/lp0")  # Aquí se asume que la impresora está en lp0 o algo similar
            return printer
        else:
            print("❌ No se detectó ninguna impresora válida.")
            return None

    except Exception as e:
        print(f"❌ Error al intentar detectar la impresora: {e}")
        return None

# Intentar conectar la impresora automáticamente
printer = get_connected_printer()

@app.route("/open", methods=["GET", "OPTIONS"])
def open_cash_drawer():
    """Abre el cajón de dinero de la impresora."""
    if printer:
        try:
            print("🔑 Intentando abrir el cajón de dinero...")
            printer.cashdraw(2)  # Comando para abrir el cajón de dinero
            print("✅ Cajón abierto correctamente.")
            return jsonify({"status": "success", "message": "Cajón abierto"}), 200
        except Exception as e:
            print(f"❌ Error al abrir el cajón: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    print("❌ La impresora no está conectada.")
    return jsonify({"status": "error", "message": "Impresora no conectada"}), 500

@app.route("/", methods=["GET", "OPTIONS"])
def home():
    """Ruta principal para asegurarse de que el servidor esté corriendo."""
    print("🌐 El servidor está funcionando correctamente.")
    return jsonify({"status": "success", "message": "Servidor en funcionamiento"}), 200

if __name__ == "__main__":
    print("🚀 Iniciando servidor Flask...")
    # Asegurarse de que la app escuche en todas las interfaces para que Android pueda acceder a ella.
    app.run(host="0.0.0.0", port=5000, debug=True)
