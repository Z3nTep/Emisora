// Radio Dinámica - Micro servidor para guardar config
// Uso: node server.js  →  Abre http://localhost:8080
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8080;
const DIR = __dirname;
const PUBLIC_DIR = DIR;
const DATA_DIR = path.join(DIR, 'data');
const CONFIG = path.join(DATA_DIR, 'radio_config.json');
const MUSIC_DIR = process.env.MUSIC_DIR || '/headless/Music';

// Crear directorios si no existen
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

const MIME = { '.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.json':'application/json', '.mp3':'audio/mpeg', '.wav':'audio/wav', '.ogg':'audio/ogg', '.m4a':'audio/mp4', '.flac':'audio/flac', '.aac':'audio/aac' };

http.createServer((req, res) => {
    // API: leer config
    if (req.method === 'GET' && req.url === '/api/config') {
        const data = fs.existsSync(CONFIG) ? fs.readFileSync(CONFIG, 'utf8') : '{}';
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(data);
    }

    // API: guardar config
    if (req.method === 'POST' && req.url === '/api/config') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            try {
                JSON.parse(body); // validar
                fs.writeFileSync(CONFIG, body);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end('{"ok":true}');
            } catch(e) {
                res.writeHead(400);
                res.end('{"error":"JSON inválido"}');
            }
        });
        return;
    }

    // API: listar canciones del servidor
    if (req.method === 'GET' && req.url === '/api/canciones') {
        const validExts = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'];
        
        function scanDir(dir, prefix = '') {
            let results = [];
            try {
                const list = fs.readdirSync(dir);
                list.forEach(file => {
                    const fullPath = path.join(dir, file);
                    const stat = fs.statSync(fullPath);
                    if (stat && stat.isDirectory()) {
                        results = results.concat(scanDir(fullPath, `${prefix}${file}/`));
                    } else {
                        const ext = path.extname(file).toLowerCase();
                        if (validExts.includes(ext)) {
                            results.push({ name: file, path: `${prefix}${file}` });
                        }
                    }
                });
            } catch (err) {
                console.error(`Error escaneando ${dir}:`, err.message);
            }
            return results;
        }

        try {
            const songs = scanDir(MUSIC_DIR);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(songs));
        } catch(e) {
            console.error("Error API canciones:", e);
            res.writeHead(500);
            res.end(JSON.stringify({error: "Error interno"}));
        }
        return;
    }

    // API: variables de entorno expuestas al frontend
    if (req.method === 'GET' && req.url === '/api/env') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ 
            autoplay: process.env.AUTO_PLAY_RADIO === 'true' 
        }));
        return;
    }

    // Servir archivos estáticos
    let file = req.url;
    if (file === '/' || file === '') file = '/emisora_dinamica.html';

    // Ruta aislada para la carpeta de música de Windows (sin ensuciar app/radio)
    if (file.startsWith('/musica/')) {
        const filePath = path.join(MUSIC_DIR, decodeURIComponent(file.substring(8)));
        console.log(`[REQ MUSIC] ${req.url} -> ${filePath}`);
        
        if (!filePath.startsWith(MUSIC_DIR)) { 
            console.warn(`[403] Bloqueado: ${filePath}`);
            res.writeHead(403); 
            return res.end(); 
        }

        fs.readFile(filePath, (err, data) => {
            if (err) { 
                console.error(`[404] Audio no encontrado: ${filePath}`);
                res.writeHead(404); 
                return res.end('No encontrado'); 
            }
            const ext = path.extname(filePath).toLowerCase();
            res.writeHead(200, { 'Content-Type': (MIME[ext] || 'audio/mpeg') });
            res.end(data);
        });
        return;
    }

    const filePath = path.join(PUBLIC_DIR, decodeURIComponent(file));
    console.log(`[REQ] ${req.url} -> ${filePath}`);
    
    // Seguridad: no salir del directorio público y evitar acceso a archivos sensibles
    if (!filePath.startsWith(PUBLIC_DIR) || file.startsWith('/server.js') || file.startsWith('/data/')) { 
        console.warn(`[403] Bloqueado: ${filePath}`);
        res.writeHead(403); 
        return res.end(); 
    }

    fs.readFile(filePath, (err, data) => {
        if (err) { 
            console.error(`[404] No encontrado: ${filePath}`);
            res.writeHead(404); 
            return res.end('No encontrado'); 
        }
        const ext = path.extname(filePath).toLowerCase();
        res.writeHead(200, { 'Content-Type': (MIME[ext] || 'application/octet-stream') + '; charset=utf-8' });
        res.end(data);
    });

}).listen(PORT, '0.0.0.0', () => {
    console.log(`🎵 Radio Dinámica en http://0.0.0.0:${PORT}`);
    console.log(`📂 Public: ${PUBLIC_DIR}`);
    console.log(`📄 Config: ${CONFIG}`);
});
