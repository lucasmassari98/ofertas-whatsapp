import pickle
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

# === CONFIGURAÇÕES ===
AMAZON_TAG = "suatag-20" 
LINKTREE_GRUPO = "https://linktr.ee/lcml_ofertas"

def descobrir_emoji(titulo):
    """Lê o título e devolve um emoji temático"""
    t = titulo.lower()
    if any(x in t for x in ['celular', 'smartphone', 'iphone', 'motorola', 'samsung']): return '📱'
    if any(x in t for x in ['notebook', 'laptop', 'macbook', 'pc', 'computador']): return '💻'
    if any(x in t for x in ['tv', 'televisão', 'smart tv', 'monitor']): return '📺'
    if any(x in t for x in ['fone', 'headset', 'airpods', 'earbuds', 'ouvido']): return '🎧'
    if any(x in t for x in ['mouse', 'mousepad', 'teclado']): return '🖱️'
    if any(x in t for x in ['perfume', 'eau de parfum', 'fragrância', 'colônia']): return '✨'
    if any(x in t for x in ['tênis', 'sapato', 'calçado', 'chinelo', 'botas']): return '👟'
    if any(x in t for x in ['camisa', 'camiseta', 'roupa', 'jaqueta', 'moletom']): return '👕'
    if any(x in t for x in ['relógio', 'smartwatch', 'apple watch']): return '⌚'
    if any(x in t for x in ['jogo', 'game', 'playstation', 'xbox', 'nintendo', 'console']): return '🎮'
    if any(x in t for x in ['livro', 'kindle', 'box']): return '📚'
    if any(x in t for x in ['casa', 'cozinha', 'eletrodoméstico', 'geladeira', 'fogão', 'ar condicionado']): return '🏠'
    if any(x in t for x in ['ferramenta', 'furadeira', 'parafusadeira']): return '🛠️'
    
    return '📦' # Se não reconhecer nada, usa a caixinha

def criar_link_amazon(url_original):
    if "?" in url_original:
        return url_original.split("?")[0] + f"?tag={AMAZON_TAG}"
    return url_original + f"?tag={AMAZON_TAG}"

def gerar_mensagem(plataforma, titulo, preco_antigo, preco_novo, link_afiliado, emoji):
    linha_preco_antigo = f"❌ De R$ {preco_antigo}\n" if preco_antigo else ""
    mensagem = f"""
{emoji} {titulo}
• Loja Validada no {plataforma}

{linha_preco_antigo}✅ Por R$ {preco_novo}

🛒 {link_afiliado}

☑️ Link do grupo: {LINKTREE_GRUPO}
"""
    return mensagem

def carregar_cookies(driver, dominio, arquivo_cookie):
    driver.get(dominio)
    try:
        cookies = pickle.load(open(arquivo_cookie, "rb"))
        for cookie in cookies:
            driver.add_cookie(cookie)
        print(f"✅ Cookies de {dominio} carregados!")
    except FileNotFoundError:
        print(f"⚠️ Arquivo {arquivo_cookie} não encontrado.")

def extrair_dados_amazon(driver, url_original):
    titulo = driver.title.split("|")[0].strip()
    preco_antigo, preco_novo = "", ""
    return titulo, preco_antigo, preco_novo, criar_link_amazon(url_original)

