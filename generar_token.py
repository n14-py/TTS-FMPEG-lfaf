from google_auth_oauthlib.flow import InstalledAppFlow

# Los mismos permisos que usa tu bot
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secrets.json'

def main():
    print("Iniciando proceso de autenticación...")
    
    # Inicia el flujo de autorización
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    
    # Esto abrirá tu navegador web
    credentials = flow.run_local_server(port=0)
    
    # Guarda las credenciales en token.json
    with open('token.json', 'w') as token:
        token.write(credentials.to_json())
    
    print("¡Éxito! Se ha creado el archivo 'token.json'.")

if __name__ == '__main__':
    main()