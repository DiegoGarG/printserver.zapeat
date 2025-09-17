from flask import Flask, request, jsonify
import os
import base64
import win32print
import win32api
import time
import json
import threading
import queue
import argparse
import sys

import fitz  # PyMuPDF (pip install pymupdf)
from PIL import Image
import io

app = Flask(__name__)
#python servidor_impresion.py --origin https://testapp.zapeat.es --port 5000

# Variable global para la URL permitida en CORS
ALLOWED_ORIGIN = 'https://app.zapeat.es'  # Valor por defecto

# Comandos ESC/POS estándar
CUT_PAPER_COMMAND = b'\x1D\x56\x00'  # Corte parcial
OPEN_DRAWER_COMMAND = b'\x1B\x70\x00\x19\xFA'  # Abrir cajón

# Cola y sincronización
print_queue = queue.Queue()
print_thread_running = False
print_lock = threading.Lock()


def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    # NUEVO: Header requerido para peticiones a redes privadas
    response.headers.add('Access-Control-Allow-Private-Network', 'true')
    return response

# También agregar el manejo explícito de OPTIONS
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_preflight(path=''):
    response = jsonify({'status': 'preflight ok'})
    return add_cors_headers(response)

@app.after_request
def after_request(response):
    return add_cors_headers(response)

# --- Utilidades de impresión en RAW (ESC/POS) ---

def get_default_printer_name():
    try:
        return win32print.GetDefaultPrinter()
    except Exception as e:
        print(f"Error obteniendo impresora por defecto: {e}")
        return None


def print_raw(data: bytes) -> bool:
    """Enviar bytes RAW directamente a la impresora por defecto usando Win32 API.
    Esto evita que Windows reinterprete el documento y agrega márgenes de página.
    """
    try:
        default_printer = get_default_printer_name()
        if not default_printer:
            print("✗ No hay impresora por defecto configurada")
            return False

        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            # El tercer parámetro especifica que enviaremos datos en RAW
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Python RAW Print", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, data)
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            print(f"✓ Enviados {len(data)} bytes RAW a '{default_printer}'")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        print(f"✗ Error enviando RAW a la impresora: {e}")
        return False


def safe_encode_text(text: str) -> bytes:
    """Codificar texto de manera segura para impresoras térmicas.
    Intenta múltiples codificaciones y reemplaza caracteres problemáticos.
    """
    if text is None:
        text = ""
    
    # Reemplazar caracteres problemáticos comunes
    char_replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N',
        'ü': 'u', 'Ü': 'U',
        '€': 'EUR',
        '°': 'º',
        '¿': '?',
        '¡': '!',
        '"': '"', '"': '"',
        ''': "'", ''': "'",
        '–': '-', '—': '-',
        '…': '...',
    }
    
    # Aplicar reemplazos
    for original, replacement in char_replacements.items():
        text = text.replace(original, replacement)
    
    # Lista de codificaciones a probar en orden de preferencia
    encodings_to_try = [
        'cp850',    # Code page 850 (Latin-1 con caracteres de caja)
        'cp437',    # Code page 437 (ASCII extendido)
        'iso-8859-1',  # Latin-1
        'cp1252',   # Windows-1252
        'ascii',    # ASCII puro (último recurso)
    ]
    
    for encoding in encodings_to_try:
        try:
            encoded = text.encode(encoding, errors='replace')
            print(f"✓ Texto codificado exitosamente con {encoding}")
            return encoded
        except Exception as e:
            print(f"✗ Fallo codificación {encoding}: {e}")
            continue
    
    # Si todas las codificaciones fallan, usar ASCII con reemplazo agresivo
    print("⚠️ Usando codificación ASCII con reemplazo de caracteres")
    return text.encode('ascii', errors='replace')


def create_qr_raster_data(qr_base64: str, target_width_mm: int = 35) -> bytes:
    """Convertir imagen QR en base64 a datos raster ESC/POS con tamaño exacto de 35mm x 35mm."""
    try:
        # Decodificar imagen base64
        qr_bytes = base64.b64decode(qr_base64)
        qr_img = Image.open(io.BytesIO(qr_bytes))
        
        print(f"QR original: {qr_img.size[0]}x{qr_img.size[1]} pixels")
        
        # Convertir a escala de grises
        gray = qr_img.convert('L')
        
        # Cálculo preciso para 35mm en impresoras térmicas
        # La mayoría de impresoras térmicas POS tienen ~203 DPI (8 dots per mm)
        # 35mm = 35 * 8 = 280 pixels aproximadamente
        # Usar múltiplo de 8 para facilitar el procesamiento raster
        target_pixels = 280  # 35mm * 8 dots/mm = exactamente 35mm
        
        print(f"Redimensionando QR a {target_pixels}x{target_pixels} pixels (35mm x 35mm)")
        
        # Redimensionar manteniendo aspecto cuadrado y usando NEAREST para mantener definición
        gray = gray.resize((target_pixels, target_pixels), Image.Resampling.NEAREST)
        
        # Binarizar con threshold optimizado para QR
        threshold = 128
        bw = gray.point(lambda x: 0 if x < threshold else 255, '1')
        
        # Verificar que el ancho sea múltiplo de 8 (requisito ESC/POS)
        w, h = bw.size
        width_bytes = (w + 7) // 8
        padded_w = width_bytes * 8
        
        print(f"Dimensiones finales: {w}x{h} pixels, {width_bytes} bytes por línea")
        
        if padded_w != w:
            print(f"Añadiendo padding: {padded_w - w} pixels")
            new = Image.new('1', (padded_w, h), 1)  # fondo blanco
            new.paste(bw, (0, 0))
            bw = new
            w = padded_w
        
        # Convertir a datos raster ESC/POS
        pixels = bw.load()
        raster_data = bytearray()
        
        for y in range(h):
            for xb in range(width_bytes):
                byte = 0
                for bit in range(8):
                    x = xb * 8 + bit
                    if x < w:
                        pixel = pixels[x, y]
                        # En modo '1', pixel == 0 => negro, pixel == 255 => blanco
                        # Para ESC/POS: 1 = negro, 0 = blanco
                        bit_val = 1 if pixel == 0 else 0
                    else:
                        bit_val = 0  # padding blanco
                    byte = (byte << 1) | bit_val
                raster_data.append(byte)
        
        # Crear comando ESC/POS raster: GS v 0 m xL xH yL yH
        GS = b'\x1D'
        m = 0  # modo normal
        xL = width_bytes & 0xFF
        xH = (width_bytes >> 8) & 0xFF
        yL = h & 0xFF
        yH = (h >> 8) & 0xFF
        
        header = GS + b'v' + b'0' + bytes([m, xL, xH, yL, yH])
        
        print(f"Header ESC/POS: GS v 0 {m} {xL} {xH} {yL} {yH}")
        print(f"Datos raster generados: {len(raster_data)} bytes")
        
        return header + raster_data
    
    except Exception as e:
        print(f"✗ Error procesando QR: {e}")
        import traceback
        traceback.print_exc()
        return b''


def build_escpos_from_text(text: str, cut_after: bool = True, qr_base64: str = '') -> bytes:
    """Construir bytes ESC/POS a partir de texto plano con codificación segura y QR opcional."""
    
    # Normalizar saltos de línea y eliminar espacios iniciales/finales
    if text is None:
        text = ""
    
    # Reemplazar CRLF por LF
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Strip for leading/trailing blank lines
    lines = [line.rstrip() for line in text.split('\n')]
    
    # Remove leading blank lines
    while len(lines) and lines[0].strip() == '':
        lines.pop(0)
    
    # Remove trailing blank lines
    while len(lines) and lines[-1].strip() == '':
        lines.pop()

    body_text = '\n'.join(lines)

    # ESC/POS sequences
    ESC = b'\x1B'
    GS = b'\x1D'
    init = ESC + b'@'  # Inicializar impresora
    # Reducir espaciado de líneas
    set_line_spacing = ESC + b'3' + bytes([24])
    # Comando para centrar
    center_align = ESC + b'a' + b'\x01'
    # Comando para alineación izquierda
    left_align = ESC + b'a' + b'\x00'

    out = bytearray()
    out += init
    out += set_line_spacing

    # Si hay QR, imprimirlo primero centrado
    if qr_base64:
        qr_raster = create_qr_raster_data(qr_base64)
        if qr_raster:
            # Centrar y imprimir QR
            out += center_align
            out += safe_encode_text("QR Tributario:\n")
            out += ESC + b'd' + bytes([1])  
            out += qr_raster
            out += safe_encode_text("\nVERI*FACTU\n")
            out += ESC + b'd' + bytes([3])  # Espaciado después del QR
            # Volver a alineación izquierda
            out += left_align

    # Asegurar que haya al menos una nueva línea al final
    if not body_text.endswith('\n'):
        body_text += '\n'

    # Codificar de manera segura
    try:
        body_bytes = safe_encode_text(body_text)
    except Exception as e:
        print(f"✗ Error en codificación segura: {e}")
        body_bytes = body_text.encode('ascii', errors='replace')

    out += body_bytes

    # Añadir avance de papel antes del corte
    out += ESC + b'd' + bytes([16])  # ESC d n -> avanzar n líneas

    if cut_after:
        out += CUT_PAPER_COMMAND

    return bytes(out)


# --- Función de impresión de texto que evita márgenes ---

def print_text_ticket(text: str, cut_after: bool = True, qr_base64: str = '') -> bool:
    """Construir y enviar un ticket de texto a la impresora en RAW (ESC/POS) con QR opcional."""
    try:
        print(f"📝 Preparando impresión de texto ({len(text)} caracteres)")
        if qr_base64:
            print(f"🖼️ Incluyendo QR ({len(qr_base64)} caracteres base64)")
        
        data = build_escpos_from_text(text, cut_after=cut_after, qr_base64=qr_base64)
        print(f"📤 Enviando {len(data)} bytes a impresora")
        return print_raw(data)
    except Exception as e:
        print(f"✗ Error en print_text_ticket: {e}")
        return False


# --- Mantengo las funciones de cajón y corte usando RAW también ---

def open_drawer():
    try:
        print(f"Abriendo cajón en impresora: {get_default_printer_name()}")
        return print_raw(OPEN_DRAWER_COMMAND)
    except Exception as e:
        print(f"✗ Error al abrir cajón: {e}")
        return False


def cut_paper():
    try:
        print(f"Enviando comando de corte a: {get_default_printer_name()}")
        return print_raw(CUT_PAPER_COMMAND)
    except Exception as e:
        print(f"✗ Error al cortar papel: {e}")
        return False


def print_pdf_file(pdf_path: str) -> bool:
    """Convertir cada página del PDF a imagen y enviarla como ESC/POS raster (GS v 0)."""
    try:
        doc = fitz.open(pdf_path)
        for p in range(len(doc)):
            page = doc.load_page(p)
            # Zoom >1 para mayor resolución; ajustar si la calidad es baja/alta
            mat = fitz.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Convertir a escala de grises y binarizar (threshold)
            gray = img.convert('L')
            threshold = 128
            bw = gray.point(lambda x: 0 if x < threshold else 255, '1')

            # Asegurar que el ancho sea múltiplo de 8 (padding a la derecha)
            w, h = bw.size
            width_bytes = (w + 7) // 8
            padded_w = width_bytes * 8
            if padded_w != w:
                new = Image.new('1', (padded_w, h), 1)  # fondo blanco
                new.paste(bw, (0, 0))
                bw = new
                w = padded_w

            # Construir los bytes raster: cada byte = 8 píxeles horizontales (MSB primero)
            pixels = bw.load()
            data = bytearray()
            for y in range(h):
                for xb in range(width_bytes):
                    byte = 0
                    for bit in range(8):
                        x = xb * 8 + bit
                        pixel = pixels[x, y]
                        # En modo '1', pixel == 0 => negro, pixel == 255 => blanco
                        bit_val = 1 if pixel == 0 else 0
                        byte = (byte << 1) | bit_val
                    data.append(byte)

            # Cabecera ESC/POS raster: GS v 0 m xL xH yL yH
            ESC = b'\x1B'
            GS = b'\x1D'
            m = 0
            xL = width_bytes & 0xFF
            xH = (width_bytes >> 8) & 0xFF
            yL = h & 0xFF
            yH = (h >> 8) & 0xFF
            header = GS + b'v' + b'0' + bytes([m, xL, xH, yL, yH])

            escpos = bytearray()
            escpos += header
            escpos += data

            # MEJORA: Añadir más avance y cortar al final con mejor espaciado
            escpos += ESC + b'd' + bytes([6])  # Aumentado el avance para PDFs también
            if p == len(doc) - 1:
                escpos += CUT_PAPER_COMMAND

            ok = print_raw(bytes(escpos))
            if not ok:
                print(f"✗ Error enviando página {p} del PDF como ESC/POS raster")
                return False

        return True
    except Exception as e:
        print(f"✗ Error en print_pdf_file (raster): {e}")
        return False

