from flask import Flask, request, jsonify, render_template, Response
import pickle
import time
import os
import requests 
import threading 
import re 
import hmac
import hashlib
import json
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

app = Flask(__name__)

# ==========================================
# CONFIGURAÇÕES TÉCNICAS E CHAVES
# ==========================================
AMAZON_TAG = "lcmlofertas0d-20" 
LINKTREE_GRUPO = "https://lcmlofertas.netlify.app/"
DESTINO_OFICIAL = "120363421633843442@g.us" 

# CHAVES DA SHOPEE INSERIDAS CONFORME SOLICITADO
SHOPEE_APP_ID = "18376350843"
SHOPEE_APP_SECRET = "5E3GX2TAEGHRT3Q636DLEKO4XBMOLJQR"

GRUPOS_FONTES = {
    "Glow perfumado Deles 👔": "120363404123314956@g.us",
    "Jotinha Cupons | Ofertas": "120363403118132992@g.us",
    "OfertaChip": "120363418799519639@g.us",
    "Cupons do Rolê (Canal)": "120363403726606386@newsletter",
    "Promo Perfumes": "120363409162898512@g.us",
    "Tech Deals": "120363405911622948@g.us"
}

PALAVRAS_PROIBIDAS = [
    'fralda', 'fraldas', 'pomada', 'hipoglos', 'hipoglós', 'creme', 
    'maquiagem', 'batom', 'absorvente', 'shampoo', 'condicionador', 
    'sabonete', 'pampers', 'huggies', 'skincare', 'cosmético'
]

TEMPO_BLOQUEIO_DUPLICATAS = 5 * 3600  
registro_duplicatas = {} 
registro_cupons_camaleao = {}
lock_duplicatas = threading.Lock()

fontes_ativas_para_copiar = list(GRUPOS_FONTES.values())
historico_ofertas = []

# ==========================================
# FUNÇÕES DE SUPORTE E LIMPEZA
# ==========================================

def obter_link_chave_spam(url):
    """Gera uma chave para o anti-spam preservando o case do path (importante para links curtos)."""
    if not url: return ""
    parsed = urllib.parse.urlparse(url.split('?')[0])
    # Domínio em minúsculo, mas o caminho (ID do produto) mantém as maiúsculas/minúsculas
    return f"{parsed.netloc.lower()}{parsed.path}".strip()

def gerar_link_amazon(url_original):
    # Resolve links curtos amzn.to para garantir que a tag seja aplicada na URL final
    if "amzn.to" in url_original:
        try:
            headers_nav = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            r = requests.get(url_original, allow_redirects=True, timeout=5, headers=headers_nav)
            url_original = r.url
        except: pass
    if "?" in url_original:
        return url_original.split("?")[0] + f"?tag={AMAZON_TAG}"
    return url_original + f"?tag={AMAZON_TAG}"

def limpar_formatacao(texto):
    if not texto:
        return ""
    return re.sub(r'[*_~`]', '', texto).strip()

def configurar_driver_camuflado():
    opts = Options()
    opts.add_argument("--headless=new") 
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--lang=pt-BR")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def extrair_emoji_do_texto(texto):
    texto_convertido = texto.replace('👉', '🔥').replace('👉🏻', '🔥').replace('👉🏼', '🔥').replace('👉🏽', '🔥').replace('👉🏾', '🔥').replace('👉🏿', '🔥')
    for char in texto_convertido:
        if '\U00010000' <= char <= '\U0010ffff' or '\u2600' <= char <= '\u27BF':
            return char
    return None

def remover_emojis(texto):
    if not texto: return ""
    return "".join(c for c in texto if not ('\U00010000' <= c <= '\U0010ffff' or '\u2600' <= c <= '\u27BF'))

def descobrir_emoji(titulo):
    t = titulo.lower() if titulo else ""
    if any(x in t for x in ['teclado', 'keyboard', 'k608', 'valheim']): return '⌨️'
    if any(x in t for x in ['mouse', 'predator', 'm612']): return '🖱️'
    if any(x in t for x in ['gabinete', 'aquário', 'hayom', 'tower', 'cooler', 'rgb']): return '🖥️'
    if any(x in t for x in ['celular', 'smartphone', 'iphone', 'samsung', 'motorola', 'poco']): return '📱'
    if any(x in t for x in ['perfume', 'eau de parfum', 'fragrância', 'versace', 'lattafa', 'parfum']): return '✨'
    if any(x in t for x in ['ps5', 'xbox', 'nintendo', 'game', 'jogo']): return '🎮'
    if any(x in t for x in ['placa de vídeo', 'rtx', 'ssd', 'processador', 'memória ram']): return '⚙️'
    if any(x in t for x in ['tênis', 'sapato', 'nike', 'adidas']): return '👟'
    if any(x in t for x in ['fone', 'headset', 'airpods', 'buds']): return '🎧'
    if any(x in t for x in ['smart tv', 'televisão', 'monitor']): return '📺'
    return ''

def carregar_cookies(driver, dominio, arquivo_cookie):
    driver.get(dominio)
    time.sleep(2) 
    try:
        if os.path.exists(arquivo_cookie):
            cookies = pickle.load(open(arquivo_cookie, "rb"))
            for cookie in cookies:
                try: 
                    driver.add_cookie(cookie)
                except: 
                    pass
            driver.refresh() 
            time.sleep(2)
    except: 
        pass

def converter_para_numero(valor_str):
    if not valor_str:
        return 0.0
    limpo = valor_str.replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(limpo)
    except:
        return 0.0

def formatar_moeda(valor_float):
    return f"{valor_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def limpar_url_suja(url):
    if not url: return ""
    # Remove caracteres de pontuação e formatação que costumam vir grudados em links do WhatsApp
    return re.sub(r'[.,!?;:()\[\]{}*~_]+$', '', url.strip())

def limpar_parcelamento(p_str):
    if not p_str: return ""
    p_str = re.sub(r'(?i)^em\s+', '', p_str)
    p_str = re.sub(r'(?i)R\$?\s*[\d\.,]+\s*/\s*[a-zA-Z0-9]+.*', '', p_str)
    return re.sub(r'\s+', ' ', p_str).strip()

def extrair_titulo_do_texto_amigo(texto):
    if not texto: return ""
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    for linha in linhas:
        l_low = linha.lower()
        if any(x in l_low for x in ['http', 'meli.la', 'amzn.to', 'shp.ee', 'shopee', 'cupom', 'código', 'r$', 'loja', 'link', 'por apenas', 'regras', 'oferta', 'validada']): 
            continue
        
        linha_limpa = re.sub(r'[^\w\s\(\)\-]', '', linha).strip()
        linha_limpa = re.sub(r'[*_~`#]', '', linha_limpa).strip()
        linha_limpa = limpar_formatacao(linha_limpa)
        linha_limpa = re.sub(r'\s*\([A-Za-z0-9]{1,3}\)', '', linha_limpa)
        linha_limpa = re.sub(r'\b(\w+)\s+\1\b', r'\1', linha_limpa, flags=re.IGNORECASE)
        
        if len(linha_limpa) > 8: 
            return linha_limpa.strip()
    return ""

