import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import yaml

load_dotenv()
driver = webdriver.Chrome()
instance = os.getenv('AB_INSTANCE')
BASE_URL = 'https://%s.actionbuilder.org' % instance
with open(r'fields.example.yml') as file:
    FIELD_MAP = yaml.load(file, Loader=yaml.FullLoader)

def login():
    driver.get(BASE_URL + '/login')
    WebDriverWait(driver, 10).until(EC.title_contains("Login"))
    driver.find_element_by_id('email').send_keys(os.getenv('AN_LOGIN'))
    driver.find_element_by_id('password').send_keys(os.getenv('AN_PASSWORD'))
    driver.find_element_by_id('loginButton').click()
    WebDriverWait(driver, 10).until(EC.title_contains("List"))

def start_upload(type, campaign, filename):
    if type is 'people':
        driver.get(BASE_URL + '/admin/upload/people/mapping')
    if type is 'info':
        driver.get(BASE_URL + '/admin/upload/tags/mapping')
    WebDriverWait(driver, 10).until(EC.title_contains("Upload"))
    # Upload file
    driver.find_element_by_css_selector('input[type="file"]').send_keys(filename)
    # Select campaign
    driver.find_element(
        By.XPATH, "//mat-select[@data-test-id='campaignUploadSelect']").send_keys(campaign)
    # Select ID for matching
    ID_SOURCE = (By.XPATH, "//mat-select[@placeholder='Id to use for matching']")
    ID_DEST = (By.XPATH, "//mat-select[@placeholder='Upload Column'][@aria-disabled='false']")
    FIELD_SOURCE = (By.CLASS_NAME, 'mapping__col--source')
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(ID_SOURCE))
    driver.find_element(*ID_SOURCE).send_keys('Custom ID')
    # Map Fields
    if type is 'people':
        col_name = (By.CSS_SELECTOR, '.mapping__col--source input')
        fields = driver.find_elements_by_class_name('mapping')
        for field in fields[:-2]:  # last two are notification and button
            if field.find_elements(*col_name):
                column = field.find_element(*col_name).get_attribute('value')
                if column in FIELD_MAP[type]:
                    field.find_element(
                        By.TAG_NAME, 'mat-select').send_keys(FIELD_MAP[type][column])
        driver.find_element(By.CSS_SELECTOR, '.mapping button').click()
    if type is 'info':
        WebDriverWait(driver, 5).until(EC.presence_of_element_located(ID_DEST))
        driver.find_element(*ID_DEST).send_keys('id')
        WebDriverWait(driver, 5).until(lambda d: len(d.find_elements(*FIELD_SOURCE)) > 1)
        fields = driver.find_elements(*FIELD_SOURCE)
        for field in fields[1:]:
            col_name = field.find_element(
                By.TAG_NAME, 'input').get_attribute('value')
            if col_name in FIELD_MAP[type]:
                dest = field.find_element(By.XPATH, './following-sibling::*[2]')
                dest.find_element(By.XPATH, './/mat-select').click()
                driver.find_element(By.TAG_NAME, 'mat-option') \
                   .send_keys(FIELD_MAP[type][col_name]['type'])
                driver.find_element(By.TAG_NAME, 'mat-option').click()
                dest.find_element(By.XPATH, './/input') \
                    .send_keys(FIELD_MAP[type][col_name]['name'])
                dest.find_element(By.XPATH, './/ul').click()
                dest.find_element(By.XPATH, './/ul//ul').click()
        driver.find_element(By.CSS_SELECTOR, '.mapping button').click()
        WebDriverWait(driver, 10).until(EC.title_contains('Map Response'))
        driver.find_element(
            By.XPATH, '//app-upload-tag-categories-mapping/div/div/button').click()
        WebDriverWait(driver, 10).until(EC.title_contains('Upload Confirm'))
        driver.find_element(
            By.XPATH, '//app-upload-tags-confirm-create-tags//button').click()


def confirm_upload():
    # Wait for upload to process
    WebDriverWait(driver, 300).until(
        EC.presence_of_element_located((By.TAG_NAME, 'snack-bar-container'))
    )
    driver.find_element(By.CSS_SELECTOR, 'snack-bar-container .link').click()

    # Confirm upload
    WebDriverWait(driver, 10).until(EC.title_contains('Upload Confirm'))
    for checkbox in driver.find_elements(By.XPATH, '//mat-checkbox//label'):
        checkbox.click()
    driver.find_element(By.CSS_SELECTOR, 'app-upload-confirm button').click()


def finish_upload(campaign):
    # Wait for upload to complete
    STATUS_LOCATOR = (
        By.XPATH, "//app-upload-list//a[text()='%s']/../following-sibling::div[2]" % campaign)
    retries = 10
    timeout = 5
    while retries > 0:
        WebDriverWait(driver, 10).until(EC.title_contains("View Uploads"))
        try:
            WebDriverWait(driver, timeout=timeout, poll_frequency=timeout).until(
                EC.text_to_be_present_in_element(STATUS_LOCATOR, 'Complete'))
            break
        except TimeoutException:
            driver.refresh()
            retries -= 1
            timeout *= 2
            print('Upload in progress. %d retries remaining' % retries)
    print("Upload Complete")

if __name__ == '__main__':
    filename = '/Users/jmann/Desktop/AB Data/Sample:Demo/Auto Upload Test Data.csv'
    campaign = 'Upload Test'
    login()
    start_upload('people', campaign, filename)
    confirm_upload()
    finish_upload(campaign)
    start_upload('info', campaign, filename)
    confirm_upload()
    finish_upload(campaign)
    driver.quit()
