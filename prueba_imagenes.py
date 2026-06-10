import requests

def probar_descarga_disfrazada(url, nombre_archivo):
    print(f"Intentando descargar: {nombre_archivo}...")
    
    # 🎭 EL DISFRAZ: Le hacemos creer al servidor que somos Chrome en Windows
    cabeceras_falsas = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/" # Fingimos que venimos de buscar en Google
    }

    try:
        # Agregamos los headers y el timeout salvador de 10 segundos
        respuesta = requests.get(url, headers=cabeceras_falsas, timeout=10)
        
        if respuesta.status_code == 200:
            with open(nombre_archivo, 'wb') as archivo:
                archivo.write(respuesta.content)
            print(f"✅ ¡ÉXITO! La imagen burló el escudo y se guardó como '{nombre_archivo}'.")
        else:
            print(f"❌ Falló. El servidor devolvió el código: {respuesta.status_code}")
            
    except Exception as e:
        print(f"❌ Error de conexión (Timeout o bloqueo persistente): {e}")
    
    print("-" * 50)


# ==========================================
# 🚀 ZONA DE PRUEBAS LOCAL
# ==========================================

url_efe = "https://i0.wp.com/efe.com/wp-content/uploads/2026/05/participacion-elecciones-andalucia.webp?fit=900%2C600&ssl=1"
probar_descarga_disfrazada(url_efe, "foto_efe_headers.webp")

url_peruano = "https://elperuano.pe/fotografia/thumbnail/2026/06/09/000382749M.jpg"
probar_descarga_disfrazada(url_peruano, "foto_peru_headers.jpg")