def extrair_info_texto(texto):
    cupom = ""
    preco_final = ""
    parcelamento = ""
    desconto_extra = ""
    chamada_especial = ""
    regra_cupom = ""
    preco_antigo = ""
    preco_contexto = ""
    
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    for linha in linhas[:2]: 
        l_upper = linha.upper()
        if (linha.isupper() or "!" in linha or "PRIME" in l_upper or "🎯" in linha or "🚨" in linha) and "HTTP" not in l_upper and "R$" not in l_upper:
            chamada_especial = linha.replace('`', '')
            break 
            
    texto_limpo = limpar_formatacao(texto)
    
    texto_limpo_sem_links = re.sub(r'(?i)http\S+', '', texto_limpo)
    texto_limpo_sem_links = re.sub(r'(?i)meli\.la\S+', '', texto_limpo_sem_links)
    texto_limpo_sem_links = re.sub(r'(?i)amzn\.to\S+', '', texto_limpo_sem_links)
    texto_limpo_sem_links = re.sub(r'(?i)shp\.ee\S+', '', texto_limpo_sem_links)
    texto_limpo_sem_links = re.sub(r'(?i)shopee\.com\S+', '', texto_limpo_sem_links)
    texto_limpo_sem_links = re.sub(r'(?i)www\.\S+', '', texto_limpo_sem_links)
    
    # --- MELHORIA: Filtro de Preços Falsos (Regras de Cupom) ---
    termos_regra = ['máximo', 'maximo', 'mínimo', 'minimo', 'limite', 'acima de', 'até', 'ate', 'compras de', 'valor de']
    
    linhas_texto = texto_limpo.split('\n')
    for linha in linhas_texto:
        l_baixa = linha.lower()
        # Se a linha contém termos de regra de cupom, ignoramos ela para busca de preço
        if any(term in l_baixa for term in termos_regra):
            continue
            
        # Prioridade 1: Formato "De R$ X por R$ Y"
        match_de_por = re.search(r'(?i)de\s*(?:r\$)?\s*([\d\.,]+)\s*por\s*(?:r\$)?\s*([\d\.,]+)(.*)', linha)
        if match_de_por:
            preco_antigo = match_de_por.group(1).strip()
            preco_final = match_de_por.group(2).strip()
            preco_contexto = re.split(r'[\n✅❌💳🛒🎟️]', match_de_por.group(3).strip())[0].strip()
            break

        # Prioridade 2: Apenas "por R$ Y"
        match_por = re.search(r'(?i)\bpor\s*(?:r\$)?\s*([\d\.,]+)(.*)', linha)
        if not match_por:
            match_por = re.search(r'(?i)(?:apenas|💰)\s*(?:r\$)?\s*([\d\.,]+)(.*)', linha)
            
        if match_por:
            preco_final = match_por.group(1).strip()
            ctx = match_por.group(2).strip()
            preco_contexto = re.split(r'[\n✅❌💳🛒🎟️]', ctx)[0].strip()
            break

    if not preco_final:
        # Fallback inteligente: pega valores R$ que não são seguidos de 'off' e não têm contexto de regra
        for m in re.finditer(r'(?i)r\$\s*([\d\.,]+)', texto_limpo):
            pos = m.start()
            contexto = texto_limpo[max(0, pos-40):pos].lower()
            if not any(term in contexto for term in termos_regra):
                suffix = texto_limpo[m.end():m.end()+15].lower()
                if 'off' not in suffix and 'desconto' not in suffix:
                    preco_final = m.group(1).strip()
                    # Não damos break aqui para tentar pegar o último valor (geralmente o menor/final)

    # Extração de Cupom permanece com a lógica de ignorar palavras comuns
    for match in re.finditer(r'(?im)^.*(?:cupom|código|🎟️|🎟|🎫|🔖|🏷️).*$', texto_limpo_sem_links):
        linha_inteira = match.group(0)
        linha_sem_trigger = re.sub(r'(?i)\b(cupom|código)\b|🎟️|🎟|🎫|🔖|🏷️|:', '', linha_inteira).strip()
        palavras = linha_sem_trigger.split()
        for p in palavras:
            verificacao = re.sub(r'[^\w]', '', p).upper()
            ignorar_exatos = ['MERCADO', 'LIVRE', 'AMAZON', 'SHOPEE', 'KABUM', 'ALIEXPRESS', 'MAGALU', 'NOVO', 'VALIDO', 'VÁLIDO', 'APP', 'SITE', 'PROMO', 'OFERTA', 'CUPOM', 'CÓDIGO', 'DESCONTO', 'OFF', 'POR', 'LINK', 'CARRINHO', 'COMPRA', 'FRETE', 'GRÁTIS', 'DE', 'DO', 'DA', 'NO', 'NA', 'EM', 'PARA', 'COM', 'RESGATE', 'ABAIXO', 'PEGAR', 'PAGINA', 'PÁGINA', 'AQUI', 'CLIQUE', 'VER', 'PRODUTO']
            if verificacao in ignorar_exatos or verificacao.isnumeric() or len(verificacao) < 3: continue
            cupom = verificacao
            break
        if cupom: break

    match_desc = re.search(r'(?i)(\d+\s*%\s*(?:off|de\s*desconto))', texto_limpo)
    if match_desc:
        desconto_extra = match_desc.group(1).strip().upper()

    regex_parcela_segura = r'(?i)(\d{1,2}\s*[xX]\s*(?:de\s*)?(?:R\$?\s*[\d\.,]+)\s*(?:sem\s*juros|s/\s*juros)?)'
    match_parc = re.search(regex_parcela_segura, texto_limpo)
    if match_parc: 
        p_str = match_parc.group(1).strip()
        p_str = re.sub(r'(?i)\s*x\s*', 'x ', p_str) 
        p_str = re.sub(r'(?i)s/\s*juros', 'sem juros', p_str) 
        parcelamento = p_str.strip()

    for linha in linhas:
        linha_baixa = linha.lower()
        if "http" in linha_baixa or "meli.la" in linha_baixa or "amzn.to" in linha_baixa or "shp.ee" in linha_baixa or "shopee.com" in linha_baixa:
            continue
        
        linha_limpa = re.sub(r'^[👉👉🏻👉🏼👉🏽👉🏾👉🏿🎟️🎟🎫🔖🏷️💡\-\s]+', '', linha).strip()

        palavras_chave = ["mínima", "mínimo", "limite", "acima de", "off", "regras", "aplique", "aplicar", "ative", "ativar", "resgate", "resgatar", "use", "insira", "anúncio", "anuncio"]
        if cupom:
            palavras_chave.append(cupom.lower())

        tem_palavra_chave = False
        for k in palavras_chave:
            if re.search(r'\b' + re.escape(k) + r'\b', linha_baixa):
                tem_palavra_chave = True
                break

        if tem_palavra_chave:
            if chamada_especial and chamada_especial.strip() == linha.strip():
                continue
            if re.search(r'(?i)(?:por|apenas)\s*(?:r\$)?\s*[\d\.,]+', linha):
                continue
                
            regra_cupom += f"{linha_limpa}\n"
            
    return cupom, preco_final, parcelamento, desconto_extra, chamada_especial, regra_cupom, preco_contexto, preco_antigo

# ==========================================
# EXTRATORES DE LOJAS E API SHOPEE
# ==========================================