# --- Endpoints ---
@app.route('/open_drawer', methods=['POST'])
def open_cash_drawer():
    try:
        job_success = add_print_job({'type': 'drawer'})
        if job_success:
            return jsonify({'status': 'success', 'message': 'Comando de cajón añadido a cola'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir comando a cola'}), 500
    except Exception as e:
        print(f"Error en /open_drawer: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/cut_paper', methods=['POST'])
def cut_paper_endpoint():
    try:
        success = cut_paper()
        if success:
            return jsonify({'status': 'success', 'message': 'Papel cortado correctamente'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al cortar el papel'}), 500
    except Exception as e:
        print(f"Error en /cut_paper: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/print_text', methods=['POST'])
def print_text_ticket_endpoint():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No se encontró el texto a imprimir'}), 400

        print(f"📥 Recibida petición de impresión de texto")
        print(f"📝 Longitud del texto: {len(data['text'])} caracteres")
        
        # Obtener QR si está presente
        qr_base64 = data.get('qr_data', '')
        if qr_base64:
            print(f"🖼️ QR recibido ({len(qr_base64)} caracteres)")
        
        # Debug: mostrar primeras líneas del texto
        lines = data['text'].split('\n')[:5]
        for i, line in enumerate(lines):
            print(f"   Línea {i+1}: '{line}'")

        job_success = add_print_job({
            'type': 'text',
            'text': data['text'],
            'cut_after': data.get('cut_after', True),
            'qr_data': qr_base64
        })

        if job_success:
            return jsonify({'status': 'success', 'message': 'Texto añadido a cola de impresión'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir texto a cola'}), 500
    except Exception as e:
        print(f"Error en /print_text: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/print', methods=['POST'])
def print_ticket():
    """Endpoint para recibir y (opcionalmente) imprimir PDFs."""
    try:
        data = request.get_json()
        if not data or 'pdf_data' not in data:
            return jsonify({'error': 'No se encontraron datos PDF'}), 400

        base64_pdf = data['pdf_data']

        # Guardar PDF temporalmente
        output_dir = os.path.join(os.path.expanduser("~"), "PrintedPDFs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"ticket_{timestamp_str}.pdf")

        pdf_bytes = base64.b64decode(base64_pdf)
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        # Añadir a cola de impresión (fallback PDF)
        job_success = add_print_job({
            'type': 'pdf',
            'path': pdf_path
        })

        if job_success:
            return jsonify({'status': 'success', 'message': 'PDF añadido a cola de impresión (fallback)'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir PDF a cola'}), 500

    except Exception as e:
        print(f"Error en /print: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/status', methods=['GET'])
def server_status():
    try:
        default_printer = get_default_printer_name()
        return jsonify({
            'status': 'online',
            'default_printer': default_printer,
            'allowed_origin': ALLOWED_ORIGIN,
            'message': 'Servidor de impresión funcionando correctamente (modo RAW para tickets)'
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500


@app.route('/clear_queue', methods=['POST'])
def clear_queue_endpoint():
    try:
        success = clear_print_queue()
        if success:
            return jsonify({'status': 'success', 'message': 'Cola de impresión limpiada'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al limpiar cola'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/test_print', methods=['POST'])
def test_print_endpoint():
    """Endpoint de prueba para verificar codificación."""
    test_text = """========================================
           TICKET DE PRUEBA
========================================

Restaurante Ejemplo
Calle Principal 123
CIF: B12345678
----------------------------------------
Fecha: 16/09/2025        Hora: 14:30
Ticket: TEST001
----------------------------------------
DESCRIPCION          CANT   PRECIO    TOTAL
----------------------------------------
Hamburguesa            x1     8.50     8.50
Patatas Fritas         x1     3.00     3.00
Coca Cola              x2     2.50     5.00
----------------------------------------
Base Imponible                      15.00
IVA (10%)                            1.50
----------------------------------------
TOTAL                               16.50
========================================

        Gracias por su visita
     Este ticket es su comprobante
              de compra
"""
    
    try:
        job_success = add_print_job({
            'type': 'text',
            'text': test_text,
            'cut_after': True
        })

        if job_success:
            return jsonify({'status': 'success', 'message': 'Ticket de prueba añadido a cola'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir ticket de prueba'}), 500
    except Exception as e:
        print(f"Error en /test_print: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint no encontrado'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500


# --- Cola de impresión y worker ---

def clear_print_queue():
    try:
        default_printer = get_default_printer_name()
        print(f"Limpiando cola de impresión de: {default_printer}")

        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            jobs = win32print.EnumJobs(hPrinter, 0, -1, 1)

            if jobs:
                print(f"Encontrados {len(jobs)} trabajos en cola")
                for job in jobs:
                    try:
                        win32print.SetJob(hPrinter, job['JobId'], 0, None, win32print.JOB_CONTROL_DELETE)
                        print(f"✓ Trabajo {job['JobId']} cancelado")
                    except Exception as e:
                        print(f"✗ Error al cancelar trabajo {job['JobId']}: {e}")

                time.sleep(2)
                print("✓ Cola de impresión limpiada")
            else:
                print("Cola de impresión ya está vacía")

        finally:
            win32print.ClosePrinter(hPrinter)
        return True
    except Exception as e:
        print(f"✗ Error al limpiar cola de impresión: {e}")
        return False


def get_print_queue_status():
    try:
        default_printer = get_default_printer_name()
        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            jobs = win32print.EnumJobs(hPrinter, 0, -1, 1)
            return len(jobs) if jobs else 0
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        print(f"Error al obtener estado de cola: {e}")
        return -1


def process_print_queue():
    global print_thread_running
    print_thread_running = True
    failed_attempts = 0
    max_failed_attempts = 3

    while print_thread_running:
        try:
            job = print_queue.get(timeout=1)

            queue_count = get_print_queue_status()
            if queue_count > 5:
                print(f"⚠️ Cola saturada ({queue_count} trabajos). Limpiando...")
                clear_print_queue()
                time.sleep(2)

            success = False
            job_type = job.get('type')

            with print_lock:
                if job_type == 'pdf':
                    success = print_pdf_file(job['path'])
                elif job_type == 'text':
                    success = print_text_ticket(
                        job['text'], 
                        job.get('cut_after', True),
                        job.get('qr_data', '')
                    )
                elif job_type == 'drawer':
                    success = open_drawer()
                elif job_type == 'cut':
                    success = cut_paper()

            if success:
                failed_attempts = 0
                print(f"✓ Trabajo {job_type} completado exitosamente")
            else:
                failed_attempts += 1
                print(f"✗ Trabajo {job_type} falló (intento {failed_attempts})")

                if failed_attempts >= max_failed_attempts:
                    print(f"⚠️ {max_failed_attempts} fallos consecutivos. Limpiando cola...")
                    clear_print_queue()
                    failed_attempts = 0
                    time.sleep(3)

            print_queue.task_done()
            time.sleep(0.2)

        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error procesando cola de impresión: {e}")
            failed_attempts += 1
            if failed_attempts >= max_failed_attempts:
                clear_print_queue()
                failed_attempts = 0


def start_print_worker():
    global print_thread_running
    if not print_thread_running:
        thread = threading.Thread(target=process_print_queue, daemon=True)
        thread.start()
        print("✓ Hilo de procesamiento de impresión iniciado")


def add_print_job(job_data):
    try:
        print_queue.put(job_data, timeout=5)
        return True
    except queue.Full:
        print("⚠️ Cola de impresión llena. Limpiando...")
        clear_print_queue()
        try:
            print_queue.put(job_data, timeout=5)
            return True
        except queue.Full:
            print("✗ No se pudo añadir trabajo a la cola")
            return False


def parse_arguments():
    """Parsear argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(description='Servidor de impresión con CORS configurable')
    parser.add_argument('--origin', '-o', 
                        type=str,
                        default='https://app.zapeat.es',
                        help='URL permitida para CORS (Access-Control-Allow-Origin). Ejemplo: https://miapp.com')
    parser.add_argument('--port', '-p',
                        type=int,
                        default=5000,
                        help='Puerto del servidor (default: 5000)')
    parser.add_argument('--host', 
                        type=str,
                        default='0.0.0.0',
                        help='Host del servidor (default: 0.0.0.0)')
    
    return parser.parse_args()


def set_allowed_origin(origin_url):
    """Establecer la URL permitida para CORS."""
    global ALLOWED_ORIGIN
    ALLOWED_ORIGIN = origin_url
    print(f"✓ Access-Control-Allow-Origin configurado a: {ALLOWED_ORIGIN}")


from waitress import serve

if __name__ == "__main__":
    print("=" * 60)
    print("    SERVIDOR DE IMPRESIÓN CON CORS CONFIGURABLE")
    print("=" * 60)
    
    # Parsear argumentos de línea de comandos
    args = parse_arguments()
    
    # Configurar la URL permitida para CORS
    set_allowed_origin(args.origin)
    
    print(f"🌐 Origen permitido (CORS): {ALLOWED_ORIGIN}")
    print(f"🖥️  Host: {args.host}")
    print(f"🔌 Puerto: {args.port}")
    print()
    
    print("Iniciando servidor de impresión en modo RAW para tickets...")
    clear_print_queue()
    start_print_worker()
    
    print("✓ Servidor iniciado correctamente")
    print()
    print("Ejemplos de uso:")
    print(f"  python {sys.argv[0]} --origin https://miapp.com --port 5000")
    print(f"  python {sys.argv[0]} -o https://localhost:3000 -p 8080")
    print()
    print("Presiona Ctrl+C para detener el servidor")
    print("=" * 60)
    
    try:
        serve(app, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\n🛑 Servidor detenido por el usuario")
        print("¡Hasta luego!")
    except Exception as e:
        print(f"\n❌ Error al iniciar el servidor: {e}")
        sys.exit(1)