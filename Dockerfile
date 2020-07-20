FROM lambci/lambda:build-python3.8

# Download chromedriver
RUN curl -SL https://chromedriver.storage.googleapis.com/2.32/chromedriver_linux64.zip > chromedriver.zip
RUN unzip chromedriver.zip -d /chrome/

# Download headless chromium
RUN curl -SL https://github.com/adieuadieu/serverless-chrome/releases/download/v1.0.0-29/stable-headless-chromium-amazonlinux-2017-03.zip > headless-chromium.zip
RUN unzip headless-chromium.zip -d /chrome/

# Clean up
RUN rm chromedriver.zip headless-chromium.zip