def gerar_link_shopee(url_original):
    url_clean = url_original.split('?')[0].split('&')[0]
    timestamp = str(int(time.time()))
    
    # Query corrigida para API v2 (originUrls é uma lista e o retorno é shortLinkList)
    query = 'mutation { generateShortLink(input: { originUrls: ["' + url_clean + '"] }) { shortLinkList { shortLink } } }'
    payload = {"query": query}
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    # Assinatura Correta para Shopee Affiliate API v2 (Concatenação SHA256)
    factor = f"{SHOPEE_APP_ID}{timestamp}{payload_str}{SHOPEE_APP_SECRET}"
    signature = hashlib.sha256(factor.encode('utf-8')).hexdigest()
    
    headers = {
        'Authorization': f'SHA256 Credential={SHOPEE_APP_ID},Timestamp={timestamp},Signature={signature}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post('https://open-api.affiliate.shopee.com.br/graphql', headers=headers, data=payload_str.encode('utf-8'), timeout=10)
        dados = response.json()
        if 'data' in dados and dados['data'] and 'generateShortLink' in dados['data'] and dados['data']['generateShortLink']['shortLinkList']:
            link_curto = dados['data']['generateShortLink']['shortLinkList'][0]['shortLink']
            print(f"✅ [Shopee API] Sucesso: {link_curto}")
            return link_curto
        elif 'errors' in dados:
            print(f"⚠️ [Shopee API] Erro no retorno: {json.dumps(dados)}")
            # Se a API retornar um erro, retorna a URL original limpa como fallback
            return url_clean
        else:
            print(f"⚠️ [Shopee API] Resposta inesperada: {json.dumps(dados)}")
            return url_clean
    except requests.exceptions.Timeout:
        print(f"❌ [Shopee API] Timeout de Conexão. Retornando URL original.")
        return url_clean
    except Exception as e: 
        print(f"❌ [Shopee API] Falha de Conexão: {e}. Retornando URL original.")
        
    return url_clean

def extrair_dados_shopee(driver, url_original, texto_amigo=""):
    # 0. RESOLUÇÃO RÁPIDA DE LINKS (Evita enviar links encurtados para a API)
    url_resolvida = url_original
    if "shp.ee" in url_original or "s.shopee.com.br" in url_original:
        try:
            headers_nav = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            resp = requests.get(url_original, allow_redirects=True, timeout=8, headers=headers_nav)
            url_resolvida = resp.url
        except: pass

    # 1. RESOLVER O LINK USANDO O NAVEGADOR (Obrigatorio para Shopee)
    driver.get(url_resolvida)
    time.sleep(10) # Shopee é pesada...

    url_resolved_by_browser = driver.current_url
    
    # Verifica se o navegador foi redirecionado para uma página de login ou erro
    if "shopee.com.br/buyer/login" in url_resolved_by_browser or \
       "shopee.com.br/login" in url_resolved_by_browser or \
       "shopee.com.br/404" in url_resolved_by_browser:
        print(f"⚠️ [Shopee] Navegador redirecionou para página de login/erro. Tentando usar URL original para API e extração de dados.")
        url_for_api = url_original
        titulo, preco_novo, img_url = "", "", "" # Reset extracted data if on login/error page
    else:
        url_for_api = url_resolved_by_browser

    titulo, preco_novo, img_url = "", "", ""

    # 2. EXTRAÇÃO VIA JAVASCRIPT (Mais seguro contra bloqueios)
    dados_js = driver.execute_script("""
        var t = ''; var pn = ''; var img = '';
        
        var t_el = document.querySelector('div[data-bundleid="product_name"]') || document.querySelector('.V_P7_Q') || document.querySelector('.y9e306') || document.querySelector('h1.EF88_n') || document.querySelector('h1') || document.querySelector('.flex-auto.flex-column span') || document.querySelector('meta[property="og:title"]');
        if(t_el) t = (t_el.tagName === 'META') ? t_el.getAttribute('content') : t_el.innerText || t_el.textContent;
        
        if(!t || t.toLowerCase().includes('shopee brasil')) t = document.title;
        
        var pn_el = document.querySelector('.G2747_') || document.querySelector('.pq7uM9') || document.querySelector('div[class*="price"]') || document.querySelector('.O9_Y3F') || document.querySelector('meta[property="product:price:amount"]');
        if(pn_el) pn = (pn_el.tagName === 'META') ? pn_el.getAttribute('content') : pn_el.textContent.replace('R$', '').split('-')[0].trim();
        
        var img_el = document.querySelector('img[src*="file/"]') || document.querySelector('.product-briefing__image') || document.querySelector('.p_Y_qB') || document.querySelector('meta[property="og:image"]');
        if(img_el) img = (img_el.tagName === 'META') ? img_el.getAttribute('content') : img_el.getAttribute('src');
        
        return {'titulo': t, 'preco': pn, 'imagem': img};
    """)

    # Se não foi redirecionado para login/erro, usa os dados extraídos via JS
    if url_for_api == url_resolved_by_browser:
        titulo = dados_js.get('titulo', '')
        titulo = dados_js.get('titulo', '').replace('Shopee Brasil | ', '').split(' | ')[0].strip()
        preco_novo = dados_js.get('preco', '')
        img_url = dados_js.get('imagem', '')

    link_afiliado = gerar_link_shopee(url_for_api)
    
    # Se a API falhou (retornou url_for_api) E a url_for_api era de login/erro,
    # então o link final deve ser a url_original.
    if link_afiliado == url_for_api and ("shopee.com.br/buyer/login" in url_for_api or "shopee.com.br/login" in url_for_api or "shopee.com.br/404" in url_for_api):
        print(f"⚠️ [Shopee] API falhou e URL para API era de login/erro. Usando URL original como fallback para link final: {url_original}")
        link_afiliado = url_original
    elif link_afiliado == url_for_api: # API falhou, mas url_for_api era uma página de produto válida
        print(f"⚠️ [Shopee] API falhou, usando URL resolvida pelo navegador como fallback para link final: {url_for_api}")
        link_afiliado = url_for_api

    # 3. TRUQUE DA URL (Fallback para o Título se o JS falhar)
    titulo_emergencia = ""
    try:
        pedaco = urllib.parse.unquote(url_for_api).split('?')[0].rstrip('/').split('/')[-1]
        if "-i." in pedaco: titulo_emergencia = pedaco.split('-i.')[0].replace('-', ' ').title()
        elif len(pedaco) > 10: titulo_emergencia = pedaco.replace('-', ' ').title()
    except: pass

    # 5. FILTROS E LIMPEZA
    lixo = ["faça login", "shopee brasil", "shopping cart", "acesso negado", "just a moment", "ofertas incríveis", "4 off", "melhores preços", "shopee"]
    if not titulo or any(x == titulo.lower() for x in lixo) or titulo.isdigit():
        titulo = titulo_emergencia or extrair_titulo_do_texto_amigo(texto_amigo) or "Produto Shopee em Oferta"

    if not preco_novo:
        _, p_amigo, _, _, _, _, _, _ = extrair_info_texto(texto_amigo)
        preco_novo = p_amigo

    if not img_url or "logo" in img_url.lower():
        img_url = "https://logodownload.org/wp-content/uploads/2021/03/shopee-logo-0.png"

    return titulo, "", preco_novo, "", link_afiliado, img_url, "produto", ""

def extrair_dados_amazon(driver, url_original, texto_amigo=""):
    driver.get(url_original)
    time.sleep(5) 
    
    url_atual = driver.current_url
    asin = None
    
    match_asin = re.search(r'/(?:dp|gp/product|product)/([A-Z0-9]{10})', url_atual)
    if not match_asin:
        match_asin = re.search(r'ASIN=([A-Z0-9]{10})', url_atual)
        
    if match_asin:
        asin = match_asin.group(1)
        link_afiliado = f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_TAG}"
    else:
        if 'tag=' in url_atual:
            link_afiliado = re.sub(r'tag=[a-zA-Z0-9\-]+', f'tag={AMAZON_TAG}', url_atual)
        else:
            sep = '&' if '?' in url_atual else '?'
            link_afiliado = f"{url_atual}{sep}tag={AMAZON_TAG}"

    dados_js = driver.execute_script("""
        var t = ''; var pa = ''; var pn = ''; var img = ''; var cupom_site = '';
        
        var t_el = document.querySelector('#productTitle') || document.querySelector('.product-title-word-break');
        if(t_el) t = t_el.textContent.trim();
        
        var pn_inteiro = document.querySelector('.priceToPay .a-price-whole') || document.querySelector('.apexPriceToPay .a-price-whole');
        var pn_fracao = document.querySelector('.priceToPay .a-price-fraction') || document.querySelector('.apexPriceToPay .a-price-fraction');
        if(pn_inteiro) {
            var fracao = pn_fracao ? pn_fracao.textContent : '00';
            pn = pn_inteiro.textContent.replace('.', '').replace(',', '') + ',' + fracao;
        } else {
            var pn_alt = document.querySelector('#corePriceDisplay_desktop_feature_div .a-price .a-offscreen') || document.querySelector('.a-price .a-offscreen');
            if(pn_alt) pn = pn_alt.textContent.replace('R$', '').trim();
        }
        
        var pa_el = document.querySelector('.basisPrice .a-offscreen');
        if(pa_el) pa = pa_el.textContent.replace('R$', '').trim();
        
        var img_el = document.querySelector('#landingImage') || document.querySelector('#imgBlkFront') || document.querySelector('#imgTagWrapperId img') || document.querySelector('.a-dynamic-image');
        if(img_el) {
            img = img_el.getAttribute('src');
            var dynamic_img = img_el.getAttribute('data-a-dynamic-image');
            if(dynamic_img && dynamic_img.includes('{')) {
                try {
                    var obj = JSON.parse(dynamic_img);
                    img = Object.keys(obj)[0]; 
                } catch(e) {}
            }
        }

        var amz_tags = document.querySelectorAll('label[id*="coupon"], span.promoPriceBadgeLabel, .savingsBadge');
        for(var i=0; i<amz_tags.length; i++){
            var txt = amz_tags[i].textContent.trim().toUpperCase();
            if(txt.includes('CUPOM') || txt.includes('DESCONTO') || (txt.includes('%') && txt.includes('OFF'))){
                cupom_site = txt;
                break;
            }
        }
        
        return {'titulo': t, 'preco_antigo': pa, 'preco_novo': pn, 'imagem': img, 'cupom_site': cupom_site};
    """)

    titulo = dados_js.get('titulo', '')
    preco_antigo = dados_js.get('preco_antigo', '')
    preco_novo = dados_js.get('preco_novo', '')
    img_url = dados_js.get('imagem', '')
    cupom_site = dados_js.get('cupom_site', '')
    
    if not img_url or "data:image" in img_url:
        try:
            img_url = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']").get_attribute("content")
        except:
            pass

    v_pa = converter_para_numero(preco_antigo)
    v_pn = converter_para_numero(preco_novo)
    if v_pa > 0 and v_pn > 0:
        if v_pa < v_pn:
            preco_antigo, preco_novo = preco_novo, preco_antigo
        elif v_pa == v_pn:
            preco_antigo = ""

    if not titulo or titulo == "":
        titulo_amigo = extrair_titulo_do_texto_amigo(texto_amigo)
        if titulo_amigo:
            titulo = titulo_amigo

    return titulo, preco_antigo, preco_novo, "", link_afiliado, img_url, "produto", cupom_site

