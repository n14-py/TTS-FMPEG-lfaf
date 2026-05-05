import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- CONFIGURACIÓN ---
# Estos son los permisos que pediremos (Subir videos y gestionar cuenta YouTube)
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload', 
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/yt-analytics.readonly'
]

# Lista de cuentas (Debe coincidir EXACTAMENTE con video_generator.py)
ACCOUNTS = [
    {"id": 0, "name": "Principal",    "secret": "client_secret_0.json", "token": "token_0.json"},
    {"id": 1, "name": "NoticiasLat1", "secret": "client_secret_1.json", "token": "token_1.json"},
    {"id": 2, "name": "NoticiasLat2", "secret": "client_secret_2.json", "token": "token_2.json"},
    {"id": 3, "name": "NoticiasLat3", "secret": "client_secret_3.json", "token": "token_3.json"},
    {"id": 4, "name": "NoticiasLat4", "secret": "client_secret_4.json", "token": "token_4.json"},
    {"id": 5, "name": "NoticiasLat5", "secret": "client_secret_5.json", "token": "token_5.json"}
]

def generar_token():
    print("--- GENERADOR DE TOKENS DE YOUTUBE (6 CUENTAS) ---")
    print("Selecciona la cuenta para autorizar:")
    
    for acc in ACCOUNTS:
        estado = "✅ LISTO" if os.path.exists(acc['token']) else "❌ FALTA TOKEN"
        print(f"[{acc['id']}] {acc['name']} (Archivo secreto: {acc['secret']}) -> {estado}")
        
    try:
        seleccion = int(input("\nIngresa el NÚMERO de la cuenta (0-5): "))
    except ValueError:
        print("Error: Debes ingresar un número.")
        return

    # Validar selección
    cuenta_seleccionada = next((acc for acc in ACCOUNTS if acc['id'] == seleccion), None)
    
    if not cuenta_seleccionada:
        print("❌ Selección inválida. Elige un número del 0 al 5.")
        return

    secret_file = cuenta_seleccionada['secret']
    token_file = cuenta_seleccionada['token']

    # Verificar que exista el archivo client_secret_X.json
    if not os.path.exists(secret_file):
        print(f"❌ ERROR: No encuentro el archivo '{secret_file}'.")
        print("Debes descargar el JSON de credenciales de Google Cloud Console y renombrarlo.")
        return

    print(f"\n🚀 Iniciando autorización para: {cuenta_seleccionada['name']}...")
    
    creds = None
    # Si ya existe un token, intentamos cargarlo (aunque la idea de este script es regenerarlo si falla)
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception:
            print("El token existente estaba corrupto, generaremos uno nuevo.")

    # Si no hay credenciales válidas, iniciamos el logueo manual
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("🔄 El token ha expirado, intentando refrescar automáticamente...")
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ No se pudo refrescar ({e}), pediremos autorización manual nuevamente.")
                flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
                # launch_browser=False es importante si estás en un servidor remoto sin pantalla
                # Si estás en tu PC local, puedes poner True.
                creds = flow.run_local_server(port=0)
        else:
            print("🌐 Se abrirá el navegador para que inicies sesión con la cuenta correcta.")
            flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Guardar el token generado
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            print(f"\n✅ ¡ÉXITO! Token guardado en '{token_file}'.")
            print("El bot ahora podrá usar esta cuenta indefinidamente (se auto-refrescará).")

if __name__ == '__main__':
    generar_token()