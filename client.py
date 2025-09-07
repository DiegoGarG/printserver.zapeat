import requests
import json
import time

SERVER_URL = "http://localhost:12345"

def test_server_status():
    print("\n=== Probando estado del servidor ===")
    try:
        response = requests.get(f"{SERVER_URL}/status")
        print(f"Estado: {response.status_code}")
        print(f"Respuesta: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_open_drawer():
    print("\n=== Probando apertura de cajón ===")
    try:
        response = requests.post(f"{SERVER_URL}/open_drawer")
        print(f"Estado: {response.status_code}")
        print(f"Respuesta: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_cut_paper():
    print("\n=== Probando corte de papel ===")
    try:
        response = requests.post(f"{SERVER_URL}/cut_paper")
        print(f"Estado: {response.status_code}")
        print(f"Respuesta: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_print_text():
    print("\n=== Probando impresión de ticket de texto ===")
    
    ticket_text = """================================
          TIENDA DE EJEMPLO
================================
Fecha: 01/01/2023 12:34:56
Caja: 1
Ticket: 1234

Artículo 1          10.00
Artículo 2          20.00
Artículo 3          15.00

TOTAL:              45.00
================================
          ¡VUELVA PRONTO!
================================
"""
    
    try:
        data = {
            'text': ticket_text,
            'cut_after': True  # Cortar después de imprimir
        }
        response = requests.post(
            f"{SERVER_URL}/print_text",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(data)
        )
        print(f"Estado: {response.status_code}")
        print(f"Respuesta: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_print_pdf():
    print("\n=== Probando impresión de PDF ===")
    print("Nota: Esta prueba requiere un PDF en base64")
    
    try:
        # Si tienes un PDF de prueba, puedes usarlo aquí
        with open("ejemplo.pdf", "rb") as pdf_file:
            import base64
            pdf_base64 = base64.b64encode(pdf_file.read()).decode('utf-8')
        
        data = {'pdf_data': pdf_base64}
        response = requests.post(
            f"{SERVER_URL}/print",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(data)
        )
        print(f"Estado: {response.status_code}")
        print(f"Respuesta: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except FileNotFoundError:
        print("No se encontró el archivo ejemplo.pdf. Prueba omitida.")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Iniciando pruebas del servidor de impresión")
    print(f"Servidor: {SERVER_URL}")
    
    tests = [
        test_server_status,
        test_open_drawer,
        test_cut_paper,
        test_print_text,
        test_print_pdf
    ]
    
    results = []
    for test in tests:
        results.append(test())
        time.sleep(1)
    
    print("\n=== RESUMEN DE PRUEBAS ===")
    for i, result in enumerate(results):
        test_name = tests[i].__name__
        status = "EXITOSA" if result else "FALLIDA"
        print(f"{test_name}: {status}")
    
    print("\nPruebas completadas.")