def extrair_dados_ml(driver, url_original, is_camaleao=False, texto_amigo=""):
    wait = WebDriverWait(driver, 15)
    driver.get(url_original)
    time.sleep(6) 
    
    dados_js = driver.execute_script("""
        var t = ''; var pa = ''; var pn = ''; var parc = ''; var img = ''; var cupom_site = '';

        var t_el = document.querySelector('h1.ui-pdp-title, .poly-component__title, h2.ui-search-item__title, h1.ui-search-breadcrumb__title, h1');
        if(t_el) t = t_el.textContent.trim();

        var pn_el = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction, .poly-price__current .andes-money-amount__fraction, .ui-search-price--size-medium .andes-money-amount__fraction');
        if(pn_el) pn = pn_el.textContent.trim();

        var pa_el = document.querySelector('s.andes-money-amount--previous .andes-money-amount__fraction, s .andes-money-amount__fraction, .ui-pdp-price__original-value .andes-money-amount__fraction, .poly-price__previous .andes-money-amount__fraction');
        if(pa_el) pa = pa_el.textContent.trim();

        var parc_el = document.querySelector('.poly-price__installments, .ui-pdp-payment-subtitle, .ui-pdp-price__subtitles');
        if(parc_el) parc = parc_el.textContent.trim();

        var img_el = document.querySelector('.ui-pdp-gallery__figure__image') || document.querySelector('img.ui-pdp-image') || document.querySelector('img.poly-component__picture');
        if(img_el) img = img_el.getAttribute('src');

        var tags = document.querySelectorAll('.ui-pdp-promotions-pill-label, .poly-promotions-pill, .ui-pdp-color--GREEN, .andes-tag__label');
        for(var i=0; i<tags.length; i++){
            var txt = tags[i].textContent.trim().toUpperCase();
            if(txt.includes('CUPOM') || (txt.includes('%') && txt.includes('OFF')) || (txt.includes('R$') && txt.includes('OFF'))){
                cupom_site = txt;
                break;
            }
        }

        return {'titulo': t, 'preco_antigo': pa, 'preco_novo': pn, 'parcelamento': parc, 'imagem': img, 'cupom_site': cupom_site};
    """)

    titulo = dados_js.get('titulo', '')
    preco_antigo = dados_js.get('preco_antigo', '')
    preco_novo = dados_js.get('preco_novo', '')
    parcelamento_ml = dados_js.get('parcelamento', '')
    img_url = dados_js.get('imagem', '')
    cupom_site = dados_js.get('cupom_site', '')

    if not img_url or "data:image" in img_url:
        try:
            img_url = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']").get_attribute("content")
        except:
            pass

    v_pa = converter_para_numero(preco_antigo)
    v_pn = converter_para_numero(preco_novo)
    if v_pa > 0 and v_pn > 0:
        if v_pa < v_pn:
            preco_antigo, preco_novo = preco_novo, preco_antigo
        elif v_pa == v_pn:
            preco_antigo = ""

    tipo_pagina = "produto"

    try:
        driver.execute_script("""
            var btns = document.querySelectorAll('button, a, span');
            for(var i=0; i<btns.length; i++){
                var txt = btns[i].innerText || btns[i].textContent;
                if(txt && (txt.toLowerCase().includes('ir para produto') || txt.toLowerCase().includes('ir para o produto'))){
                    btns[i].click();
                    return;
                }
            }
        """)
        time.sleep(5)
    except:
        pass

    if is_camaleao:
        try:
            driver.execute_script("""
                var btns = document.querySelectorAll('button, a, span');
                for(var i=0; i<btns.length; i++){
                    var txt = btns[i].innerText || btns[i].textContent;
                    if(txt && (txt.toLowerCase().includes('mostrar mais') || txt.toLowerCase().includes('ver mais'))){
                        btns[i].click();
                        return;
                    }
                }
            """)
            time.sleep(4)
            tipo_pagina = "lista_nicho"
        except:
            pass

    if titulo:
        titulo = titulo.strip()
        
    if not titulo or titulo == "" or "Mercado Livre" in titulo or "Categorias" in titulo:
        titulo_amigo = extrair_titulo_do_texto_amigo(texto_amigo)
        if titulo_amigo:
            titulo = titulo_amigo

    link_afiliado = url_original
    for _ in range(2):
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        
    try:
        clicou = driver.execute_script("""
            var shareBtns = document.querySelectorAll("button, a");
            for(var i=0; i<shareBtns.length; i++){
                var el = shareBtns[i];
                var aria = el.getAttribute('aria-label') || '';
                var classN = el.className || '';
                var txt = el.innerText || el.textContent || '';
                if(aria.toLowerCase().includes('compartilhar') || classN.toLowerCase().includes('share') || txt.toLowerCase().includes('compartilhar')){
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if clicou:
            time.sleep(2)
            link_afiliado = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[data-testid='text-field__label_link'], input.andes-form-control__field"))).get_attribute("value")
    except:
        pass
    
    return titulo, preco_antigo, preco_novo, parcelamento_ml, link_afiliado, img_url, tipo_pagina, cupom_site

# ==========================================
# ROTAS DA APLICAÇÃO E MODO MANUAL
# ==========================================

@app.route('/')
def home():
    return render_template('index.html', fontes=GRUPOS_FONTES)

@app.route('/configurar_fontes', methods=['POST'])
def configurar_fontes():
    global fontes_ativas_para_copiar
    fontes_ativas_para_copiar = request.json.get('fontes', [])
    print(f"📡 Escutando ofertas de: {len(fontes_ativas_para_copiar)} grupo(s).")
    return jsonify({"sucesso": True})

@app.route('/historico', methods=['GET'])
def get_historico():
    return jsonify(historico_ofertas)

@app.route('/gerar', methods=['POST'])
def gerar():
    dados = request.json
    url = dados.get('url', '')
    
    cupom_nome = limpar_formatacao(dados.get('cupomNome', ''))
    cupom_pct = dados.get('cupomPct', '').strip()
    cupom_fixo = dados.get('cupomFixo', '').strip()
    cupom_max = dados.get('cupomMax', '').strip()
    cupom_min = dados.get('cupomMin', '').strip()
    manual_desconto = dados.get('manualDesconto', '').strip()
    manual_parcela = dados.get('manualParcela', '').strip()

    loja_frontend = dados.get('loja', dados.get('tag', '')).strip().lower()

    if cupom_nome and ("SELO" in cupom_nome.upper() or "SELECIONE" in cupom_nome.upper()):
        cupom_nome = "CUPOM DIRETO NO PRODUTO"

    driver = configurar_driver_camuflado()
    
    try:
        is_amz = "amazon" in url.lower() or "amzn.to" in url.lower() or loja_frontend == 'amazon'
        is_shp = "shopee" in url.lower() or "shp.ee" in url.lower() or "s.shopee" in url.lower() or loja_frontend == 'shopee'
        
        if is_amz:
            t, pa, pn, parc_ml, link, img, tipo_pagina, cupom_site = extrair_dados_amazon(driver, url, "")
            loja_nome = "Amazon"
        elif is_shp:
            t, pa, pn, parc_ml, link, img, tipo_pagina, cupom_site = extrair_dados_shopee(driver, url, "")
            loja_nome = "Shopee"
        else:
            carregar_cookies(driver, "https://www.mercadolivre.com.br", "cookies_ml.pkl")
            t, pa, pn, parc_ml, link, img, tipo_pagina, cupom_site = extrair_dados_ml(driver, url, False, "")
            loja_nome = "Mercado Livre"

        if not img or "data:image" in img: 
            if loja_nome == "Mercado Livre":
                img = "https://http2.mlstatic.com/frontend-assets/ui-navigation/5.19.1/mercadolivre/logo__large_plus@2x.png"
            elif loja_nome == "Amazon":
                img = "https://m.media-amazon.com/images/G/32/social_share/amazon_logo._CB633266945_.png"
            else:
                img = "https://logodownload.org/wp-content/uploads/2021/03/shopee-logo-0.png"
        
        # MODO À PROVA DE BALAS PARA MANTER O LAYOUT
        if pn == "":
            t_exibicao = t if t else "PROMOÇÃO DETECTADA"
            emoji = '🔥'
            
            if cupom_nome:
                pct_texto = ""
                if cupom_pct:
                    limite_texto = f" até R$ {formatar_moeda(float(cupom_max))}" if cupom_max else ""
                    min_texto = f" acima de R$ {formatar_moeda(float(cupom_min))}" if cupom_min and not cupom_max else ""
                    pct_texto = f" ({int(float(cupom_pct))}% OFF{limite_texto}{min_texto})"
                elif cupom_fixo:
                    min_texto = f" acima de R$ {formatar_moeda(float(cupom_min))}" if cupom_min else ""
                    pct_texto = f" (R$ {formatar_moeda(float(cupom_fixo))} OFF{min_texto})"

                linha_cupom = f"🎟️ Código: *{cupom_nome.upper()}*{pct_texto}\n\n"
                
                chamada = f"🚨 *NOVO CUPOM DA AMAZON* 🚨" if is_amz else (f"🚨 *NOVO CUPOM DA SHOPEE* 🚨" if is_shp else "🚨 *NOVO CUPOM DO MERCADO LIVRE* 🚨")
                msg = f"{chamada}\n\n{linha_cupom}👇 *Confira todos os itens válidos no link abaixo:*\n🛒 {link}\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"
            
            else:
                if t_exibicao != "PROMOÇÃO DETECTADA":
                    msg = f"{emoji} *{t_exibicao}*\n_{loja_nome}_\n\n👇 *Confira no link abaixo:*\n🛒 {link}\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"
                else:
                    msg = f"🚨 *OFERTAS LIBERADAS!* 🚨\n{emoji} *{t_exibicao}*\n\n👇 *Confira todos os itens válidos no link abaixo:*\n🛒 {link}\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"
            
        else:
            linha_cupom = ""
            texto_final = ""
            linha_parcelamento = ""
            
            if cupom_pct or cupom_fixo: 
                valor_pn = converter_para_numero(pn)
                if valor_pn > 0:
                    aplica_desconto = True
                    if cupom_min:
                        minimo = float(cupom_min)
                        if valor_pn < minimo:
                            aplica_desconto = False

                    if aplica_desconto:
                        if cupom_pct:
                            pct = float(cupom_pct)
                            desconto = valor_pn * (pct / 100)
                            if cupom_max:
                                maximo = float(cupom_max)
                                if desconto > maximo:
                                    desconto = maximo
                            
                            pn_calculado = valor_pn - desconto
                            pn = formatar_moeda(pn_calculado)

                            limite_texto = f" até R$ {formatar_moeda(float(cupom_max))}" if cupom_max else ""
                            linha_cupom = f"🎟️ Cupom: *{cupom_nome.upper()}* ({int(pct)}% OFF{limite_texto})\n"
                            texto_final = " _(com cupom)_"
                            
                        elif cupom_fixo:
                            desconto = float(cupom_fixo)
                            pn_calculado = valor_pn - desconto
                            if pn_calculado < 0:
                                pn_calculado = 0
                            pn = formatar_moeda(pn_calculado)
                            
                            min_texto = f" acima de R$ {formatar_moeda(float(cupom_min))}" if cupom_min else ""
                            linha_cupom = f"🎟️ Cupom: *{cupom_nome.upper()}* (R$ {formatar_moeda(desconto)} OFF{min_texto})\n"
                            texto_final = " _(com cupom)_"
            
            elif cupom_nome:
                cupom_nome = limpar_formatacao(cupom_nome)
                linha_cupom = f"🎟️ Cupom: *{cupom_nome.upper()}*\n"
                texto_final = " _(com cupom)_"
                
            if manual_desconto:
                texto_final = f" _(com {manual_desconto})_"
                if not cupom_pct and not cupom_fixo:
                    match_matematica = re.search(r'(\d+)\s*%', manual_desconto)
                    if match_matematica:
                        pct = float(match_matematica.group(1))
                        valor_pn = converter_para_numero(pn)
                        if valor_pn > 0:
                            desconto = valor_pn * (pct / 100)
                            pn = formatar_moeda(valor_pn - desconto)
                
            if manual_parcela:
                parc_formatado = limpar_parcelamento(manual_parcela).lower().replace('r$', 'R$')
                linha_parcelamento = f"💳 Ou em {parc_formatado}\n"
            elif parc_ml:
                parc_formatado = limpar_parcelamento(parc_ml).lower().replace('r$', 'R$')
                linha_parcelamento = f"💳 Ou em {parc_formatado}\n"
            
            v_pa_final = converter_para_numero(pa)
            v_pn_final = converter_para_numero(pn)
            if v_pa_final > 0 and v_pn_final > 0 and v_pa_final <= v_pn_final:
                pa = "" 

            t_exibicao = t if t else "PROMOÇÃO DETECTADA"
            emoji = '🔥'
            linha_antigo = f"❌ ~De R$ {pa}~\n" if pa else ""
            
            loja_txt = "no Mercado Livre" if loja_nome == "Mercado Livre" else f"na {loja_nome}"
            
            msg = f"{emoji} *{t_exibicao}*\n_{loja_nome}_\n\n{linha_antigo}✅ Por R$ {pn}{texto_final}\n{linha_cupom}{linha_parcelamento}\n🛒 {link}\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"
            
        historico_ofertas.insert(0, {"imagem": img, "mensagem": msg.strip()})
        if len(historico_ofertas) > 5:
            historico_ofertas.pop()
            
        return jsonify({"mensagem": msg.strip(), "imagem": img})
        
    except Exception as e:
        return jsonify({"erro": str(e)})
    finally:
        driver.quit()

@app.route('/enviar_wpp', methods=['POST'])
def enviar_wpp():
    dados = request.json
    mensagem = dados.get('mensagem')
    imagem_url = dados.get('imagem')

    if not mensagem:
        return jsonify({"sucesso": False, "erro": "Dados incompletos"})

    try:
        payload = {"numero_ou_grupo": DESTINO_OFICIAL, "mensagem": mensagem}
        if imagem_url:
            payload["imagem_url"] = imagem_url
        
        resposta = requests.post('http://localhost:3000/enviar', json=payload)
        if resposta.status_code == 200:
            return jsonify({"sucesso": True})
            
        return jsonify({"sucesso": False, "erro": "Falha na API"})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": "Servidor do WhatsApp desligado."})

@app.route('/enviar_cupom_avulso', methods=['POST'])
def enviar_cupom_avulso():
    dados = request.json
    codigo = limpar_formatacao(dados.get('codigo', ''))
    info = dados.get('info', '').strip()
    link = dados.get('link', '').strip()
    imagem = dados.get('imagem', '').strip()
    
    loja_frontend = dados.get('loja', dados.get('tag', '')).strip().lower()
    
    if loja_frontend == 'amazon':
        loja_nome = "DA AMAZON"
    elif loja_frontend == 'shopee':
        loja_nome = "DA SHOPEE"
    elif loja_frontend == 'kabum':
        loja_nome = "DA KABUM"
    else:
        loja_nome = "DO MERCADO LIVRE"
    
    bloco_codigo = f"🎟️ Código: *{codigo.upper()}*\n" if codigo else ""
    bloco_regra = f"{info}\n" if info else ""
    bloco_link = f"\n👇 *Acesse pelo link abaixo:*\n🛒 {link}\n" if link else "\n"
    
    msg = f"🚨 *NOVO CUPOM {loja_nome}* 🚨\n\n{bloco_codigo}{bloco_regra}{bloco_link}\n☑️ Link do grupo: {LINKTREE_GRUPO}"
    
    try:
        payload = {"numero_ou_grupo": DESTINO_OFICIAL, "mensagem": msg.strip()}
        if imagem:
            payload["imagem_url"] = imagem
        
        resposta = requests.post('http://localhost:3000/enviar', json=payload)
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"erro": str(e)})

# ==========================================
# O FANTASMA (AUTOMAÇÃO PRINCIPAL)
# ==========================================

def extrair_loja_amigo(texto):
    """Identifica linhas que falam de lojas específicas e copia o texto original do amigo."""
    if not texto: return ""
    for linha in texto.split('\n'):
        linha_limpa = linha.strip()
        l_baixa = linha_limpa.lower()
        if "loja" in l_baixa or "vendido" in l_baixa or "🏪" in linha_limpa:
            texto_teste = re.sub(r'[^\w]', '', l_baixa)
            ignorados = ["mercadolivre", "amazon", "shopee", "ml", "lojamercadolivre", "lojaamazon", "lojashopee", "lojaml"]
            if texto_teste in ignorados: continue 
            loja = re.sub(r'^[👉🛒✅🎟️🏪\-\*\s]+', '', linha_limpa).strip()
            return loja
    return ""

def trabalhador_fantasma(url, texto_original="", imagem_base64=None):
    print(f"[FANTASMA] Iniciando processamento para URL: {url}")
    if not texto_original: return

    texto_verificacao = texto_original.lower()
    
    if any(palavra in texto_verificacao for palavra in PALAVRAS_PROIBIDAS):
        print("🛑 [FILTRO] Oferta ignorada: Contém palavra proibida.")
        return 
    
    url = limpar_url_suja(url)

    # 🛡️ ANTI-SPAM INICIAL (Bloqueio por URL antes de abrir o Selenium)
    url_chave = url.split('?')[0].lower().strip()
    url_chave = obter_link_chave_spam(url)
    with lock_duplicatas:
        agora = time.time()
        # Limpeza de itens expirados (Duplicatas e Cupons)
        for k in [k for k, v in registro_duplicatas.items() if agora - v > TEMPO_BLOQUEIO_DUPLICATAS]: del registro_duplicatas[k]
        for k in [k for k, v in registro_cupons_camaleao.items() if agora - v > TEMPO_BLOQUEIO_DUPLICATAS]: del registro_cupons_camaleao[k]

        if url_chave in registro_duplicatas:
            print(f"🚫 [ANTI-SPAM] Link já processado recentemente: {url_chave}")
            return
        registro_duplicatas[url_chave] = agora

    # ==========================================================
    # 🕵️ GATILHO DO CAMALEÃO
    # ==========================================================
    modo_camaleao = False
    
    texto_limpo = re.sub(r'[^\w\s]', '', texto_original.lower()).strip()
    primeiras_palavras = texto_limpo.split()[:10]

    termos_avulsos = [
        'novo cupom', 'cupom novo', 'cupom disponivel', 'cupom disponível', 
        'cupom liberado', 'cupom geral', 'cupom na area', 'cupom na área',
        'cupom amazon', 'cupom app', 'cupom mercado livre', 'cupom ml', 'cupom site',
        'lista de', 'cupom voltou', 'cupom ativo', 'cupom valido', 'cupons ativos',
        'cupons no mercado', 'cupons ml', 'lista de cupons', 'cupons disponiveis', 
        'novos cupons', 'cupons ainda'
    ]
    
    if 'cupom' in primeiras_palavras or 'cupons' in primeiras_palavras:
        modo_camaleao = True
    elif any(termo in texto_verificacao for termo in termos_avulsos):
        modo_camaleao = True
    elif texto_original.count('💡') >= 2:
        modo_camaleao = True

    # ==========================================================
    # 🛡️ ESCUDO INTELIGENTE (TITÂNIO)
    # ==========================================================
    if modo_camaleao:
        sinais_produto = ["por r$", "de r$", "💰 r$", "💰r$", "apenas r$"]
        if any(sinal in texto_verificacao for sinal in sinais_produto):
            modo_camaleao = False
            print("🛡️ [ESCUDO] Cancelado: A mensagem tem preço direto de produto!")

    # ==========================================================
    # 🚫 ANTI-SPAM EXCLUSIVO DE CUPONS AVULSOS (CÉREBRO 2)
    # ==========================================================
    if modo_camaleao:
        try:
            # Escaneia o texto buscando palavras que parecem códigos de cupom
            cupons_detectados = set()
            palavras = re.findall(r'\b[A-Z0-9]{5,25}\b', texto_original)
            ignoradas = {"MERCADO", "LIVRE", "AMAZON", "SHOPEE", "CUPOM", "CUPONS", "NOVO", "NOVOS", "LIMITADO", "COMPRA", "MINIMA", "MÍNIMA", "DESCONTO", "MAXIMO", "MÁXIMO", "DIRETO", "PRODUTO", "FRETE", "GRATIS", "GRÁTIS", "ACIMA", "RENOVADO", "FAMILIA", "OFERTA", "ATIVE", "PESQUISE", "DESEJADO", "GRUPO", "LINK", "AQUI", "SITE", "APP", "CARTAO", "CREDITO", "JUROS", "PARTICIPAR"}
            
            for p in palavras:
                if not p.isdigit() and p not in ignoradas:
                    cupons_detectados.add(p)
            
            with lock_duplicatas:
                # Se o bot achou cupons e TODOS eles já estão na memória, significa que é Spam!
                if cupons_detectados and all(c in registro_cupons_camaleao for c in cupons_detectados):
                    print(f"🚫 [ANTI-SPAM CAMALEÃO] Os cupons {cupons_detectados} já foram postados hoje! Abortando aviso repetido.")
                    return 
                
                # Se for novidade, salva o cupom novo na memória
                for c in cupons_detectados:
                    registro_cupons_camaleao[c] = time.time()

        except Exception as e:
            print(f"⚠️ Erro no Anti-Spam do Camaleão: {e}")

    # 🔥 O CURTO-CIRCUITO DO CAMALEÃO (POSTAGEM) 🔥
    if modo_camaleao:
        print("🦎 MODO CAMALEÃO ATIVADO: Formatando lista de cupons e injetando link fixo!")
        try:
            link_afiliado = url
            img_priorizada = "https://i.postimg.cc/yYVj8FLm/Whats-App-Image-2026-02-10-at-20-17-34.jpg" 

            if "meli.la" in url or "mercadolivre" in url or "mercadolivre.com" in url: 
                link_afiliado = "https://mercadolivre.com/sec/2EeUQxZ"
                img_priorizada = "https://i.postimg.cc/yYVj8FLm/Whats-App-Image-2026-02-10-at-20-17-34.jpg" 
                
            elif "amzn.to" in url or "amazon" in url: 
                link_afiliado = gerar_link_amazon(url)
                img_priorizada = "https://i.postimg.cc/VsTt3n3L/Whats-App-Image-2026-03-25-at-14-37-35.jpg" 
                
            elif "shp.ee" in url or "shopee" in url or "s.shopee" in url: 
                print(f"[FANTASMA] Detectado link Shopee: {url}")
                # Tenta resolver o link curto para pegar a URL real de destino antes de passar para a API
                url_para_gerar = url
                if "shp.ee" in url or "s.shopee" in url:
                    try:
                        headers_nav = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        resp = requests.get(url, allow_redirects=True, timeout=8, headers=headers_nav)
                        url_para_gerar = resp.url
                        # Só aceita a URL resolvida se não for tela de login
                        if "shopee.com.br/buyer/login" not in resp.url and "shopee.com.br/login" not in resp.url:
                            url_para_gerar = resp.url
                            print(f"🕵️ URL Shopee resolvida para: {url_para_gerar}")
                    except: pass
                link_afiliado = gerar_link_shopee(url_para_gerar)
                img_priorizada = "https://i.postimg.cc/Ssc0kWgq/Whats-App-Image-2026-03-27-at-14-54-55.jpg" 

            linhas = texto_original.split('\n')
            linhas_limpas = []
            titulo_adicionado = False

            for linha in linhas:
                l_baixa = linha.lower().strip()
                
                if not l_baixa: 
                    linhas_limpas.append("")
                    continue

                if "chat.whatsapp.com" in l_baixa or "t.me" in l_baixa or "linktr.ee" in l_baixa: continue
                if any(nome in l_baixa for nome in ["tech deals", "jotinha", "ofertachip", "promo perfumes", "cupons do rolê", "glow perfumado"]): continue

                if url in linha: 
                    linha = linha.replace(url, link_afiliado)
                elif re.search(r'https?://[^\s]+', linha):
                    if any(loja in l_baixa for loja in ["amzn", "amazon", "shopee", "shp", "meli", "mercadolivre"]):
                        linha = re.sub(r'https?://[^\s]+', link_afiliado, linha)

                if not titulo_adicionado:
                    linha_limpa = linha.replace('🚨', '').strip()
                    linha = f"🚨 {linha_limpa} 🚨"
                    titulo_adicionado = True
                else:
                    if '💡' in linha:
                        linha = linha.replace('💡', '⚠️')
                    elif any(p in l_baixa for p in ['ative', 'use', 'aplicar', 'limite', 'mínima', 'minima', 'regra', 'acima', 'desconto', 'máximo', 'maximo']):
                        if not any(linha.strip().startswith(e) for e in ['🎟', '🛒', '✅', '❌', '💳', '⚠️', '🔖', '💰']):
                            linha = f"⚠️ {linha.strip()}"

                linhas_limpas.append(linha)
            
            msg_final = "\n".join(linhas_limpas).strip()
            if LINKTREE_GRUPO not in msg_final:
                msg_final += f"\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"

            requests.post('http://localhost:3000/enviar', json={
                "numero_ou_grupo": DESTINO_OFICIAL,
                "mensagem": msg_final,
                "imagem_url": img_priorizada
            })
            print("[FANTASMA] Post de Camaleão enviado com SUCESSO!")
        except Exception as e:
            print(f"🛑 [ERRO NO CAMALEÃO] Falha ao processar: {e}")
        
        return 

    # ==========================================
    # DAQUI PARA BAIXO É A POSTAGEM NORMAL DE PRODUTO 
    # ==========================================
    
    cupom_amigo, preco_amigo, parcelamento_amigo, desconto_amigo, chamada_amigo, regra_amigo, contexto_preco_amigo, preco_antigo_amigo = extrair_info_texto(texto_original)
    loja_amigo = extrair_loja_amigo(texto_original)

    # 🔄 DETECTOR DE LINK DE CUPOM VS PRODUTO (Link Swap)
    # Se a mensagem tem 2 links da Shopee e o Node entregou o de cupom (que vem primeiro), trocamos para o de produto.
    if "shopee" in url.lower() or "shp.ee" in url.lower() or "s.shopee" in url.lower():
        todos_links_shopee = re.findall(r'(?i)https?://(?:s\.shopee\.com\.br|shopee\.com\.br|shp\.ee)/[^\s]+', texto_original)
        if len(todos_links_shopee) > 1:
            primeiro_link = limpar_url_suja(todos_links_shopee[0].split('\n')[0].split(' ')[0])
            # Se o link atual for o primeiro e houver "cupom" ou "resgate" perto dele, pegamos o segundo link (produto)
            contexto_link = texto_original[max(0, texto_original.find(primeiro_link)-50):texto_original.find(primeiro_link)].lower()
            if url == primeiro_link and any(x in contexto_link for x in ['cupom', 'resgate', 'pegue']):
                url = limpar_url_suja(todos_links_shopee[1].split('\n')[0].split(' ')[0])
                print(f"🔄 [Link Swap] Trocando link de cupom pelo link de produto: {url}")

    # 🧹 1. REMOVEDOR DE TÍTULOS GENÉRICOS DE CUPOM EM PRODUTOS
    if chamada_amigo:
        c_baixa = chamada_amigo.lower()
        if "cupom" in c_baixa and any(p in c_baixa for p in ["novo", "mercado", "disponível", "area", "área"]):
            chamada_amigo = ""

    # 🛡️ 2. ESCUDO CONTRA PREÇOS FALSOS (Ex: "Desconto máximo R$ 60")
    if preco_amigo:
        pa_num = re.sub(r'\D', '', preco_amigo.split(',')[0]) 
        lista_falsos = re.findall(r'(?i)(?:máximo|maximo|limite|acima\s*de|mínima|minima)[^\d]*(\d+)', texto_original)
        if pa_num in lista_falsos:
            preco_amigo = ""

    if cupom_amigo:
        cupom_amigo = limpar_formatacao(cupom_amigo)
        c_teste = cupom_amigo.upper().replace(" ", "")
        
        if len(c_teste) >= 3:
            match_completo = re.search(r'(?i)\b([A-Z0-9]*' + re.escape(c_teste) + r'[A-Z0-9]*)\b', re.sub(r'[^\w\s]', '', texto_original))
            if match_completo:
                cupom_resgatado = match_completo.group(1).upper()
                if len(cupom_resgatado) > len(c_teste) and "CUPOM" in cupom_resgatado:
                    cupom_amigo = cupom_resgatado
                    c_teste = cupom_amigo

        if "SELO" in c_teste or "SELECIONE" in c_teste:
            cupom_amigo = "CUPOM DIRETO NO PRODUTO"
        elif re.fullmatch(r'R\$?\d+(OFF)?', c_teste):
            cupom_amigo = "" 

    driver = configurar_driver_camuflado()
    
    try:
        is_amz = "amazon" in url.lower() or "amzn.to" in url.lower()
        is_shp = "shopee" in url.lower() or "shp.ee" in url.lower() or "s.shopee" in url.lower()
        is_ml = not is_amz and not is_shp

        if is_amz: 
            t, pa, pn, parc_ml, link_afiliado, img, _, cupom_site = extrair_dados_amazon(driver, url, texto_original)
            loja_nome = "Amazon"
        elif is_shp: 
            print(f"[FANTASMA] Processando produto Shopee: {url}")
            t, pa, pn, parc_ml, link_afiliado, img, _, cupom_site = extrair_dados_shopee(driver, url, texto_original)
            loja_nome = "Shopee"
        else:
            carregar_cookies(driver, "https://www.mercadolivre.com.br", "cookies_ml.pkl")
            t, pa, pn, parc_ml, link_afiliado, img, _, cupom_site = extrair_dados_ml(driver, url, False, texto_original)
            loja_nome = "Mercado Livre"

        # 🔥 PRIORIDADE: Usar título do alvo se disponível (Conforme solicitado)
        titulo_alvo = extrair_titulo_do_texto_amigo(texto_original)
        if titulo_alvo and len(titulo_alvo) > 8:
            t = titulo_alvo
            
        # Proteção contra loops no ML, mas permitimos Shopee seguir mesmo se falhar a conversão (pode ser link de cupom)
        if is_ml and link_afiliado == url: return

        # ==========================================================
        # 🚫 ANTI-SPAM DE PRODUTOS (CÉREBRO 1 - Não olha para os cupons)
        # ==========================================================
        # Normalização agressiva: Remove tudo que não é letra ou número para comparar títulos
        t_normalizado = re.sub(r'[^\w]', '', t).lower() if t else ""
        
        with lock_duplicatas:
            agora = time.time()
            # Se o título existe e não é genérico, checamos duplicatas
            if t_normalizado and t_normalizado not in ["produtoshopeeeoferta", "promoçãodetectada"]:
                if t_normalizado in registro_duplicatas:
                    print(f"🚫 [ANTI-SPAM] Título duplicado detectado: {t}")
                    return
                registro_duplicatas[t_normalizado] = agora
            
            # 🛡️ CORREÇÃO CRÍTICA: Verifica o link final de afiliado antes de prosseguir
            if link_afiliado:
                link_chave = link_afiliado.split('?')[0].lower().strip()
                link_chave = obter_link_chave_spam(link_afiliado)
                # Se o link final já foi postado por outra thread, aborta!
                if link_chave in registro_duplicatas:
                    if agora - registro_duplicatas[link_chave] < TEMPO_BLOQUEIO_DUPLICATAS:
                        print(f"🚫 [ANTI-SPAM] Link final já postado recentemente: {link_chave}")
                        return
                
                registro_duplicatas[link_chave] = agora

        if cupom_site:
            cupom_amigo = "DIRETO NO ANÚNCIO"
            dica_site = f"Ative o {cupom_site.lower()} no próprio anúncio"
            if dica_site.lower() not in regra_amigo.lower():
                regra_amigo = f"{dica_site}\n{regra_amigo}"

        # 📸 IMAGEM DO WHATSAPP COMO PRIORIDADE
        img_priorizada = None
        if imagem_base64: 
            img_priorizada = f"data:image/jpeg;base64,{imagem_base64}"
        elif img and not "data:image" in img: 
            img_priorizada = img 
        else:
            if is_ml: img_priorizada = "https://http2.mlstatic.com/frontend-assets/ui-navigation/5.19.1/mercadolivre/logo__large_plus@2x.png"
            elif is_amz: img_priorizada = "https://m.media-amazon.com/images/G/32/social_share/amazon_logo._CB633266945_.png"
            else: img_priorizada = "https://logodownload.org/wp-content/uploads/2021/03/shopee-logo-0.png"

        linha_cupom, bloco_regras, texto_final = "", "", ""
        
        if contexto_preco_amigo: 
            texto_final = f" _{contexto_preco_amigo}_"
        elif desconto_amigo: 
            texto_final = f" _(com {desconto_amigo})_"
        
        cupom_impresso = False
        ultima_regra = "" 

        if regra_amigo:
            for lr in regra_amigo.strip().split('\n'):
                if cupom_amigo and cupom_amigo.lower() in lr.lower() and any(x in lr.lower() for x in ['cupom', 'código', 'codigo', cupom_amigo.lower()]):
                    partes = re.split(r'(?i)\b(?:cupom|código|codigo)\b\s*:?\s*', lr)
                    lr_clean = partes[-1] if len(partes) > 1 else lr
                    lr_clean = limpar_formatacao(lr_clean)
                    if len(lr_clean) < 2: lr_clean = cupom_amigo
                    
                    # Burlador de preposições e descrições (Anti-Cupom: DE)
                    l_baixa_clean = lr_clean.lower()
                    if any(x in l_baixa_clean for x in ['%', 'off', 'página', 'anúncio', 'anuncio', 'clique', 'ative', 'ativar']) or l_baixa_clean in ['de', 'do', 'da', 'no', 'na', 'para', 'com', 'o', 'a']:
                        lr_clean = "DIRETO NO PRODUTO"
                        texto_final = f" {texto_final} (com cupom)" if "(com cupom)" not in texto_final else texto_final
                    elif "DIRETO" not in lr_clean:
                        lr_clean = re.split(r'[\s\-—|]+', lr_clean.strip())[0]
                    
                    if not cupom_impresso:
                        linha_cupom = f"🎟️ Cupom: *{lr_clean.upper()}*\n"
                        cupom_impresso, texto_final = True, " _(com cupom)_"
                    else: 
                        regra_pronta = f"💡 {lr.strip()}"
                        if regra_pronta != ultima_regra:
                            bloco_regras += f"{regra_pronta}\n"
                            ultima_regra = regra_pronta
                    continue

                texto_base = re.sub(r'(?i)\b(use|aplique|aplicar|insira|adicione|coloque|digite|utilize|utilizar|vale|ganhe|o|a|no|na|app|site|cupom|código)\b', '', lr)
                texto_base = re.sub(r'[^\w]', '', texto_base).upper()
                if cupom_amigo: texto_base = texto_base.replace(cupom_amigo.upper().replace(' ', ''), '')
                desc_base = re.sub(r'[^\w%]', '', desconto_amigo).upper() if desconto_amigo else ""
                if len(texto_base) < 3 or (desc_base and texto_base == desc_base): continue
                
                regra_pronta = f"💡 {lr.strip()}"
                if regra_pronta != ultima_regra:
                    bloco_regras += f"{regra_pronta}\n"
                    ultima_regra = regra_pronta
        
        if cupom_amigo and len(cupom_amigo) > 1 and not cupom_impresso:
            c_limpo_final = re.split(r'[\s\-—|]+', cupom_amigo.strip())[0] if "DIRETO" not in cupom_amigo else cupom_amigo
            linha_cupom = f"🎟️ Cupom: *{c_limpo_final.upper()}*\n"
            texto_final = f" {texto_final} (com cupom)" if "(com cupom)" not in texto_final else texto_final

        if preco_antigo_amigo and not pa: pa = preco_antigo_amigo
        if preco_amigo and len(preco_amigo) > 1: pn = preco_amigo

        linha_parcelamento = ""
        if parc_ml: linha_parcelamento = f"💳 Ou em {limpar_parcelamento(parc_ml).lower().replace('r$', 'R$')}\n"
        elif parcelamento_amigo: linha_parcelamento = f"💳 Ou em {limpar_parcelamento(parcelamento_amigo).lower().replace('r$', 'R$')}\n"
            
        v_pa_final, v_pn_final = converter_para_numero(pa), converter_para_numero(pn)
        if v_pa_final > 0 and v_pn_final > 0 and v_pa_final <= v_pn_final: pa = "" 

        bloco_chamada = ""
        if chamada_amigo:
            c_limpa, t_limpo = re.sub(r'[^\w\s]', '', chamada_amigo).strip().lower(), re.sub(r'[^\w\s]', '', t).strip().lower()
            if c_limpa and not (c_limpa in t_limpo or t_limpo in c_limpa):
                p_chamada, p_titulo = set(c_limpa.split()), set(t_limpo.split())
                if not (p_chamada and len(p_chamada.intersection(p_titulo)) / len(p_chamada) >= 0.4):
                    bloco_chamada = f"{chamada_amigo}\n\n"

        emoji = extrair_emoji_do_texto(texto_original)
        if not emoji: emoji = '🔥'
        
        t = remover_emojis(t).strip()
        linha_antigo = f"❌ ~De R$ {pa}~\n" if pa else ""
        bloco_chamada = remover_emojis(bloco_chamada).strip() + "\n\n" if bloco_chamada else ""
        
        if loja_amigo:
            if "loja" in loja_amigo.lower() or "vendido" in loja_amigo.lower(): linha_loja = f"🏪 {loja_amigo}\n\n"
            else: linha_loja = f"🏪 Loja: {loja_amigo}\n\n"
        else:
            linha_loja = f"_{loja_nome}_\n\n"
        
        msg_final = f"{bloco_chamada}{emoji} *{t}*\n{linha_loja}{linha_antigo}✅ Por R$ {pn}{texto_final}\n{linha_cupom}{bloco_regras}{linha_parcelamento}\n🛒 {link_afiliado}"

        if LINKTREE_GRUPO not in msg_final:
            msg_final += f"\n\n☑️ Link do grupo: {LINKTREE_GRUPO}"

        historico_ofertas.insert(0, {"imagem": img_priorizada, "mensagem": msg_final})
        if len(historico_ofertas) > 5: historico_ofertas.pop()

        print(f"[FANTASMA] Finalizado. Enviando oferta para o grupo!")
        requests.post('http://localhost:3000/enviar', json={
            "numero_ou_grupo": DESTINO_OFICIAL,
            "mensagem": msg_final,
            "imagem_url": img_priorizada
        })

    except Exception as e: 
        print(f"[FANTASMA] Erro na automação: {e}")
    finally: 
        driver.quit()

@app.route('/automacao_invisivel', methods=['POST'])
def automacao_invisivel():
    dados = request.json
    url = dados.get('url')
    grupo_origem = dados.get('grupo_origem')
    texto_original = dados.get('texto_original', '') 
    imagem_base64 = dados.get('imagem_base64') 
    
    print(f"\n[PYTHON] O Node entregou um link do grupo ID: {grupo_origem}")
    
    if grupo_origem in fontes_ativas_para_copiar and url:
        print(f"✅ Grupo Autorizado! Acordando o Fantasma para trabalhar...")
        threading.Thread(target=trabalhador_fantasma, args=(url, texto_original, imagem_base64)).start()
        return jsonify({"sucesso": True})
    
    print(f"❌ Ignorado. Esse grupo não está autorizado na minha memória no momento.")
    return jsonify({"ignorado": True})

# ==========================================================
# INICIALIZAÇÃO DO SERVIDOR
# ==========================================================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
