import pickle
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

print("🚀 Abrindo o navegador para salvar seu login...")

opts = Options()
opts.add_argument("--window-size=1920,1080")
# O SEGREDO: A mesma identidade (User-Agent) que o robô usa!
opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

try:
    # Passo 1: Amazon
    driver.get("https://www.amazon.com.br")
    print("\n" + "="*50)
    print("🛑 ATENÇÃO: Uma janela do Chrome abriu!")
    print("1. Vá nessa janela e faça seu login na Amazon.")
    print("2. IMPORTANTE: Marque a caixinha 'Mantenha-me conectado'.")
    print("3. Depois que logar e a página inicial da Amazon carregar por completo...")
    input("👉 APERTE A TECLA 'ENTER' AQUI NO TERMINAL PARA SALVAR! ")
    
    pickle.dump(driver.get_cookies(), open("cookies_amazon.pkl", "wb"))
    print("✅ Cookies da Amazon salvos com sucesso!")
    
    # Passo 2: Mercado Livre
    driver.get("https://www.mercadolivre.com.br")
    print("\n" + "="*50)
    print("🛑 Agora o site do Mercado Livre abriu na mesma janela!")
    print("1. Faça seu login no Mercado Livre.")
    print("2. Depois que logar e a página inicial carregar...")
    input("👉 APERTE A TECLA 'ENTER' AQUI NO TERMINAL PARA SALVAR! ")
    
    pickle.dump(driver.get_cookies(), open("cookies_ml.pkl", "wb"))
    print("✅ Cookies do Mercado Livre salvos com sucesso!")
    
    print("\n🎉 Tudo pronto! Pode fechar essa janela. Seu robô agora tem acesso total!")

except Exception as e:
    print(f"Erro: {e}")
finally:
    driver.quit()
