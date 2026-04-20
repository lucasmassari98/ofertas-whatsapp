import pickle
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://www.amazon.com.br")

print("--------------------------------------------------")
print("⚠️ ATENÇÃO: Faça o login na Amazon na janela que abriu!")
print("Certifique-se de que a barra SiteStripe apareceu lá em cima.")
print("Você tem 60 segundos antes de o robô salvar os cookies...")
print("--------------------------------------------------")

time.sleep(60) # Tempo para você digitar senha e e-mail

pickle.dump(driver.get_cookies(), open("cookies_amazon.pkl", "wb"))
print("✅ Cookies salvos com sucesso! Pode fechar.")
driver.quit()