def extrair_dados_ml(driver, url_original):
    wait = WebDriverWait(driver, 10)
    
    # === PASSO 1: Clicar no produto na vitrine ===
    print("🔍 [PASSO 1] Verificando se caiu numa vitrine...")
    try:
        seletor_vitrine = "a.poly-component__title, a.poly-component__link--action-link"
        elemento_produto = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor_vitrine)))
        print("   🎯 Vitrine detectada! Clicando no produto...")
        driver.execute_script("arguments[0].click();", elemento_produto)
        time.sleep(4)
    except:
        print("   👉 Indo direto para a página do produto.")

    # === EXTRAÇÃO DE DADOS ===
    titulo, preco_antigo, preco_novo = "", "", ""
    link_afiliado = url_original 
    
    print("🔍 Buscando Título...")
    try:
        titulo_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ui-pdp-title")))
        titulo = titulo_el.text.strip()
        print(f"   ✅ Achou o produto: {titulo[:30]}...")
    except:
        titulo = driver.title.split("|")[0].strip()
        print("   ⚠️ Usando título da aba.")
        
    print("🔍 Buscando Preços...")
    try:
        preco_novo_el = driver.find_element(By.CSS_SELECTOR, "div.ui-pdp-price__second-line span.andes-money-amount__fraction")
        preco_novo = preco_novo_el.text
        print(f"   ✅ Novo: R$ {preco_novo}")
        try:
            preco_antigo_el = driver.find_element(By.CSS_SELECTOR, "s.andes-money-amount--previous span.andes-money-amount__fraction")
            preco_antigo = preco_antigo_el.text
            print(f"   ✅ Antigo: R$ {preco_antigo}")
        except:
            pass
    except:
        print("   ❌ Erro ao buscar os preços.")

    # === MATA-POPUP TURBINADO ===
    print("🧹 Fechando pop-ups (Meli Dólar, Entendi, etc)...")
    try:
        # Procura botões com os textos "Entendi" ou "Agora não"
        botoes_fechar = driver.find_elements(By.XPATH, "//button[contains(text(), 'Entendi')] | //span[contains(text(), 'Entendi')] | //button[contains(text(), 'Agora não')]")
        for btn in botoes_fechar:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                print("   ✅ Botão 'Entendi' clicado e fechado!")
                time.sleep(1)
    except:
        pass

    for _ in range(3):
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)

    # === PASSO 2 e 3: Compartilhar e Copiar Link ===
    print("⏳ Aguardando barra de Afiliado (3s)...")
    time.sleep(3)

    print("🔍 [PASSO 2] Buscando botão 'Compartilhar'...")
    try:
        btn_compartilhar = wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Compartilhar')]")))
        driver.execute_script("arguments[0].click();", btn_compartilhar)
        print("   ✅ Botão Compartilhar clicado!")
        
        print("⏳ [PASSO 3] Aguardando caixinha do link abrir...")
        try:
            textarea_link = WebDriverWait(driver, 4).until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[data-testid='text-field__label_link']")))
        except:
            print("   ⚠️ A caixinha não abriu de primeira. Insistindo...")
            ActionChains(driver).send_keys(Keys.ESCAPE).perform() 
            time.sleep(1)
            driver.execute_script("arguments[0].click();", btn_compartilhar)
            textarea_link = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[data-testid='text-field__label_link']")))

        link_gerado = textarea_link.get_attribute("value")
        if link_gerado:
            link_afiliado = link_gerado
            print(f"   ✅ SEU Link capturado com sucesso: {link_afiliado}")
            
    except Exception as e:
        print("   ❌ Falha nos Passos 2 ou 3.")
        
    return titulo, preco_antigo, preco_novo, link_afiliado

def principal():
    print("=== GERADOR DE PROMOÇÕES AUTÔNOMO ===")
    url = input("Cole o link aqui: ")
    
    opcoes = Options()
    opcoes.add_argument("--start-maximized")
    opcoes.add_argument("--log-level=3") 
    
    print("\n🚀 Abrindo navegador...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opcoes)
    
    plataforma = "Loja"
    link_final = url
    
    try:
        if "amazon" in url.lower():
            plataforma = "Amazon"
            carregar_cookies(driver, "https://www.amazon.com.br", "cookies_amazon.pkl")
            driver.get(url)
            titulo, preco_antigo, preco_novo, link_final = extrair_dados_amazon(driver, url)
            
        elif "mercadolivre" in url.lower() or "meli" in url.lower():
            plataforma = "Mercado Livre"
            carregar_cookies(driver, "https://www.mercadolivre.com.br", "cookies_ml.pkl")
            print(f"\n📦 Acessando o link repassado...")
            driver.get(url)
            titulo, preco_antigo, preco_novo, link_final = extrair_dados_ml(driver, url)

        if not preco_novo:
            print("\n⚠️ O robô precisará de ajuda com os preços.")
            preco_antigo = input("Digite o preço ANTIGO (ou Enter se não tiver): ")
            preco_novo = input("Digite o preço NOVO: ")
            
        # Puxa o emoji dinâmico baseado no título lido
        emoji_produto = descobrir_emoji(titulo)
        
        texto_pronto = gerar_mensagem(plataforma, titulo, preco_antigo, preco_novo, link_final, emoji_produto)
        
        print("\n" + "="*30)
        print("MENSAGEM PRONTA:")
        print("="*30)
        print(texto_pronto)
        
    except Exception as e:
        print(f"\n❌ Erro Geral: {e}")
    finally:
        time.sleep(2)
        driver.quit()

if __name__ == "__main__":
    principal()
