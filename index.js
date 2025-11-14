// Archivo: index.js (Servidor Worker tts-fmpeg)
require('dotenv').config();
const express = require('express');
const axios = require('axios');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json());

// --- Configuración ---
const PORT = process.env.PORT || 3001;
const MAIN_API_URL = process.env.MAIN_API_URL; 
const ADMIN_API_KEY = process.env.ADMIN_API_KEY; 

if (!MAIN_API_URL || !ADMIN_API_KEY) {
    console.error("¡ERROR FATAL! Faltan MAIN_API_URL o ADMIN_API_KEY en el .env");
    process.exit(1);
}

// --- Ubicación de tus videos de presentadores ---
const AVATAR_DIR = path.join(__dirname, 'avatars');
const TEMP_DIR = path.join(__dirname, 'temp');

// --- Endpoint principal ---
// Tu API de $7 llamará a esta ruta
app.post('/api/v1/generate-video', async (req, res) => {
    // 1. Seguridad: Validar que la llamada venga de tu propia API
    if (req.headers['x-api-key'] !== ADMIN_API_KEY) {
        return res.status(403).json({ error: 'Acceso no autorizado.' });
    }

    const { texto, articleId, miniaturaUrl } = req.body;
    
    if (!texto || !articleId) {
        return res.status(400).json({ error: 'Faltan texto o articleId' });
    }

    // 2. Responder INMEDIATAMENTE a la API principal (Modo "Fire-and-Forget")
    res.json({ message: 'Procesamiento de video iniciado.' });

    // --- El trabajo pesado comienza AHORA (en segundo plano) ---
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

        // --- PASO C: Subir a Ezoic (¡REEMPLAZAR SIMULACIÓN!) ---
        console.log(`[JOB ${articleId}] Subiendo a Ezoic...`);
        const ezoicUrl = await uploadToEzoic(finalVideoFile, miniaturaUrl);
        console.log(`[JOB ${articleId}] Subida completa: ${ezoicUrl}`);

        // --- PASO D: Avisar a la API Principal (lfaftechapi) ---
        console.log(`[JOB ${articleId}] Notificando a la API principal...`);
        await notifyMainApi(articleId, ezoicUrl, null);
        console.log(`[JOB ${articleId}] ¡TRABAJO FINALIZADO!`);

    } catch (error) {
        console.error(`[JOB ${articleId}] Error fatal: ${error.message}`);
        // Avisar a la API principal que este job falló
        await notifyMainApi(articleId, null, error.message);
    } finally {
        // Limpiar archivos temporales
        if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
        if (fs.existsSync(videoPath)) fs.unlinkSync(videoPath);
    }
});

// --- Funciones de Ayuda (Helpers) ---

function runCoquiTTS(text, audioOutputPath) {
    return new Promise((resolve, reject) => {
        console.log(`[CoquiTTS] Llamando a tts_script.py...`);
        // Limpiamos el texto para la línea de comandos
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
    return new Promise((resolve, reject) => {
        // 1. Cargar lista de avatares y elegir uno
        const avatars = fs.readdirSync(AVATAR_DIR).filter(f => f.endsWith('.mp4'));
        if (avatars.length === 0) {
            return reject(new Error("No se encontraron videos en la carpeta /avatars"));
        }
        const randomAvatar = avatars[Math.floor(Math.random() * avatars.length)];
        const avatarPath = path.join(AVATAR_DIR, randomAvatar);
        console.log(`[FFmpeg] Usando avatar: ${randomAvatar}`);

        // 2. Comando FFmpeg (copia video, re-codifica audio, usa el más corto)
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

async function uploadToEzoic(videoPath, thumbnailUrl) {
    // --- ================================== ---
    // --- ¡¡SIMULACIÓN!! ¡DEBES REEMPLAZAR ESTO! ---
    // --- ================================== ---
    // Aquí es donde usas `axios` o la librería de Ezoic
    // para subir el `videoPath` (usando `fs.createReadStream(videoPath)`)
    // y la `thumbnailUrl` (si la API de Ezoic lo permite).
    
    console.log(`[Ezoic] SIMULANDO subida de ${videoPath}...`);
    await new Promise(res => setTimeout(res, 3000)); // Simular 3s de subida
    
    // Devuelve una URL falsa de Ezoic
    const fakeEzoicUrl = `https://simulado.ezoic.com/video/${path.basename(videoPath)}`;
    return fakeEzoicUrl;
    // --- ================================== ---
}

async function notifyMainApi(articleId, videoUrl, errorMessage) {
    try {
        await axios.post(
            `${MAIN_API_URL}/api/article/video-complete`,
            {
                articleId: articleId,
                videoUrl: videoUrl, // Será null si hay un error
                error: errorMessage // Será null si hay éxito
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
    // Asegurarse que las carpetas 'temp' y 'avatars' existan
    if (!fs.existsSync(TEMP_DIR)) fs.mkdirSync(TEMP_DIR);
    if (!fs.existsSync(AVATAR_DIR)) fs.mkdirSync(AVATAR_DIR);
    
    console.log(`🚀 Servidor Worker 'tts-fmpeg' corriendo en puerto ${PORT}`);
});