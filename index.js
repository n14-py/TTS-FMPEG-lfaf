// Archivo: index.js (Servidor Worker tts-fmpeg)
require('dotenv').config();
const express = require('express');
const axios = require('axios');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const cloudinary = require('cloudinary').v2; // ¡IMPORTANTE!

const app = express();
app.use(express.json());

// --- Configuración ---
const PORT = process.env.PORT || 3001;
const MAIN_API_URL = process.env.MAIN_API_URL; 
const ADMIN_API_KEY = process.env.ADMIN_API_KEY; 

// --- ¡NUEVO! Configuración de Cloudinary ---
cloudinary.config({
    cloud_name: process.env.CLOUDINARY_CLOUD_NAME,
    api_key: process.env.CLOUDINARY_API_KEY,
    api_secret: process.env.CLOUDINARY_API_SECRET
});

if (!MAIN_API_URL || !ADMIN_API_KEY || !process.env.CLOUDINARY_CLOUD_NAME) {
    console.error("¡ERROR FATAL! Faltan MAIN_API_URL, ADMIN_API_KEY o credenciales de CLOUDINARY en el .env");
    process.exit(1);
}

// --- Ubicación de tus videos de presentadores ---
const AVATAR_DIR = path.join(__dirname, 'avatars');
const TEMP_DIR = path.join(__dirname, 'temp');

// --- Endpoint principal ---
app.post('/api/v1/generate-video', async (req, res) => {
    // 1. Seguridad
    if (req.headers['x-api-key'] !== ADMIN_API_KEY) {
        return res.status(403).json({ error: 'Acceso no autorizado.' });
    }

    // ¡CAMBIO! Recibimos 'miniaturaUrl'
    const { texto, articleId, miniaturaUrl } = req.body;
    
    if (!texto || !articleId) {
        return res.status(400).json({ error: 'Faltan texto o articleId' });
    }

    // 2. Responder INMEDIATAMENTE
    res.json({ message: 'Procesamiento de video iniciado.' });

    // --- El trabajo pesado comienza AHORA ---
    console.log(`[JOB ${articleId}] Iniciado.`);
    const audioPath = path.join(TEMP_DIR, `${articleId}_audio.wav`);
    const videoPath = path.join(TEMP_DIR, `${articleId}_final.mp4`);

    try {
        // --- PASO A: Generar Audio con CoquiTTS ---
        console.log(`[JOB ${articleId}] Iniciando TTS...`);
        const audioFile = await runCoquiTTS(texto, audioPath);
        console.log(`[JOB ${articleId}] TTS completado: ${audioFile}`);

        // --- PASO B: Generar Video con FFmpeg ---
        console.log(`[JOB ${articleId}] Iniciando FFmpeg...`);
        const finalVideoFile = await runFFmpeg(audioFile, videoPath);
        console.log(`[JOB ${articleId}] FFmpeg completado: ${finalVideoFile}`);

        // --- ¡¡PASO C MODIFICADO!! Subir a Cloudinary ---
        console.log(`[JOB ${articleId}] Subiendo a Cloudinary...`);
        // Pasamos la miniatura a Cloudinary para que la use como "imagen de póster"
        const cloudinaryResult = await uploadToCloudinary(finalVideoFile, articleId, miniaturaUrl);
        console.log(`[JOB ${articleId}] Subida a Cloudinary completa: ${cloudinaryResult.secure_url}`);

        // --- ¡¡PASO D MODIFICADO!! Avisar a la API Principal ---
        console.log(`[JOB ${articleId}] Notificando a la API principal...`);
        // Enviamos la 'cloudinary_url' y la 'miniaturaUrl'
        await notifyMainApi(articleId, cloudinaryResult.secure_url, miniaturaUrl, null);
        console.log(`[JOB ${articleId}] ¡TRABAJO FINALIZADO!`);

    } catch (error) {
        console.error(`[JOB ${articleId}] Error fatal: ${error.message}`);
        // Avisar a la API principal que este job falló
        await notifyMainApi(articleId, null, miniaturaUrl, error.message);
    } finally {
        // Limpiar archivos temporales
        if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
        if (fs.existsSync(videoPath)) fs.unlinkSync(videoPath);
    }
});

// --- Funciones de Ayuda (Helpers) ---

