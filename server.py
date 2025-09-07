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
import subprocess

def print_pdf_file(pdf_path):
    """Imprimir un archivo PDF usando comando de sistema sin abrirlo"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Usando impresora por defecto: {default_printer}")
        
        # Usar SumatraPDF para imprimir silenciosamente (si está instalado)
        try:
            subprocess.run([
                "SumatraPDF.exe", 
                "-print-to", default_printer, 
                "-silent", 
                pdf_path
            ], check=True, capture_output=True)
            print("Impreso con SumatraPDF")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback: usar comando print de Windows
            try:
                subprocess.run([
                    "powershell", 
                    f"Start-Process -FilePath '{pdf_path}' -ArgumentList '/t' -WindowStyle Hidden"
                ], check=True, capture_output=True)
                print("Impreso con PowerShell")
                return True
            except subprocess.CalledProcessError:
                # Último recurso: usar printto pero minimizado
                win32api.ShellExecute(0, "printto", pdf_path, f'"{default_printer}"', ".", 7)  # SW_SHOWMINNOACTIVE
                print("Impreso con ShellExecute minimizado")
                return True
                
    except Exception as e:
        print(f"Error al imprimir el PDF: {e}")
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
    """Imprimir un archivo PDF directamente sin abrirlo"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Usando impresora por defecto: {default_printer}")
        
        # Imprimir directamente sin modificar configuración de impresora
        win32api.ShellExecute(
            0, 
            "printto", 
            pdf_path, 
            f'"{default_printer}"', 
            ".", 
            0  # SW_HIDE - no mostrar ventana
        )
        
        print(f"Archivo PDF '{pdf_path}' enviado directamente a la impresora '{default_printer}'")
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
        job_success = add_print_job({'type': 'drawer'})
        
        if job_success:
            return jsonify({'status': 'success', 'message': 'Comando de cajón añadido a cola'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir comando a cola'}), 500
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
        
        job_success = add_print_job({
            'type': 'text',
            'text': data['text'],
            'cut_after': data.get('cut_after', True)
        })
        
        if job_success:
            return jsonify({'status': 'success', 'message': 'Texto añadido a cola de impresión'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir texto a cola'}), 500
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
        
        # Guardar PDF temporalmente
        output_dir = os.path.join(os.path.expanduser("~"), "PrintedPDFs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(output_dir, f"ticket_{timestamp_str}.pdf")
        
        pdf_bytes = base64.b64decode(base64_pdf)
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        
        # Añadir a cola de impresión
        job_success = add_print_job({
            'type': 'pdf',
            'path': pdf_path,
            'timestamp': timestamp
        })
        
        if job_success:
            return jsonify({'status': 'success', 'message': 'PDF añadido a cola de impresión'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al añadir PDF a cola'}), 500
            
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
    

@app.route('/clear_queue', methods=['POST'])
def clear_queue_endpoint():
    """Endpoint para limpiar cola de impresión manualmente"""
    try:
        success = clear_print_queue()
        if success:
            return jsonify({'status': 'success', 'message': 'Cola de impresión limpiada'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Error al limpiar cola'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint no encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Error interno del servidor'}), 500




import threading
import queue
import time

# Cola para gestionar las peticiones de impresión
print_queue = queue.Queue()
print_thread_running = False
print_lock = threading.Lock()

def clear_print_queue():
    """Limpiar cola de impresión de Windows"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        print(f"Limpiando cola de impresión de: {default_printer}")
        
        hPrinter = win32print.OpenPrinter(default_printer)
        try:
            # Obtener todos los trabajos en cola
            jobs = win32print.EnumJobs(hPrinter, 0, -1, 1)
            
            if jobs:
                print(f"Encontrados {len(jobs)} trabajos en cola")
                for job in jobs:
                    try:
                        # Cancelar cada trabajo
                        win32print.SetJob(hPrinter, job['JobId'], 0, None, win32print.JOB_CONTROL_DELETE)
                        print(f"✓ Trabajo {job['JobId']} cancelado")
                    except Exception as e:
                        print(f"✗ Error al cancelar trabajo {job['JobId']}: {e}")
                
                # Esperar un poco para que se procesen las cancelaciones
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
    """Obtener estado de la cola de impresión"""
    try:
        default_printer = win32print.GetDefaultPrinter()
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
    """Procesar cola de impresión en hilo separado"""
    global print_thread_running
    print_thread_running = True
    failed_attempts = 0
    max_failed_attempts = 3
    
    while print_thread_running:
        try:
            # Obtener siguiente trabajo de la cola (timeout 1 segundo)
            job = print_queue.get(timeout=1)
            
            # Verificar estado de la cola antes de imprimir
            queue_count = get_print_queue_status()
            if queue_count > 5:  # Si hay más de 5 trabajos en cola
                print(f"⚠️  Cola saturada ({queue_count} trabajos). Limpiando...")
                clear_print_queue()
                time.sleep(2)
            
            # Procesar el trabajo
            success = False
            job_type = job.get('type')
            
            with print_lock:  # Evitar impresiones simultáneas
                if job_type == 'pdf':
                    success = print_pdf_file(job['path'])
                elif job_type == 'text':
                    success = print_text_ticket(job['text'], job.get('cut_after', True))
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
                
                # Si fallan muchos trabajos seguidos, limpiar cola
                if failed_attempts >= max_failed_attempts:
                    print(f"⚠️  {max_failed_attempts} fallos consecutivos. Limpiando cola...")
                    clear_print_queue()
                    failed_attempts = 0
                    time.sleep(3)
            
            # Marcar trabajo como completado
            print_queue.task_done()
            
            # Pausa pequeña entre trabajos
            time.sleep(0.5)
            
        except queue.Empty:
            # No hay trabajos en cola, continuar
            continue
        except Exception as e:
            print(f"Error procesando cola de impresión: {e}")
            failed_attempts += 1
            if failed_attempts >= max_failed_attempts:
                clear_print_queue()
                failed_attempts = 0

def start_print_worker():
    """Iniciar hilo de procesamiento de impresión"""
    global print_thread_running
    if not print_thread_running:
        thread = threading.Thread(target=process_print_queue, daemon=True)
        thread.start()
        print("✓ Hilo de procesamiento de impresión iniciado")

def add_print_job(job_data):
    """Añadir trabajo a la cola de impresión"""
    try:
        print_queue.put(job_data, timeout=5)
        return True
    except queue.Full:
        print("⚠️  Cola de impresión llena. Limpiando...")
        clear_print_queue()
        try:
            print_queue.put(job_data, timeout=5)
            return True
        except queue.Full:
            print("✗ No se pudo añadir trabajo a la cola")
            return False
        

        
if __name__ == "__main__":
    print("Iniciando servidor de impresión...")
    
    # Limpiar cola al inicio
    clear_print_queue()
    
    # Iniciar hilo de procesamiento
    start_print_worker()
    
    print("Endpoints disponibles:")
    print("  POST /open_drawer - Abrir cajón de la impresora")
    print("  POST /cut_paper - Cortar papel")
    print("  POST /print_text - Imprimir ticket de texto")
    print("  POST /print - Imprimir ticket PDF")
    print("  POST /clear_queue - Limpiar cola de impresión")
    print("  GET /status - Estado del servidor")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )