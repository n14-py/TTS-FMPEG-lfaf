from google_auth_oauthlib.flow import InstalledAppFlow
import os

# Alcance de permisos para subir videos
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    print("--- GENERADOR DE TOKENS INFINITOS (SISTEMA DE 4 CANALES) ---")
    print("0: Cuenta Principal")
    print("1: noticiaslat1")
    print("2: noticiaslat2")
    print("3: noticiaslat3")
    
    opcion = input("\n¿Para qué cuenta quieres generar el token? (0-3): ").strip()
    
    if opcion not in ['0', '1', '2', '3']:
        print("❌ Opción no válida.")
        return

    secret_file = f'client_secret_{opcion}.json'
    token_file = f'token_{opcion}.json'

    if not os.path.exists(secret_file):
        print(f"❌ ERROR: No encuentro el archivo '{secret_file}'.")
        print("Asegúrate de haber descargado el JSON de Google Cloud y renombrado correctamente.")
        return

    print(f"\nIniciando autorización para la CUENTA {opcion}...")
    print(f"Usando secreto: {secret_file}")
    
    flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    
    # Esto abrirá el navegador para que te loguees con el gmail correspondiente
    credentials = flow.run_local_server(port=0)
    
    # Guardamos el token
    with open(token_file, 'w') as token:
        token.write(credentials.to_json())
    
    print(f"✅ ¡ÉXITO! Se ha creado '{token_file}'.")
    print("Este archivo contiene el 'refresh_token' para acceso permanente.")

if __name__ == '__main__':
    main()