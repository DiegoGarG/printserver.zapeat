from flask import Flask, request, jsonify
import os
import base64
import win32print
import win32api
import time
import json

app = Flask(__name__)

# Comandos ESC/POS estándar
CUT_PAPER_COMMAND = b'\x1D\x56\x00'  # Comando de corte parcial
OPEN_DRAWER_COMMAND = b'\x1B\x70\x00\x19\xFA'  # Comando para abrir cajón

def open_drawer():
    """Abrir cajón conectado a la impresora"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Abriendo cajón en impresora: {default_printer}")
        
        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Abrir Cajon", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, OPEN_DRAWER_COMMAND)
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            print("✓ Comando de apertura enviado correctamente")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        print(f"✗ Error al abrir cajón: {e}")
        return False

def cut_paper():
    """Enviar comando de corte de papel a la impresora"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Enviando comando de corte a: {default_printer}")
        
        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Corte Papel", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, CUT_PAPER_COMMAND)
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            print("✓ Comando de corte enviado correctamente")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        print(f"✗ Error al cortar papel: {e}")
        return False

def print_text_ticket(text_content, cut_after=True):
    """Imprimir ticket de texto plano en la impresora por defecto"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Imprimiendo en: {default_printer}")
        
        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Ticket", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            
            # Codificar texto para impresora
            try:
                data = text_content.encode('cp850')
            except UnicodeEncodeError:
                data = text_content.encode('utf-8', errors='replace')
            
            # Enviar datos a la impresora
            win32print.WritePrinter(hPrinter, data)
            
            # Enviar comando de corte si está habilitado
            if cut_after:
                win32print.WritePrinter(hPrinter, CUT_PAPER_COMMAND)
                print("✓ Comando de corte enviado después de imprimir")
            
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            print("✓ Ticket impreso correctamente")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        print(f"✗ Error al imprimir ticket: {e}")
        return False
    
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
    
@app.after_request
def after_request(response):
    return add_cors_headers(response)

# Manejar peticiones OPTIONS
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    response = jsonify({'status': 'OK'})
    return add_cors_headers(response)


def print_pdf_file(pdf_path):
    """Imprimir un archivo PDF en la impresora por defecto de Windows"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Usando impresora por defecto: {default_printer}")
        win32api.ShellExecute(
            0, "printto", pdf_path, f'"{default_printer}"', ".", 0
        )
        print(f"Archivo PDF '{pdf_path}' enviado a la impresora '{default_printer}'")
        return True
    except Exception as e:
        print(f"Error al imprimir el PDF: {e}")
        return False

def save_and_print_pdf(base64_pdf_data):
    """Guardar el PDF desde base64 e imprimirlo"""
    try:
        output_dir = os.path.join(os.path.expanduser("~"), "PrintedPDFs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"ticket_{timestamp}.pdf")
        
        pdf_bytes = base64.b64decode(base64_pdf_data)
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        print(f"PDF guardado en: {pdf_path}")
        
        if not os.path.exists(pdf_path):
            print("Error: No se pudo crear el archivo PDF")
            return False
        
        result = print_pdf_file(pdf_path)
        return result
    except Exception as e:
        print(f"Error en el proceso de guardado e impresión: {e}")
        return False

@app.route('/open_drawer', methods=['POST'])
def open_cash_drawer():
    """Endpoint para abrir el cajón de la impresora"""
    try:
        success = open_drawer()
        if success:
            return jsonify({'status': 'success', 'message': 'Cajón abierto correctamente'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al abrir el cajón'}), 500
    except Exception as e:
        print(f"Error en el endpoint /open_drawer: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/cut_paper', methods=['POST'])
def cut_paper_endpoint():
    """Endpoint para cortar el papel"""
    try:
        success = cut_paper()
        if success:
            return jsonify({'status': 'success', 'message': 'Papel cortado correctamente'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al cortar el papel'}), 500
    except Exception as e:
        print(f"Error en el endpoint /cut_paper: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/print_text', methods=['POST'])
def print_text_ticket_endpoint():
    """Endpoint para imprimir tickets de texto"""
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No se encontró el texto a imprimir'}), 400
        
        text_content = data['text']
        cut_after = data.get('cut_after', True)  # Por defecto corta después de imprimir
        print(f"Texto recibido, tamaño: {len(text_content)} caracteres")
        print(f"Corte después de imprimir: {cut_after}")
        
        success = print_text_ticket(text_content, cut_after)
        if success:
            return jsonify({'status': 'success', 'message': 'Ticket impreso correctamente'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al imprimir el ticket'}), 500
    except Exception as e:
        print(f"Error en el endpoint /print_text: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/print', methods=['POST'])
def print_ticket():
    """Endpoint para recibir y imprimir tickets PDF"""
    try:
        data = request.get_json()
        if not data or 'pdf_data' not in data:
            return jsonify({'error': 'No se encontraron datos PDF'}), 400
        
        base64_pdf = data['pdf_data']
        timestamp = data.get('timestamp', time.time())
        print(f"PDF recibido, tamaño en base64: {len(base64_pdf)} caracteres")
        print(f"Timestamp: {timestamp}")
        
        success = save_and_print_pdf(base64_pdf)
        if success:
            print("✓ PDF impreso correctamente")
            return jsonify({'status': 'success', 'message': 'PDF impreso correctamente'}), 200
        else:
            print("✗ Error al imprimir el PDF")
            return jsonify({'status': 'error', 'message': 'Error al imprimir el PDF'}), 500
    except Exception as e:
        print(f"Error en el endpoint /print: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/status', methods=['GET'])
def server_status():
    """Endpoint para verificar el estado del servidor"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        return jsonify({
            'status': 'online',
            'default_printer': default_printer,
            'message': 'Servidor de impresión funcionando correctamente'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint no encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == "__main__":
    print("Iniciando servidor de impresión...")
    print("Endpoints disponibles:")
    print("  POST /open_drawer - Abrir cajón de la impresora")
    print("  POST /cut_paper - Cortar papel")
    print("  POST /print_text - Imprimir ticket de texto")
    print("  POST /print - Imprimir ticket PDF")
    print("  GET /status - Estado del servidor")
    
    app.run(
        host='0.0.0.0',
        port=12345,
        debug=True,
        threaded=True
    )