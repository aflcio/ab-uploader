# ab-uploader
Action Builder upload automation

curl -SL https://chromedriver.storage.googleapis.com/2.32/chromedriver_linux64.zip > chromedriver.zip
unzip chromedriver.zip -d chromelayer/bin/
curl -SL https://github.com/adieuadieu/serverless-chrome/releases/download/v1.0.0-29/stable-headless-chromium-amazonlinux-2017-03.zip > headless-chromium.zip
unzip headless-chromium.zip -d bin/
rm chromedriver.zip chromelayer/headless-chromium.zip
