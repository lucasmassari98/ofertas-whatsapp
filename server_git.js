const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers, fetchLatestBaileysVersion, downloadMediaMessage } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');

const app = express();
app.use(express.json({ limit: '50mb' }));

let sock;

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('sessao_baileys');
    
    const { version } = await fetchLatestBaileysVersion();
    console.log(`📱 Iniciando robô com a versão do WhatsApp: v${version.join('.')}`);

    sock = makeWASocket({
        version, 
        auth: state,
        browser: Browsers.ubuntu('Chrome'), 
        logger: pino({ level: 'silent' }),
        syncFullHistory: false
    });

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) qrcode.generate(qr, { small: true });

        if (connection === 'close') {
            const shouldReconnect = lastDisconnect.error?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) setTimeout(connectToWhatsApp, 2000);
        } else if (connection === 'open') {
            console.log('\n✅ WhatsApp Conectado com Sucesso!');
            console.log('📡 Radar ativado. Escutando Grupos e Canais...\n');
        }
    });

    sock.ev.on('messages.upsert', async ({ messages }) => {
        const msg = messages[0];
        if (!msg.message || msg.key.fromMe) return; 

        const from = msg.key.remoteJid;
        
        // 🚀 A MÁGICA ACONTECE AQUI: Agora ele aceita Grupos (@g.us) e Canais (@newsletter)
        if (!from.endsWith('@g.us') && !from.endsWith('@newsletter')) return; 
        
        let mensagemReal = msg.message;
        // Desembrulha mensagens temporárias (ephemeral), de visualização única ou editadas
        if (mensagemReal.ephemeralMessage) mensagemReal = mensagemReal.ephemeralMessage.message;
        if (mensagemReal.viewOnceMessage) mensagemReal = mensagemReal.viewOnceMessage.message;
        if (mensagemReal.viewOnceMessageV2) mensagemReal = mensagemReal.viewOnceMessageV2.message;
        if (mensagemReal.editedMessage) mensagemReal = mensagemReal.editedMessage.message || mensagemReal.editedMessage.protocolMessage?.editedMessage;

        if (!mensagemReal) return;

        const texto = mensagemReal.conversation || 
                      mensagemReal.extendedTextMessage?.text || 
                      mensagemReal.imageMessage?.caption || 
                      mensagemReal.videoMessage?.caption || 
                      mensagemReal.templateButtonReplyMessage?.selectedId || 
                      mensagemReal.buttonsResponseMessage?.selectedButtonId || "";

        const regexLink = /((?:https?:\/\/|www\.)[^\s]+)/g;
        const links = texto.match(regexLink);

        if (links) {
            
            // Fofoqueiro: Imprime o ID de quem mandou o link para te ajudar a cadastrar novos!
            console.log(`\n🔎 MENSAGEM COM LINK RECEBIDA DA ORIGEM: ${from}`);
            
            let imagemB64 = null;
            if (msg.message.imageMessage) {
                try {
                    const buffer = await downloadMediaMessage(msg, 'buffer', { }, { logger: pino({ level: 'silent' }) });
                    imagemB64 = buffer.toString('base64');
                    console.log("📸 Imagem original capturada com sucesso!");
                } catch (err) {
                    console.log("⚠️ Não foi possível baixar a foto original.");
                }
            }

            for (const link of links) {
                const linkLower = link.toLowerCase();
                const lojasAlvo = ['amazon', 'amzn.to', 'mercadolivre', 'meli.la', 'shopee', 'shp.ee', 's.shopee'];
                if (lojasAlvo.some(loja => linkLower.includes(loja))) {
                    console.log(`🚨 Link detectado no radar! -> ${link}`);
                    
                    try {
                        await fetch('http://localhost:5000/automacao_invisivel', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                url: link, 
                                grupo_origem: from, 
                                texto_original: texto,
                                imagem_base64: imagemB64 
                            })
                        });
                        console.log("✅ Dados e foto entregues ao Python!");
                    } catch (e) {
                        console.log("⚠️ AVISO: O Python está desligado (Porta 5000).");
                    }
                    break; 
                }
            }
        }
    });

    sock.ev.on('creds.update', saveCreds);
}

connectToWhatsApp();

app.post('/enviar', async (req, res) => {
    const { numero_ou_grupo, mensagem, imagem_url } = req.body;
    try {
        if (imagem_url) {
            if (imagem_url.startsWith('data:image')) {
                const base64Data = imagem_url.split(',')[1];
                const buffer = Buffer.from(base64Data, 'base64');
                await sock.sendMessage(numero_ou_grupo, { image: buffer, caption: mensagem });
            } else {
                await sock.sendMessage(numero_ou_grupo, { image: { url: imagem_url }, caption: mensagem });
            }
        } else {
            await sock.sendMessage(numero_ou_grupo, { text: mensagem });
        }
        res.json({ sucesso: true });
    } catch (erro) {
        res.status(500).json({ sucesso: false, erro: erro.toString() });
    }
});

app.listen(3000, () => {});