function runCoquiTTS(text, audioOutputPath) {
    // (Esta función no cambia)
    return new Promise((resolve, reject) => {
        console.log(`[CoquiTTS] Llamando a tts_script.py...`);
        const cleanText = text.replace(/"/g, "'").replace(/\n/g, " ");
        const pythonProcess = spawn('python3', ['tts_script.py', cleanText, audioOutputPath]);
        pythonProcess.stdout.on('data', (data) => console.log(`[CoquiTTS-STDOUT]: ${data}`));
        pythonProcess.stderr.on('data', (data) => console.error(`[CoquiTTS-STDERR]: ${data}`));
        pythonProcess.on('close', (code) => {
            if (code !== 0) {
                return reject(new Error(`CoquiTTS falló (código ${code})`));
            }
            resolve(audioOutputPath);
        });
    });
}

function runFFmpeg(audioInput, videoOutput) {
    // (Esta función no cambia)
    return new Promise((resolve, reject) => {
        const avatars = fs.readdirSync(AVATAR_DIR).filter(f => f.endsWith('.mp4'));
        if (avatars.length === 0) {
            return reject(new Error("No se encontraron videos en la carpeta /avatars"));
        }
        const randomAvatar = avatars[Math.floor(Math.random() * avatars.length)];
        const avatarPath = path.join(AVATAR_DIR, randomAvatar);
        console.log(`[FFmpeg] Usando avatar: ${randomAvatar}`);

        const args = [
            '-i', avatarPath,     // Input 0 (Video)
            '-i', audioInput,     // Input 1 (Audio)
            '-c:v', 'copy',       // Copiar stream de video (rápido)
            '-c:a', 'aac',        // Re-codificar audio a AAC
            '-map', '0:v:0',      // Usar video del Input 0
            '-map', '1:a:0',      // Usar audio del Input 1
            '-shortest',          // Terminar cuando el input más corto (el audio) termine
            '-y',                 // Sobrescribir output si existe
            videoOutput
        ];
        const ffmpegProcess = spawn('ffmpeg', args);
        ffmpegProcess.stderr.on('data', (data) => console.error(`[FFmpeg-STDERR]: ${data}`));
        ffmpegProcess.on('close', (code) => {
            if (code !== 0) {
                return reject(new Error(`FFmpeg falló (código ${code})`));
            }
            resolve(videoOutput);
        });
    });
}

/**
 * ¡NUEVA FUNCIÓN!
 * Sube el video final a Cloudinary.
 */
async function uploadToCloudinary(videoPath, articleId, miniaturaUrl) {
    try {
        const result = await cloudinary.uploader.upload(videoPath, {
            resource_type: "video",
            folder: "noticias_lat_videos", // Carpeta en Cloudinary
            public_id: articleId,         // Usa el ID del artículo como ID público
            overwrite: true,
            // ¡Truco! Usamos la miniatura de la noticia como la imagen "poster"
            // que se muestra antes de dar play al video.
            // Cloudinary la descargará y la asociará.
            image_url: miniaturaUrl 
        });
        return result;
    } catch (error) {
        console.error(`[Cloudinary] Error subiendo ${videoPath}:`, error.message);
        throw new Error(`Fallo en la subida a Cloudinary: ${error.message}`);
    }
}


/**
 * ¡FUNCIÓN MODIFICADA!
 * Ahora envía la 'cloudinary_url' y la 'miniaturaUrl' a la API principal.
 */
async function notifyMainApi(articleId, cloudinaryUrl, miniaturaUrl, errorMessage) {
    try {
        await axios.post(
            `${MAIN_API_URL}/api/article/video-complete`,
            {
                articleId: articleId,
                cloudinary_url: cloudinaryUrl, // ¡CAMBIO!
                miniatura_url: miniaturaUrl,   // ¡NUEVO!
                error: errorMessage 
            },
            {
                headers: { 'x-api-key': ADMIN_API_KEY }
            }
        );
        console.log(`[API-Notify] Notificación enviada para ${articleId}.`);
    } catch (e) {
        console.error(`[API-Notify] ¡FALLO CRÍTICO! No se pudo notificar a la API principal: ${e.message}`);
    }
}

app.listen(PORT, () => {
    if (!fs.existsSync(TEMP_DIR)) fs.mkdirSync(TEMP_DIR);
    if (!fs.existsSync(AVATAR_DIR)) fs.mkdirSync(AVATAR_DIR);
    console.log(`🚀 Servidor Worker 'tts-fmpeg' corriendo en puerto ${PORT}`);
});