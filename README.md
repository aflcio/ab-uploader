# Action Builder Upload
Automates uploads to Action Builder with AWS S3, Lambda and Step Functions.

## To run locally
Install [ChromeDriver](https://chromedriver.chromium.org) and update with the path to your file and config **local.py**.

```
source venv/bin/activate
pip install -r requirements.txt
python local.py
```

## Deploy to AWS
```
npm install
serverless deploy
```
