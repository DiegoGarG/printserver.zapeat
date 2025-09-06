from flask import Flask, jsonify
import win32print
import win32api
import sys
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Comando ESC/POS para abrir cajón (estándar para impresoras térmicas)
OPEN_DRAWER_COMMAND = b'\x1B\x70\x00\x19\xFA'  # ESC p 0 25 250

def get_default_printer():
    """Obtiene la impresora por defecto del sistema"""
    try:
        return win32print.GetDefaultPrinter()
    except Exception as e:
        logger.error(f"Error obteniendo impresora por defecto: {e}")
        return None

def open_cash_drawer(printer_name=None):
    """
    Envía comando para abrir cajón portamonedas
    """
    try:
        # Si no se especifica impresora, usar la por defecto
        if not printer_name:
            printer_name = get_default_printer()
            if not printer_name:
                return False, "No se pudo obtener la impresora por defecto"
        
        # Abrir conexión con la impresora
        printer_handle = win32print.OpenPrinter(printer_name)
        
        # Configurar el trabajo de impresión
        job_info = ("Abrir Cajon", None, "RAW")
        job_id = win32print.StartDocPrinter(printer_handle, 1, job_info)
        
        # Iniciar página
        win32print.StartPagePrinter(printer_handle)
        
        # Enviar comando para abrir cajón
        win32print.WritePrinter(printer_handle, OPEN_DRAWER_COMMAND)
        
        # Finalizar página y documento
        win32print.EndPagePrinter(printer_handle)
        win32print.EndDocPrinter(printer_handle)
        
        # Cerrar conexión
        win32print.ClosePrinter(printer_handle)
        
        logger.info(f"Comando enviado exitosamente a {printer_name}")
        return True, "Cajón abierto exitosamente"
        
    except Exception as e:
        error_msg = f"Error abriendo cajón: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def list_printers():
    """Lista todas las impresoras disponibles en el sistema"""
    try:
        printers = []
        printer_enum = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for printer in printer_enum:
            printers.append(printer[2])  # Nombre de la impresora
        return printers
    except Exception as e:
        logger.error(f"Error listando impresoras: {e}")
        return []

@app.route('/')
def home():
    """Página principal con información"""
    printers = list_printers()
    default_printer = get_default_printer()
    
    html = f"""
    <h1>Servidor Cajón Impresora Térmica</h1>
    <p><strong>Impresora por defecto:</strong> {default_printer or 'No encontrada'}</p>
    <h3>Endpoints disponibles:</h3>
    <ul>
        <li><a href="/open">/open</a> - Abrir cajón</li>
        <li><a href="/status">/status</a> - Estado del sistema</li>
        <li><a href="/printers">/printers</a> - Lista de impresoras</li>
    </ul>
    <h3>Impresoras disponibles:</h3>
    <ul>
    """
    
    for printer in printers:
        html += f"<li>{printer}</li>"
    
    html += """
    </ul>
    <p><em>Servidor ejecutándose en http://127.0.0.1:5000</em></p>
    """
    
    return html

@app.route('/open')
def open_drawer():
    """Endpoint principal para abrir el cajón"""
    try:
        success, message = open_cash_drawer()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error inesperado: {str(e)}'
        }), 500

@app.route('/open/<printer_name>')
def open_drawer_specific(printer_name):
    """Abrir cajón en impresora específica"""
    try:
        success, message = open_cash_drawer(printer_name)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                'printer': printer_name
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message,
                'printer': printer_name
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error inesperado: {str(e)}',
            'printer': printer_name
        }), 500

@app.route('/status')
def status():
    """Estado del sistema y conexión con impresoras"""
    default_printer = get_default_printer()
    printers = list_printers()
    
    return jsonify({
        'status': 'running',
        'default_printer': default_printer,
        'available_printers': printers,
        'total_printers': len(printers)
    })

@app.route('/printers')
def printers():
    """Lista todas las impresoras disponibles"""
    printers_list = list_printers()
    
    return jsonify({
        'printers': printers_list,
        'count': len(printers_list),
        'default': get_default_printer()
    })

@app.route('/test')
def test():
    """Endpoint de prueba simple"""
    return jsonify({
        'status': 'ok',
        'message': 'Servidor funcionando correctamente'
    })

if __name__ == '__main__':
    print("=" * 50)
    print("SERVIDOR CAJÓN IMPRESORA TÉRMICA")
    print("=" * 50)
    print(f"Impresora por defecto: {get_default_printer()}")
    print(f"Impresoras disponibles: {len(list_printers())}")
    print("\nEndpoints disponibles:")
    print("- http://127.0.0.1:5000/open (Abrir cajón)")
    print("- http://127.0.0.1:5000/status (Estado)")
    print("- http://127.0.0.1:5000/printers (Lista impresoras)")
    print("=" * 50)
    
    # Ejecutar servidor
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True
    )